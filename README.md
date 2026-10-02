# intersoulligence

> 人机关系人格模块（persona module）的运行时实现。
> 工程化落地 `agent-human` Wiki 设计稿中的 28 个 v1 接口契约。

## 这是什么

`intersoulligence` 是一个**可被多个 work agent 加载的人格模块**——不是 agent 本体。它提供：

- **Layer 0 IDENTITY**（PROTECTED）：核心身份 + 价值内核 + 场景价值变体
- **Layer 1 EXPRESSION**（半稳定）：语气 / 口头禅 / 称呼 / 蛐蛐 / 转场白语
- **Layer 2 MEMORY**（MUTABLE）：2a 互动事实 / 2b 实体画像 / 2c 长期行为模式 / 2d 自我更新账本
- **harness**：三环节（grill / plan / build）的主循环协调 + C5/C6 强制约束点
- **StorageBackend**（v2）：可插拔存储抽象——SQLite 参考实现，向量后端（sqlite-vec）与关系型后端按同一契约接入
- **MCP server**：5 个工具暴露给 work agent

## 文档导航（2026-10-01 整合后共 3 份）

| 文档 | 内容 |
|---|---|
| `README.md`（本文） | 项目入口 + 快速开始 + demo 使用 |
| `ARCHITECTURE.md` | **架构设计总纲**：三层架构 / 场景边界 / 阶段切换协议 / 遗忘机制 / 全局规则 / harness 运行时 / 28 接口契约总览 / **v2 设计定稿（§13：记忆生命线 + 存储抽象 + persona bundle）** |
| `PRD.md` | **技术执行总纲**：需求 / 接口→SQL→MCP 映射 / 测试 / 验收 + 功能追踪（§15）/ v1.1 修复记录（§16）/ 变更记录（§17）/ 端到端验收日志（§18） |
| `REPORT-v2.md` | **v2 开发汇报**：M1-M5 逐阶段结果 / 遇到的问题 / 跳过项 / 待用户决策点 |

设计推导原文（外部 Wiki `agent-human/`）：`core/` 五份定稿（架构 / 场景边界 / 阶段切换 / 遗忘 / harness）、`runtime/` 接口契约两视角、`research/PRD-v1-定稿.md`。

## 快速开始

```bash
# 安装依赖
uv sync --extra dev

# 运行测试（12 步关键路径 + 28 接口 + 存储契约 + v2 新能力 + 记忆增长闭环 + MCP 5 工具）
uv run pytest tests/ -v

# 运行 demo（不接真实 LLM，用 canned response 模拟，详见下文 demo 节）
uv run python demo/run.py

# 启动 MCP server（stdio transport，供 work agent 加载）
uv run intersoulligence-server
```

## 工程结构

```
intersoulligence/
├── README.md / ARCHITECTURE.md / PRD.md   # 三份整合文档
├── persona_runtime/        # 人格模块核心（config / storage 存储抽象 / schema_loader / signal_parser / memory_recall / memory_write / self_check / persistence / scheduler / harness）
├── mcp_server/             # MCP server（5 工具）
├── data/                   # persona_schema.yaml 声明 + SQLite db + 快照
├── tests/                  # pytest（关键路径 + 全接口 + 存储契约 + MCP 工具）
└── demo/                   # demo work agent（run.py + opencode 配置示例）
```

## 28 个 v1 接口

按工程调用时机分组（逐接口契约见 `ARCHITECTURE.md` §11，SQL / MCP 映射见 `PRD.md` §7）：

| 类别 | 接口 | 数 |
|---|---|---|
| A 加载 | A1-A4, A6-A9 | 8 |
| B 解析 | B1-B4 | 4 |
| C 召回 | C1-C6 | 6 |
| D 写入 | D6-D9 | 4 |
| E 自检 | E1 | 1 |
| F 持久化 | F1, F2, F4 | 3 |
| G 调度 | G1, G4 | 2 |

v2 新增接口契约（D1/D2 写入、F3 会话总结、2c 聚类、2d→Layer 1 演化应用、语义召回）见 `ARCHITECTURE.md` §13.5。

## demo

`demo/run.py` 是脚本化的 demo：不接真实 LLM，用 canned response 模拟人格模块产出，依次走完 PRD §8 的 12 步闭环（启动加载 / 快照加载 / 首轮与持续场景自检 / 价值层自检 / 阶段切换 / 召回 / 召回后处理 / 2d 自评 / 2b 字段写入 / 快照+衰减 / plan_subagent 启动），每步打印 `[PASS]` / `[FAIL]`，末尾输出 `Verdict: PASS — v1 关键路径闭环通过`。

### 接入 opencode（真实 LLM）

1. 在工程目录 `uv sync --extra dev`
2. 将 `demo/opencode_config.example.yaml` 合并到你的 opencode 配置（把 `intersoulligence-server` 注册为 stdio MCP server；system_prompt 不写死，由 agent 启动时调用 `persona_get_system_prompt` 获取）
3. 重启 opencode，对话中即可触发人格模块流程

## 项目进度

> 这一段是给未来的 session 用的——恢复现场前先读这一段。详细追踪见 `PRD.md` §15-§18。

### 当前状态（截至 2026-10-01）

