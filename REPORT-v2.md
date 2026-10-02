# intersoulligence v2 开发汇报（M1-M5）

> 汇报时间：2026-10-02。范围：v2 全部里程碑（M1 存储契约 → M5 验收）的实施结果、遇到的问题、跳过项与**待你给出修改意见的决策点**。
> 设计依据：`ARCHITECTURE.md` §13（2026-10-01 定稿）；工程追踪：`PRD.md` §15。

## 总览

| 验收项（§13.6） | 结果 |
|---|---|
| pytest 全量 | **258 用例全过**（210 v1 基线行为不变 + 48 v2 新增），覆盖率 92% |
| demo 12 步闭环 | 12/12 PASS |
| MCP 冒烟 | 5 工具 + 全部新 operation 端到端通过 |
| ADR-1 门槛：冷启动 | **52ms**（门槛 <1s，含首次工具调用） |
| ADR-1 门槛：每轮 harness 开销 | **p99 = 4.49ms**（门槛 <50ms；200 轮基准，含 Scribe 写入） |
| 记忆增长闭环（canned） | 对话 → 2a → 双路召回 → F3 → F4 → 2c → 2d → overlay → prompt 演化，全链路测试通过 |

一句话结论：**v2 的四个里程碑全部实施完成，v1「能跑通闭环但无法长期活着」的三个写侧缺口已全部补上**——2a/2c 有了运行时写入路径，F4 衰减的对象真实存在，2d 账本第一次能真的改变 Layer 1（通过 overlay 在 prompt 合成时生效）。

各里程碑交付：

| 里程碑 | 交付物 |
|---|---|
| M1 存储契约 | `persona_runtime/storage/`（端口契约 + SQLite 参考实现 + FileSnapshotStore），全生产路径去 conn 化，4 处方言移植点消除 |
| M2 写侧闭环 | D1 `append_2a_entry` / D2 `append_2a_batch`（enum 扩展 `episode`）+ Scribe 对话→2a 规则提取 + F3 `persist_session_summary`（2a episode + 2b + markdown 投影三路落点） |
| M3 语义召回 | `HashingEmbeddingProvider`（默认注入）+ `interaction_embeddings` 表 + `find_similar` 暴力余弦 + C1 双路召回（`recall_channels` 标注）+ C5 语义封顶 cautious + F4 向量行同步删除 |
| M4 演化应用 | `PatternRepo.upsert_from_cluster`（confidence 只增 / evidence 累计）+ Librarian 规则聚类（每 6 次快照自动触发）+ `overlay.yaml`（A11 加载 + PROTECTED 拒改 + D6 挂钩 + system_prompt 合成） |
| M5 验收 | 上述全部验收项 |

---

## 逐阶段：做了什么、遇到什么问题

### M1 存储契约（2026-10-01）

**做了什么**：StorageBackend Port/Adapter 契约（五个仓储 + EmbeddingProvider 接口）；SQLite 参考实现；F1/F2 文件逻辑转正为 SnapshotStore；15 个生产函数去 conn 化；4 处方言移植点消除。

**遇到的问题（均已解决）**：

1. **去掉 `datetime('now')` 默认值暴露了隐藏依赖**——conftest 种子 helper 和适配器初版漏传 `created_at`/`updated_at`（v1 一直靠 DB 默认值兜底），引发 NOT NULL 约束失败。这正是该方言移植点想逼出来的显式化：现在所有时间戳都来自 Python 侧唯一入口 `utc_now_iso()`。
2. **快照测试的排序不确定性**——同一毫秒内两次保存时 mtime 相同，`load_latest` 排序歧义。测试用显式 `os.utime` 确定化。注意：这是 v1 F2 就存在的潜在问题，只是 v1 没有触发它的用例。

### M2 写侧闭环（2026-10-02）

**做了什么**：D1/D2 接口层（type 枚举校验 + 80 字上限 + 整批原子）；`scribe.py` 每轮从对话提取互动事实并批量写入（harness 主闭环内自动执行，故障隔离）；`persistence.F3` 会话总结三路落点 + markdown 投影；端口扩展 `find_by_conversation`；MCP 新增 3 个 operation。

**遇到的问题 / 我做的决定（第 ① 项需要你的意见）**：

1. **【待你意见】Scribe 的实体来源**：规则提取时把「已知实体」写进 2a 的 `entities` 字段（C5 双通道判定和精确召回都依赖它）。当前 `known_entities` 由调用方传入——但生产链路里该传什么没有定稿。候选：a) 2b 已有实体自动汇总；b) schema 声明 + 2b 动态合并；c) 保持调用方传入。**现状：harness 主闭环暂传 None（entities 为空，精确召回靠不上、语义召回可兜底），lifecycle 测试里手动传入验证了链路。**
2. **2a 类型枚举扩展了 `episode`**（F3 会话总结的落点类型）——设计文档 §13.5 要求 episode 条目落 2a 但没说枚举怎么办，我选择扩枚举而不是塞进既有五类。已记入 §13.7。
3. **F3 的触发是显式的**：契约说「会话正常结束触发」，但 harness 无法感知会话结束（work agent 的职责），所以实现为 MCP operation `persist_session_summary` + Python 函数，由 work agent / 用户在会话结束时调用。**没有人调用它就没有总结**——这一点未来接 opencode 时要在 demo 配置里挂上。

### M3 语义召回（2026-10-02）

**做了什么**：`HashingEmbeddingProvider`（字符 bigram 哈希）；`interaction_embeddings` 向量表；`find_similar`；C1 双路召回（精确 ∪ 语义，每条记录带 `recall_channels` 通道标注）；C5 联动（仅语义命中 → cautious 封顶，防「把联想当事实说出口」）；F4 的 30 天向量删除与 90 天内容清空同步删向量行。

**遇到的问题（第 ① 项是本次开发最有价值的 bug）**：

1. **dim=64 的哈希碰撞对消失真**：初版 64 维向量上，查询「读论文原文」与文档「我喜欢直接读论文」的余弦相似度**精确等于 0**——共享的 bigram（读论/论文）在其他 token 的哈希碰撞下被逐维对消。诊断后把默认维度提到 256，问题消失。这个 bug 的价值在于它证明了「语义召回必须有真实用例盯着」，纯单元测试（确定性往返）抓不住它。
2. **【待你意见】默认注入 provider**：`from_config` 现在默认带 HashingEmbeddingProvider（开箱即有语义召回，写入即生成向量）；显式传 `None` 可关闭。代价：每条 2a 写入多一次哈希计算（实测无感）。我认为值得，但这改变了 v1 `vector_indexed` 字段的语义——**无 provider 写入的行 vector_indexed=0，衰减时会跳过 vector_deleted 阶段、90 天直接 content_wipe**（语义自洽：没有向量就没有「删向量」可做）。
3. **暴力余弦的性能债**：单用户万行量级、256 维、纯 Python——千行实测毫秒级，**万行估算会超过 50ms p99 门槛**。升级路径已写在 §13.7：sqlite-vec 或 numpy。当前数据量（新项目冷启动）远未到，不算违约，先记账。

### M4 演化应用（2026-10-02）

**做了什么**：`upsert_from_cluster`（confidence 只增不减 + evidence_count 累计 + UNIQUE 去重，严格 §7.3 语义）；`librarian.py` 对 cooling 期 2a 行做贪心凝聚聚类（preference 类型优先），harness 每 6 次快照自动触发，也可 MCP 手动触发；`overlay.py` 实现 2d→Layer 1 演化：D6 写入 affected_layer='Layer 1' 的自评 → 自动落 `persona.overlay.yaml` 调整列表 → A11 启动加载（Layer 0 键出现即拒绝）→ `build_system_prompt` 渲染「演化调整」段。

**遇到的问题 / 设计取舍（第 ① 项需要你的意见）**：

1. **【待你意见】overlay 的演化是 prompt 级的，不是 yaml 字段改写**：2d 的 change 是自由文本（「语气更克制」），无法可靠地自动映射成 Layer 1 的结构化字段（sentence_length / catchphrases…）。我的方案是双形态：`layer1_overrides`（结构化覆盖，深合并渲染）+ `adjustments`（2d 文字指令，渲染为 prompt 里独立的「演化调整」段，声明为「属于你 Layer 1 的现行表达」）。这是诚实的最小机制，但意味着**演化对表达的影响强度取决于 LLM 对该段的遵循度**——效果要等真实 LLM 链路验证。如果你想要「自评必须落到具体字段」的强约束，需要重新设计 2d 的写入格式（change 结构化），工作量不小。
2. **A11 的 PROTECTED 校验是键名级的**（`layer0` / `identity` / `value_kernel` / `scenarios` 出现在 overlay 顶层即拒绝加载）——宁可错杀，与 D8 的伦理校验同风格。