- ✅ 设计 + Wiki 文档定稿（三层架构 / 场景边界 / 阶段切换协议 v6 / 遗忘机制 / harness / 28 接口契约）
- ✅ v0.1.0 全部代码实施（persona_runtime 10 模块 + MCP 5 工具 + 210 用例全过，覆盖率 93%）
- ✅ v1.1 debug 三项修复（人格硬控制 / 结构化信号 / 场景量化判定，见 `PRD.md` §16）
- ✅ demo 12/12 PASS（canned response 模式）
- ✅ 文档整合：7 份 → 3 份（README / ARCHITECTURE / PRD）
- ✅ **v2 设计定稿（2026-10-01）**：记忆生命线 + 存储抽象 + persona bundle，见 `ARCHITECTURE.md` §13
- ✅ **v2 M1 存储契约实施（2026-10-01）**：`persona_runtime/storage/`（StorageBackend 契约 + SQLite 参考实现 + FileSnapshotStore）+ 4 处方言移植点消除；230 用例全过、覆盖率 93%、demo 12/12 PASS、MCP 冒烟全过（ARCHITECTURE §13.3 / PRD §15 M1）
- ✅ **v2 M2-M5 实施完成（2026-10-02）**：D1/D2 写侧 + Scribe 提取 + F3 会话总结；语义召回（双路 + C5 联动）；2c 聚类 + 2d→Layer 1 overlay 演化。**258 用例全过、覆盖率 92%、demo 12/12、MCP 冒烟全过、ADR-1 门槛实测达标**（冷启动 52ms / 每轮 p99 4.49ms）。逐阶段问题汇报见 `REPORT-v2.md`
- ⬜ v1 遗留处置：完整 6 阶段 opencode + 真 LLM 端到端验收**延后至产品成型**（策略变更，模板保留于 `PRD.md` §18）；当前验收线（MCP 冒烟 + canned 记忆增长闭环）已于 M5 达成
- ⬜ v2 后续：LLM 提取/聚类挂点接入（Scribe/Librarian 的 `*_fn` 参数）、语义检索性能升级（sqlite-vec）、persona bundle 实施（随 v3 H1/H2）

### 关键决策日志

**不要再踩的坑**——开始改动前务必确认：

1. **接口数是 28，不是 21 也不是 25**：v1 收敛后的枚举为 A8 + B4 + C6 + D4 + E1 + F3 + G2 = **28 个**（砍掉 A5/A10、D1-D5、E2-E5、F3、G2/G3、H1/H2）。老文档里的「21 个」是过时的；「25 个」是 Wiki `接口-v1-按工程分类.md` 汇总表的算术错误（各类保留数之和实为 28，2026-10-01 审查勘误）。一律以该 Wiki 的逐接口枚举为准。
2. **关键路径 12 步不是 9 步**：按 Layer 视角重组（3 + 3 + 4 + 2）。老文档提"9 步闭环"是过时的。
3. **License 是 Apache 2.0 不是 MIT**：原 PRD 写 MIT 已修正。
4. **memory.py 已拆为 memory_recall.py + memory_write.py**：召回与写入分离。
5. **数据库是 SQLite 单实例 + WAL 模式**：不共享多实例，不走 Postgres 路线。
6. **信号走结构化输出**：阶段切换 / 场景自检通过 `emit_stage_transition` / `emit_scenario_check` tool call 发送（v1.1），文本协议标记只是兼容回退，不要往回改。
7. **存储是可插拔接口，不是写死 SQLite**（v2 设计，supersede 决策 5 的 v1 范围）：`StorageBackend` Port/Adapter 契约按 Layer 2 子层划分仓储；SQLite 为参考实现，向量后端（sqlite-vec）为第二实现；后端选型交给用户。「SQLite 单实例不走 Postgres」只对 v1 实施有效。
8. **人格文件存在形式 = persona bundle**（v2 设计，填补 v1 空白）：目录为常态（manifest.json / persona.yaml / overlay.yaml / memory/*.jsonl / content/ markdown 投影 / snapshots/），`.isoul`(zip) 仅为传输态，解压即读即改；manifest 哈希只覆盖 persona.yaml（PROTECTED 层），改记忆不破坏校验，改 Layer 0 走版本升级。
9. **语言策略：Python 编排层不换，计算下沉引擎**（v2 ADR-1）：人格模块是 LLM-bound 非 CPU-bound；设 profiling 门槛（冷启动 <1s、每轮 harness 开销 p99 <50ms），先测量后迁移；语言迁移仅由「脱离 MCP 的嵌入形态」触发。

### 下一步建议

1. v2 实施按 `ARCHITECTURE.md` §13.6 里程碑推进：M1 存储契约 + SQLite 适配重构 → M2 写侧闭环（D1/D2 + Scribe + F3）→ M3 语义召回 → M4 演化应用（2c 聚类 + 2d→Layer 1 overlay）→ M5 MCP 冒烟 + canned 记忆增长验收
2. v3 候选：H1/H2 跨 agent 一致性（配合 bundle 分发「带走 AI 伴侣」）、A5/A10 多人格管理、E2-E5 自检智能化、G2/G3 多 subagent 协作

## License

[Apache 2.0](LICENSE)