### M5 验收（2026-10-02）

**做了什么**：扩展版 MCP 冒烟（5 工具 + 全部新 operation 端到端）；`tests/test_memory_lifecycle.py` 记忆增长闭环（两用例：全链路生命周期 + harness 主闭环自动写入）；ADR-1 两个 profiling 门槛首次有了实测数字，全部达标且余量充足。

**遇到的问题**：无。测试编写中发现 Scribe 不传 `known_entities` 时精确召回为空（预期行为，见 M2 问题 1），已按真实链路修正测试。

---

## 跳过 / 未实施（按你的指示，明确跳过而非含糊）

| 项 | 状态 | 理由 | 建议 |
|---|---|---|---|
| **persona bundle 实施**（§13.4 目录结构 / manifest / JSONL 交换 / .isoul） | 未实施 | M1-M5 里程碑清单不含 bundle；「DB 为源、markdown 为投影」已部分落地（F3 的 `content/sessions/*.md`） | 随 v3 H1/H2 跨 agent 可移植一起做，bundle 的消费者（导入/导出）到那时才存在 |
| **真语义 Embedding 模型**（本地 1B-7B / API） | 未接入 | 引入模型运行时是重决策（依赖、体积、速度），不适合悄悄做 | HashingEmbeddingProvider 已验证全链路；你选定模型后只需实现端口并注入 |
| **sqlite-vec** | 未接入 | 避免网络依赖 + 当前数据量不需要 | 万行量级到来时升级（接口不变） |
| **opencode 真 LLM 端到端** | 维持延后决策（2026-10-01） | 你的既定决策：产品成型后连同基准与实例一起做 | — |
| v1.1 搁置问题 7/8/9（评分口径 / 自评偏差 / 模型 ID） | 维持挂起 | 属 E2E 基准范畴 | 随产品成型阶段处理 |

其余搁置问题状态：问题 4（2b vs 2d 边界）已随 F3 契约定稿（F3 永不产 2d）；问题 3/6 在 M2 的失败隔离与显式时间戳中消化；问题 10（system_prompt 与 yaml 重复）在 M1 shim 化后不再成立；问题 11（覆盖盲区）随 48 个新用例收敛。

---

## 待你给出修改意见的决策点（汇总）

| # | 决策点 | 我的现状/倾向 | 需要你定 |
|---|---|---|---|
| ① | **Scribe 的 known_entities 来源**（影响精确召回与 C5 双通道判定的可用性） | 暂传 None，语义召回兜底 | a) 2b 实体自动汇总 / b) schema+2b 合并 / c) 维持调用方传入 |
| ② | **默认注入 HashingEmbeddingProvider**（开箱语义召回 vs 写入开销；vector_indexed 语义变化） | 已默认开启 | 维持 / 改为默认关闭 |
| ③ | **overlay 演化强度**：prompt 级文字指令（现状） vs 2d 写入结构化 + 字段级强制改写 | prompt 级最小机制 | 维持并等真 LLM 验证 / 升级为强约束（需重新设计 2d 格式） |
| ④ | **语义检索性能升级时机**（sqlite-vec / numpy） | 记账不动，万行量级再升 | 认可 / 要求现在就换 |
| ⑤ | 覆盖率 93% → 92%（新模块边界分支） | 接受（绝对数 +48 用例） | 如有 95% 红线再议 |

## 附：变更清单

- 新增模块：`storage/base.py`、`storage/sqlite_adapter.py`、`storage/file_snapshot.py`、`storage/embedding.py`、`scribe.py`、`librarian.py`、`overlay.py`
- 新增测试：`test_storage.py`（20）、`test_v2_features.py`（26）、`test_memory_lifecycle.py`（2）
- 重构：`memory_recall.py` / `memory_write.py` / `persistence.py` / `harness.py` / `mcp_server/*` / `demo/run.py` / `config.py`（`content_dir`、`cluster_interval_snapshots`）
- 新增 MCP operation：`append_2a`、`append_2a_batch`、`persist_session_summary`、`cluster_patterns`（layer2）；`overlay` 字段（layer0）——工具数保持 5 个
- 提交记录：M1 `09c1e01`；M2-M5 见本次提交
