# intersoulligence — PRD（技术执行总纲）

> 本文是**技术执行**的单一整合文档：PRD 主体（需求 / 映射 / 测试 / 验收）+ 功能追踪（§15）+ v1.1 Debug 修复记录（§16）+ 项目变更记录（§17）+ 端到端验收日志（§18）。
> 架构设计（三层模型 / 场景边界 / 阶段切换协议 / 遗忘机制 / harness 机制 / 25 接口契约总览）统一见 `ARCHITECTURE.md`；设计推导原文见外部 Wiki `agent-human/`（core / runtime / research）。

## 1. 需求复述

工程化落地人格模块的 v1 详细化版 **28 个**接口契约（A8 / B4 / C6 / D4 / E1 / F3 / G2 = 28）。

架构设计统一见本仓库 `ARCHITECTURE.md`（整合自 Wiki 五份 core 定稿）；接口契约两视角见 Wiki：`agent-human/runtime/接口-v1-按工程分类.md` / `接口-v2-按Layer分类.md`；设计推导见 Wiki：`agent-human/core/`（Layer0 / Layer0.3 / Layer1.5 / Layer2 / 跨层-harness 五份定稿）与 `agent-human/research/PRD-v1-定稿.md`。

## 2. 目标

构建一个 Python 工程，实现人格模块 **28 个** v1 接口的运行时版本，工程代号 `intersoulligence`。

> 接口列表见 `接口-v1-按工程分类.md`（按工程调用时机分组）或 `接口-v2-按Layer分类.md`（按 Layer 架构分组）。两份文档描述同一套接口，分类视角不同。

## 3. 范围

### 3.1 必须实现（v1）

| 模块 | 内容 |
|---|---|
| SQLite schema | 4 张表（2a/2b/2c/2d）+ 衰减字段（2a status/last_accessed + 2d TTL）+ 索引 |
| persona_runtime | **28 个**接口的 Python 实现 |
| harness | C5 + C6 强制约束点（人格模块自带的伦理边界） |
| MCP server | 暴露 5 个工具（persona_layer0_get / persona_layer1_get / persona_layer2_query / persona_runtime_op / persona_get_system_prompt） |
| demo work agent | opencode 形态，跑通 12 步闭环（按 Layer 视角） |
| 关键路径测试 | 启动 → 加载 → 阶段切换 → plan_subagent → 召回 → 自评 → 持久化 → 衰减 |
| 全接口测试 | 关键路径通过后补全 **28 个**接口的单元测试 |
| 衰减机制 | F4 apply_decay 每 20 轮触发（2a 三阶段衰减 / 2d TTL） |

### 3.2 非目标（v1 不做）

- 跨人格 / 跨 agent 实例共享（不同人格模块记忆不互通）
- Postgres / DuckDB 等替代数据库
- 真实 LLM API 调用（Claude / GPT / 豆包等）—— demo 走 opencode，不接 API key
- v2 阶段加入的接口（A5/A10 个性化路径 / D1-D5 批量写入 / E2-E5 自检调度 / F3 会话总结 / G2-G3 多 subagent 协作 / H1-H2 跨 agent 一致性）

### 3.3 v2 范围（2026-10-01 设计定稿，未实施）

> 设计全文见 `ARCHITECTURE.md` §13（主题定位 / 三条 ADR / 接口契约 / 里程碑）。功能追踪见本文档 §15「v2」段。

**纳入项**：

- 记忆生命线全组接口：D1 append_2a_entry / D2 append_2a_batch / F3 persist_session_summary / 2c 聚类 deep cycle / 2d→Layer 1 演化应用（overlay + A11）/ 语义召回（C1 双路 + C5 联动）
- StorageBackend Port/Adapter 契约 + SQLiteAdapter 参考实现 + sqlite-vec 向量后端 + EmbeddingProvider 接口（**supersede 决策「SQLite 单实例不走 Postgres」的 v1 范围限定**，后端选型交还用户）
- persona bundle 规范（manifest / persona.yaml / overlay.yaml / memory JSONL / content markdown 投影；.isoul 仅传输态）
- 验收：MCP server 冒烟 + canned 记忆增长闭环（E2E 策略变更见 §18）

**不纳入项**：H1/H2、A5/A10、E2-E5、G2/G3 顺延 v3；关系型第二后端仅保证接口就绪不交付实施；完整 6 阶段真 LLM 验收延后至产品成型。

## 4. 工程栈

| 项 | 选择 | 备注 |
|---|---|---|
| 项目名 | intersoulligence | — |
| 语言 | Python | — |
| 包管理 | uv | pyproject.toml |
| 数据库 | SQLite | 单文件、单实例 |
| MCP 框架 | mcp（官方 Python SDK） | — |
| 测试框架 | pytest | — |
| demo agent | opencode | 运行时由用户手动配置 |
| License | **Apache 2.0** | — |

## 5. 工程目录结构

```
intersoulligence/
├── PRD.md                                  # 本文档（技术执行总纲，含 §15-§18 追踪 / 修复 / 变更 / 验收）
├── ARCHITECTURE.md                         # 架构设计总纲
├── README.md                               # 项目说明 + demo 使用
├── LICENSE                                 # Apache 2.0 License
├── .gitignore
├── persona_runtime/                        # 人格模块核心代码
│   ├── __init__.py
│   ├── config.py                           # 配置加载（数据目录 / schema 路径）
│   ├── db.py                               # SQLite 连接 + 初始化 schema
│   ├── schema_loader.py                    # A1-A4, A6-A9
│   ├── signal_parser.py                    # B1-B4
│   ├── memory_recall.py                     # C1-C6（召回 + 后处理）
│   ├── memory_write.py                      # D6-D9（写入 + 校验 + 2b 字段管理）
│   ├── self_check.py                       # E1
│   ├── persistence.py                      # F1, F2
│   ├── scheduler.py                        # G1, G4
│   └── harness.py                          # C5+C6 强制约束点
├── mcp_server/                             # MCP server
│   ├── __init__.py
│   ├── server.py                           # MCP 入口
│   └── tools/
│       ├── __init__.py
│       ├── layer0.py                       # persona_layer0_get
│       ├── layer1.py                       # persona_layer1_get
│       ├── layer2.py                       # persona_layer2_query
│       ├── runtime.py                      # persona_runtime_op
│       └── system_prompt.py                # persona_get_system_prompt（v1.1）
├── data/
│   └── persona_schema.yaml                 # Layer 0/1 声明（YAML）
├── tests/                                  # 单元测试
│   ├── conftest.py                         # pytest fixture
│   ├── test_schema_loader.py
│   ├── test_signal_parser.py
│   ├── test_memory_recall.py                # C1-C6
│   ├── test_memory_write.py                 # D6-D9
│   ├── test_self_check.py
│   ├── test_persistence.py
│   ├── test_scheduler.py
│   ├── test_harness.py                     # C5+C6 约束测试
│   ├── test_critical_path.py               # 12 步闭环
│   └── test_mcp_server.py                  # MCP 5 工具
└── demo/                                   # demo work agent
    ├── run.py                              # demo 入口
    └── opencode_config.example.yaml        # opencode 配置示例
```

> 原 `docs/`（FEATURES / CHANGELOG / Debug_v1_1 / TEST_LOG）与 `demo/README.md` 已分别并入本文档 §15-§18 与 README，2026-10-01 文档整合时移除。

## 6. Mermaid 流程图

启动闭环 / 每轮响应闭环 / 阶段切换闭环三个运行时序列图统一收录于 `ARCHITECTURE.md` §10.3（2026-10-01 文档整合时迁移，避免两处维护）。

## 7. 28 个接口 → SQL schema → MCP 工具映射

### 7.1 SQLite schema（4 张表 + 衰减字段）

> 基于架构文档 §4 收敛。2a/2b/2c/2d 各一张表，2a 加衰减状态字段，2d 加 TTL 衰减支持。

```sql
-- Layer 2a: 互动事实（高频演化 + 三阶段衰减）
CREATE TABLE interaction_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT,                      -- 可能为 null（content_wiped 后）
    type TEXT NOT NULL,                -- observation / reflection / preference / event / state
    source_conv TEXT,                  -- 来源会话 ID
    timestamp TEXT NOT NULL,           -- ISO datetime（事件发生时间）
    entities TEXT NOT NULL DEFAULT '[]',  -- JSON 数组
    channel TEXT NOT NULL DEFAULT 'direct',  -- direct / indirect / single
    status TEXT NOT NULL DEFAULT 'active',   -- active / cooling / vector_deleted / content_wiped
    last_accessed TEXT NOT NULL DEFAULT (datetime('now')),  -- 衰减计时器
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Layer 2b: 实体画像（字段级管理 + 三字段分流）
CREATE TABLE entity_profile (
    entity TEXT PRIMARY KEY,           -- 实体名（用户、产品、项目等）
    facts TEXT NOT NULL DEFAULT '[]',  -- JSON: [{content, confidence}]  -- mode: overwrite
    current_status TEXT NOT NULL DEFAULT '[]',  -- JSON: [{content, timestamp}]  -- mode: covering_update
    judgment TEXT NOT NULL DEFAULT '[]',  -- JSON: [{content, timestamp}]  -- mode: append
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Layer 2c: 长期模式（confidence 只增不减）
CREATE TABLE long_term_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,      -- 模式描述
    confidence REAL NOT NULL DEFAULT 0.0,  -- 0-1，只增不减
    first_observed TEXT NOT NULL,      -- ISO datetime
    last_accessed TEXT NOT NULL,       -- ISO datetime（freshness 独立）
    evidence_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Layer 2d: 自我更新账本（人格自评 + TTL 衰减）
CREATE TABLE self_growth_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    change TEXT NOT NULL,              -- 变化内容
    reason TEXT NOT NULL,              -- 因何故
    affected_layer TEXT NOT NULL,      -- Layer 1 | Layer 2b
    timestamp TEXT NOT NULL,           -- ISO datetime
    reversible INTEGER NOT NULL DEFAULT 1,  -- 0/1
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 索引
CREATE INDEX idx_interaction_timestamp ON interaction_memory(timestamp);
CREATE INDEX idx_interaction_channel ON interaction_memory(channel);
CREATE INDEX idx_interaction_status ON interaction_memory(status);
CREATE INDEX idx_interaction_last_accessed ON interaction_memory(last_accessed);
CREATE INDEX idx_patterns_confidence ON long_term_patterns(confidence);
CREATE INDEX idx_ledger_timestamp ON self_growth_ledger(timestamp);
```

### 7.2 接口 → schema → MCP 工具映射（28 个接口）

| 接口 | SQL 表 | 字段 / 操作 | MCP 工具 | operation |
|---|---|---|---|---|
| **A1** load_persona_schema | — | 文件读取 | persona_layer0_get | schema |
| **A2** get_identity_anchors | — | 文件读取 | persona_layer0_get | anchors |
| **A3** get_value_kernel | — | 文件读取 | persona_layer0_get | value_kernel |
| **A4** get_available_scenarios | — | 文件读取 | persona_layer0_get | scenarios |
| **A6** get_self_check_policy | — | 文件读取 | persona_layer0_get | self_check_policy |
| **A7** get_stage_signal_prompt | — | 文件读取 | persona_layer1_get | stage_signal_prompt |
| **A8** get_initial_scenario_check_prompt | — | 文件读取 | persona_layer0_get | initial_scenario_check |
| **A9** get_ongoing_scenario_check_prompt | — | 文件读取 | persona_layer1_get | ongoing_scenario_check |
| **B1** parse_stage_transition | — | 字符串解析 | persona_runtime_op | parse_stage_transition |
| **B2** parse_scenario_check | — | 字符串解析 | persona_runtime_op | parse_scenario_check |
| **B3** validate_stage_transition | interaction_memory | 查询近 N 轮违规率 | persona_runtime_op | validate_stage_transition |
| **B4** validate_scenario_check | — | 白名单校验 | persona_runtime_op | validate_scenario_check |
| **C1** recall_2a | interaction_memory | SELECT（更新 last_accessed） | persona_layer2_query | recall_2a |
| **C2** recall_2b | entity_profile | SELECT | persona_layer2_query | recall_2b |
| **C3** recall_2c | long_term_patterns | SELECT（更新 last_accessed） | persona_layer2_query | recall_2c |
| **C4** recall_2d | self_growth_ledger | SELECT | persona_layer2_query | recall_2d |
| **C5** apply_recall_permission | interaction_memory | channel 字段判定 | persona_runtime_op | apply_recall_permission |
| **C6** rewrite_voice | — | 语态改写 | persona_runtime_op | rewrite_voice |
| **D6** append_2d_entry | self_growth_ledger | INSERT | persona_layer2_query | append_2d |
| **D7** maybe_2d_trigger | interaction_memory, self_growth_ledger | SELECT 最近 N 条 | persona_layer2_query | maybe_2d_trigger |
| **D8** validate_2d_entry | — | 伦理约束检测 | persona_runtime_op | validate_2d_entry |
| **D9** write_2b_entry | entity_profile | UPDATE（按字段分流） | persona_layer2_query | write_2b |
| **E1** value_self_check | — | 价值层校验 | persona_runtime_op | value_self_check |
| **F1** take_snapshot | 多表聚合 | 计算 violation_rate | persona_runtime_op | take_snapshot |
| **F2** load_latest_snapshot | 文件系统 | 读取最近快照 | persona_runtime_op | load_latest_snapshot |
| **F4** apply_decay | interaction_memory, self_growth_ledger | UPDATE / DELETE | persona_runtime_op | apply_decay |
| **G1** spawn_plan_subagent | — | 进程管理 | persona_runtime_op | spawn_plan_subagent |
| **G4** inject_plan_subagent_first_switch_rule | — | 规则注入 | persona_runtime_op | inject_plan_subagent_rule |

### 7.3 MCP 工具签名

#### persona_layer0_get

```yaml
输入:
  field: enum[schema, anchors, value_kernel, scenarios, self_check_policy, initial_scenario_check]
输出:
  data: <对应字段的完整数据>
错误:
  - field 不识别 → 拒绝
  - 数据未初始化 → 拒绝
```

#### persona_layer1_get

```yaml
输入:
  field: enum[stage_signal_prompt, ongoing_scenario_check]
  current_scenario: string  # 仅 ongoing_scenario_check 必填
输出:
  data: <对应字段的 prompt 模板>
错误:
  - field 缺失 current_scenario → 拒绝
  - 当前场景不在白名单 → 回退到首轮
```

#### persona_layer2_query

```yaml
输入:
  operation: enum[
    recall_2a, recall_2b, recall_2c, recall_2d,
    append_2d, maybe_2d_trigger,
    write_2b
  ]
  # 各 operation 不同的 params
输出:
  data: <查询/写入结果>
错误:
  - operation 不识别 → 拒绝
  - 写入触发伦理违规 → 拒绝 + 冲突条款
```

#### persona_runtime_op

```yaml
输入:
  operation: enum[
    parse_stage_transition,
    parse_scenario_check,
    validate_stage_transition,
    validate_scenario_check,
    apply_recall_permission,
    rewrite_voice,
    validate_2d_entry,
    value_self_check,
    take_snapshot,
    load_latest_snapshot,
    apply_decay,
    spawn_plan_subagent,
    inject_plan_subagent_rule,
    emit_stage_transition,
    emit_scenario_check
  ]
  # 各 operation 不同的 params
输出:
  data: <操作结果>
错误:
  - operation 不识别 → 拒绝
  - 参数缺失 → 拒绝 + 缺失字段名
```

> v1.1 补充：`emit_stage_transition` / `emit_scenario_check` 为结构化输出 operation（§16 问题 2）——LLM 通过 tool call 发送阶段切换 / 场景自检信号，不走文本通道；MCP server 端经 B3/B4 校验后同步 live harness 状态。

## 8. 关键路径测试（12 步闭环，按 Layer 视角）

**测试文件**：`tests/test_critical_path.py`

> v1 收敛到 28 个接口后，关键路径闭环从 9 步扩到 12 步（按 Layer 视角）。完整闭环见 `接口-v2-按Layer分类.md` §"v1 验收标准"。

### Layer 0 闭环（3 步）

| 步骤 | 验证内容 |
|---|---|
| 1. 启动加载 | A1 / A2 / A3 / A4 / A6 全部返回正确数据 |
| 2. 快照加载 | F2 加载最近快照（无则 fresh_start） |
| 3. 首轮场景自检 | A8 注入 prompt + B2 解析初始场景 |

### Layer 1 闭环（3 步）

| 步骤 | 验证内容 |
|---|---|
| 4. 持续场景自检 | A9 注入 prompt + B2 解析 stay/switch_to |
| 5. 价值层自检 | E1 检测违规 + 行动决策 |
| 6. 阶段切换 | B1 解析 + B3 校验 + G1 启动 subagent |

### Layer 2 闭环（4 步）

| 步骤 | 验证内容 |
|---|---|
| 7. 召回原始数据 | C1 / C2 / C3 / C4 召回（按层分流） |
| 8. 召回后处理 | C5 应用 permission + C6 语态改写 → 注入 prompt |
| 9. Layer 2d 自评 | D7 触发 + D8 校验 + D6 写入 |
| 10. 2b 字段写入 | D9 write_2b_entry（按字段分流：facts / current_status / judgment） |

### 跨层辅佐闭环（2 步）

| 步骤 | 验证内容 |
|---|---|
| 11. 快照 + 衰减 | F1 每 20 轮落盘 + F4 apply_decay 跑衰减（2a 三阶段 / 2d TTL） |
| 12. plan_subagent 启动 | G1 启动 + G4 注入 first switch rule（首次切换时） |

**判定**：12 步全部通过 = 关键路径 PASS，可以进入全接口测试阶段。

## 9. 全接口测试（28 个）

**测试文件分布**：

| 测试文件 | 覆盖接口 |
|---|---|
| `tests/test_schema_loader.py` | A1, A2, A3, A4, A6, A7, A8, A9（8 个） |
| `tests/test_signal_parser.py` | B1, B2, B3, B4（4 个） |
| `tests/test_memory_recall.py` | C1, C2, C3, C4, C5, C6（6 个，召回 + 后处理） |
| `tests/test_memory_write.py` | D6, D7, D8, D9（4 个，写入 + 校验 + 2b 字段管理） |
| `tests/test_self_check.py` | E1（1 个） |
| `tests/test_persistence.py` | F1, F2, F4（3 个，含衰减） |
| `tests/test_scheduler.py` | G1, G4（2 个） |
| **合计** | **28 个接口** |

## 10. 验收标准

### 10.1 关键路径验收

- [x] `tests/test_critical_path.py` 12 步全部通过（按 Layer 视角）（实测 12/12，2026-08-26）
- [x] Layer 0 闭环：F2 加载快照 + A8 首轮场景自检
- [x] Layer 1 闭环：A9 持续场景自检 + E1 价值层自检 + B1/B3 阶段切换
- [x] Layer 2 召回路径：C1-C4 召回 + C5/C6 后处理
- [x] Layer 2 写入路径：D7/D8/D6 自评路径 + D9 2b 字段写入
- [x] 持久化 + 衰减路径：F1 落盘 + F4 apply_decay（2a 三阶段 / 2d TTL）
- [x] plan_subagent 启动：G1 启动 + G4 注入 first switch rule

### 10.2 全接口验收

- [x] `tests/` 下测试文件全部通过（实际 10 个文件、129 用例全过）
- [x] **28 个**接口 100% 覆盖（每个接口至少 1 个测试用例）
- [x] pytest 覆盖率 ≥ 80%（核心模块）（全项目实测 92%：persona_runtime 82%~98%，mcp_server 88%~100%）
- [x] harness.py 的 C5+C6 约束至少 3 个测试用例（cite / cautious / associate-only）（恰 3 个）
- [x] F4 apply_decay 至少 4 个测试用例（2a cooling / vector_deleted / content_wiped / 2d TTL）（7 个）

### 10.3 demo 验收

- [x] `demo/run.py` 在 opencode 环境下能跑通 12 步闭环（本地 canned response 模式实测 12/12 PASS）
- [x] opencode 配置示例文件 `demo/opencode_config.example.yaml` 可用（YAML 解析通过）
- [ ] 用户手动配置 opencode 环境后，demo 能输出人格模块的预期响应（**用户侧待办**）

## 11. 文件级修改计划（依赖顺序）

依赖顺序：1 → 2 → ... → 27

| 序号 | 文件 | 依赖 | 改动内容 |
|---|---|---|---|
| 1 | `pyproject.toml` | — | uv 项目配置 + 依赖 |
| 2 | `.gitignore` | — | Python / SQLite 忽略规则 |
| 3 | `LICENSE` | — | Apache 2.0 License 文本 |
| 4 | `README.md` | 1 | 项目说明 |
| 5 | `docs/FEATURES.md` | 1 | 功能追踪初始条目 |
| 6 | `docs/CHANGELOG.md` | 1 | 变更记录初始 |
| 7 | `data/persona_schema.yaml` | — | Layer 0/1 声明（YAML） |
| 8 | `persona_runtime/config.py` | 1 | 配置加载 |
| 9 | `persona_runtime/db.py` | 7, 8 | SQLite 连接 + 初始化 schema |
| 10 | `persona_runtime/schema_loader.py` | 7, 8 | A1-A4, A6-A9 |
| 11 | `persona_runtime/signal_parser.py` | 10 | B1, B2, B3, B4 |
| 12 | `persona_runtime/memory_recall.py` | 9, 10 | C1, C2, C3, C4, C5, C6（召回 + 后处理） |
| 13 | `persona_runtime/memory_write.py` | 9, 10 | D6, D7, D8, D9（写入 + 校验 + 2b 字段管理） |
| 14 | `persona_runtime/self_check.py` | 10 | E1 |
| 15 | `persona_runtime/persistence.py` | 9 | F1, F2, F4（含衰减） |
| 16 | `persona_runtime/scheduler.py` | 10 | G1, G4 |
| 17 | `persona_runtime/harness.py` | 11, 12, 13, 14, 15, 16 | C5+C6 强制约束点 + 主循环 |
| 18 | `persona_runtime/__init__.py` | 8-17 | 包导出 |
| 19 | `mcp_server/tools/layer0.py` | 10 | persona_layer0_get |
| 20 | `mcp_server/tools/layer1.py` | 10 | persona_layer1_get |
| 21 | `mcp_server/tools/layer2.py` | 12, 13 | persona_layer2_query |
| 22 | `mcp_server/tools/runtime.py` | 11, 12, 13, 14, 15, 16 | persona_runtime_op |
| 23 | `mcp_server/server.py` | 19-22 | MCP server 入口 |
| 24 | `mcp_server/__init__.py` | 23 | 包导出 |
| 25 | `tests/conftest.py` | 9 | pytest fixture |
| 26 | `tests/test_critical_path.py` | 25 | 12 步闭环测试 |
| 27 | `tests/test_*.py`（其余 6 个） | 25 | 全接口测试 |
| 28 | `demo/run.py` + `demo/opencode_config.example.yaml` + `demo/README.md` | 17, 23 | demo 入口 + opencode 配置 |

**说明**：
- 序号 1-6：项目骨架（无依赖）
- 序号 7：数据声明（独立）
- 序号 8-17：persona_runtime（核心代码）
- 序号 18-23：MCP server
- 序号 24-26：测试
- 序号 27：demo

> 注：本表为 v1 实施时的**历史计划**，保留原文不动。表中 `docs/FEATURES.md`、`docs/CHANGELOG.md`、`demo/README.md` 已于 2026-10-01 文档整合时分别并入本文档 §15 / §17 与 README；`ARCHITECTURE.md` 为整合时新增的架构总纲。

## 12. 风险与回退

| 风险 | 回退策略 |
|---|---|
| MCP 工具签名调试复杂 | 先做 9 步闭环跑通 + 测试通过，再接 MCP |
| opencode 运行时配置遇到问题 | 提供 example config + README 说明 |
| SQLite 并发问题（人格模块 + work agent 同时写） | v1 用 WAL 模式 + 串行化写入 |
| 价值层自检误判 | E1 违规时只 regenerate 1 次，避免无限循环 |
| 长窗口降档逻辑复杂 | v1 用简化的滑动窗口（最近 100 轮） |

## 13. 影响范围

⚡ 影响范围：
- **新增工程**：`intersoulligence/`（28 个文件，含拆分后的 memory_recall / memory_write）
- **数据契约**：`data/persona_schema.yaml` 是 Layer 0/1 的事实声明，未来人格模块调整需修改此文件
- **接口契约**：28 个接口的输入输出与 Wiki `项目/agent-human/接口-v1-按工程分类.md` 一致，修改时需要双向同步
- **数据库**：SQLite 单文件路径在 `data/persona.db`（默认），含 2a 衰减字段（status / last_accessed）+ 2d TTL 字段
- **衰减机制**：F4 apply_decay 每 20 轮触发，2a 三阶段（cooling/vector_deleted/content_wiped）+ 2d TTL（≥180 天）
- **测试基线**：12 步关键路径通过是进入全接口测试的前提

## 14. 修订记录

- 2026-08-14：初版 PRD。完成 21 个接口的工程化映射、MCP 工具签名、9 步闭环验收、文件级修改计划。
- 2026-08-14 22:30：v2 全量对齐。**关键变更**：接口 21 → **25 个**（补回 C1-C4 召回 + 新增 D9 2b 字段管理 + 新增 F4 衰减机制）；关键路径 9 步 → **12 步**（按 Layer 视角重组）；第 11 章文件级修改计划拆分 memory.py → memory_recall.py + memory_write.py；SQL schema 加 2a 衰减字段（status / last_accessed）+ 索引；MCP 工具 operation 列表扩到 7 + 13 个。**对齐目标**：与 Wiki `接口-v1-按工程分类.md` + `接口-v2-按Layer分类.md` + `Layer2-遗忘机制-定稿.md` 保持一致。
- 2026-08-14 22:30：所有 Wiki 引用同步到新文件名（Layer0-架构设计-定稿 / Layer0.3-场景价值变体边界-定稿 / Layer1.5-阶段切换信号-定稿 / Layer2-遗忘机制-定稿 / 跨层-harness-定稿 / 接口-v1-按工程分类 / 接口-v2-按Layer分类 / 对照-四份材料横评）。
- 2026-08-26 03:45：License 由 MIT 改为 **Apache 2.0**（第 4 章工程栈 / 第 5 章目录结构 / 第 11 章文件级修改计划 三处同步修正）。
- 2026-08-26 17:30：验收核销与结构图同步。§5 目录结构同步 memory 拆分（memory_recall / memory_write）与 test_memory 拆分；§10 验收标准按实测核销（129 用例全过 / persona_runtime 核心覆盖率 82%~98% / demo 12/12 PASS）；代码托管于 GitHub `GreyzAchilles/Intersoulligence`。遗留：mcp_server 单测补齐、用户侧 opencode 环境实测。
- 2026-08-26 18:10：补齐 mcp_server 单元测试（`tests/test_mcp_server.py` 39 用例），TOTAL 覆盖率 78% → **92%**。修复两个由测试暴露的缺陷：① mcp 2.x 移除 FastMCP 导致 server 入口 RuntimeError → `server.py` 改为 MCPServer（2.x）/ FastMCP（1.x）双版本导入兼容；② SQLite 连接开启 `check_same_thread=False`（MCP 工具处理器运行于任意工作线程，写入串行化仍由 PRD §12 WAL + 单实例保证）。遗留：用户侧 opencode 环境实测。
- 2026-08-27：v1.1 debug 三项修复（详见 §16）：① 问题 1 人格硬控制——`Harness.build_system_prompt()` prompt 强制组装器 + 第 5 个 MCP 工具 `persona_get_system_prompt`；② 问题 2 结构化输出——`persona_runtime_op` 扩到 15 个 operation（新增 emit_stage_transition / emit_scenario_check），B1/B2 支持 dict 输入，`process_turn` 收 tool_calls，server 端同步 live harness；③ 问题 5 场景判定量化——scenario 加 discriminator，A8/A9 注入判定清单。测试 205 用例全过，覆盖率 93%。
- 2026-10-01：**文档整合**。架构设计知识收敛至 `ARCHITECTURE.md`；本文档吸收原 `docs/FEATURES.md`（→ §15）、`docs/Debug_v1_1.md`（→ §16）、`docs/CHANGELOG.md`（→ §17）、`docs/TEST_LOG.md`（→ §18）；原 §6 流程图迁移至 ARCHITECTURE §10.3。文档总数 7 → 3（README / ARCHITECTURE / PRD）。
- 2026-10-01：**接口计数勘误 25 → 28**。Wiki `接口-v1-按工程分类.md` 汇总表「42 → 25」为算术错误——其各类保留数 8 + 4 + 6 + 4 + 1 + 3 + 2 + 0 = 28，与逐接口枚举一致；§1 公式「B8 / C10」笔误同步修正为「B4 / C6」。历史条目中的「25 个」保留原文不改，仅改活文档。
- 2026-10-01：**v2 设计定稿**（`ARCHITECTURE.md` §13 新增，本文档 §3.3 / §15 / §18 同步）。五项决策：① v2 主题 = 记忆生命线（写侧缺口：2a/2c 零运行时写入、2d 无应用），H1/H2 等顺延 v3；② ADR-1 语言策略——Python 编排层不换，计算下沉引擎，profiling 门槛先行；③ ADR-2 存储抽象 StorageBackend 可插拔（**supersede v1「SQLite 单实例不走 Postgres」**），SQLite 参考实现 + sqlite-vec 向量后端；④ ADR-3 persona bundle 规范（四角色格式拆分、目录常态 + .isoul 传输态、manifest Layer 0 哈希、DB 为源 markdown 为投影）；⑤ **E2E 策略变更**——完整 6 阶段真 LLM 验收延后至产品成型，当前验收线 = MCP 冒烟 + canned 记忆增长闭环。v1.1 搁置问题 4（2b vs 2d 边界）随 F3 契约定稿，其余分级处置（§13.6）。

## 15. 功能追踪（原 docs/FEATURES.md）

> v1 工程化落地的功能状态追踪。原 `docs/FEATURES.md`，2026-10-01 并入。

### v1.0 — 初始工程化落地

#### Layer 0 / 1 加载（A 类接口）
- [x] A1 `load_persona_schema()` — 读取 schema 文件返回结构化声明
- [x] A2 `get_identity_anchors()` — 返回场景对应的身份锚点
- [x] A3 `get_value_kernel()` — 返回价值内核（beliefs / refusals / judgment_principles）
- [x] A4 `get_available_scenarios()` — 返回可用场景白名单
- [x] A6 `get_self_check_policy()` — 返回自检机制归属（harness_managed）
- [x] A7 `get_stage_signal_prompt()` — 返回阶段切换信号 prompt 模板
- [x] A8 `get_initial_scenario_check_prompt()` — 返回首轮场景自检 prompt
- [x] A9 `get_ongoing_scenario_check_prompt()` — 返回持续场景自检 prompt

#### Layer 1 信号解析（B 类接口）
- [x] B1 `parse_stage_transition()` — 解析阶段切换信号（emit tool call / 文本标记双输入）
- [x] B2 `parse_scenario_check()` — 解析场景自检信号
- [x] B3 `validate_stage_transition()` — 长窗口违规率降档校验
- [x] B4 `validate_scenario_check()` — 场景白名单校验

#### Layer 2 召回（C 类接口）
- [x] C1 `recall_2a()` — 互动事实召回（更新 last_accessed）
- [x] C2 `recall_2b()` — 实体画像召回
- [x] C3 `recall_2c()` — 长期模式召回（更新 last_accessed）
- [x] C4 `recall_2d()` — 自我更新账本召回
- [x] C5 `apply_recall_permission()` — 三档 recall permission 标记
- [x] C6 `rewrite_voice()` — 检索后语态改写

#### Layer 2 写入（D 类接口）
- [x] D6 `append_2d_entry()` — 自我更新账本写入
- [x] D7 `maybe_2d_trigger()` — 2d 触发检测
- [x] D8 `validate_2d_entry()` — 2d 条目伦理校验
- [x] D9 `write_2b_entry()` — 2b 字段级写入（facts / current_status / judgment 分流）

#### 自检（E 类接口）
- [x] E1 `value_self_check()` — 价值层自检（规则化）

#### 持久化（F 类接口）
- [x] F1 `take_snapshot()` — 每 20 轮落盘快照
- [x] F2 `load_latest_snapshot()` — 启动时加载最近快照
- [x] F4 `apply_decay()` — 2a 三阶段衰减 + 2d TTL 衰减

#### 调度（G 类接口）
- [x] G1 `spawn_plan_subagent()` — 启动 plan subagent + 注入规则
- [x] G4 `inject_plan_subagent_first_switch_rule()` — 首次切换注入 first switch rule

#### harness
- [x] C5 + C6 强制约束点
- [x] 主循环协调器（每轮响应闭环）

#### MCP server
- [x] `persona_layer0_get` 工具
- [x] `persona_layer1_get` 工具
- [x] `persona_layer2_query` 工具
- [x] `persona_runtime_op` 工具
- [x] `persona_get_system_prompt` 工具（v1.1）

#### v1.1 debug 修复（详见 §16）
- [x] 问题 1 — `Harness.build_system_prompt()` prompt 强制组装器 + MCP 第 5 工具下发
- [x] 问题 2 — 结构化输出：`emit_stage_transition` / `emit_scenario_check` + B1/B2 dict 输入 + `process_turn(tool_calls)` + server 端 live harness 状态同步
- [x] 问题 5 — 场景 `discriminator` 判定特征 + A8/A9 prompt 注入

#### 数据
- [x] SQLite schema（4 张表 + 衰减字段 + 索引）
- [x] `persona_schema.yaml` — Layer 0/1 声明（含场景 discriminator 判定特征）

#### 测试
- [x] 12 步关键路径闭环
- [x] 28 个接口全覆盖
- [x] harness C5/C6 约束 3 用例
- [x] F4 衰减 4 用例
- [x] 210 用例全过（168 基线 + 42 v1.1 新增），覆盖率 93%
- [ ] opencode 端到端实测（v1 验收唯一未完成项）— 见 §18
- [ ] v1.1 重跑 6 阶段对话验收 — 见 §16 / §18

#### demo
- [x] `demo/run.py` — 12 步闭环
- [x] opencode 配置示例

### v2 — 设计定稿（2026-10-01，未实施）

> 设计全文见 `ARCHITECTURE.md` §13；实施范围见本文档 §3.3；里程碑 M1-M5 与验收线见 §13.6。以下条目在对应里程碑完成时勾选。

#### 设计与决策
- [x] v2 主题定稿：记忆生命线（H1/H2、A5/A10、E2-E5、G2/G3 顺延 v3）
- [x] ADR-1 语言策略（Python 编排层 + profiling 门槛）
- [x] ADR-2 存储抽象 StorageBackend（supersede v1「SQLite 单实例」的 v1 范围限定）
- [x] ADR-3 persona bundle 规范（四角色格式 + manifest Layer 0 哈希 + JSONL 交换 + markdown 投影）
- [x] E2E 策略变更（完整真 LLM 验收延后至产品成型）

#### M1 存储契约
- [ ] StorageBackend Port/Adapter 契约（InteractionRepo / EntityRepo / PatternRepo / LedgerRepo / SnapshotStore）
- [ ] SQLiteAdapter 重构（约 15 个生产函数去 conn 化 + 4 处方言移植点消除）
- [ ] 测试迁移（约 25 个改动点：conftest 4 个 INSERT helper + 13 处 SELECT 断言 + FlakyConn 重写）
- [ ] EmbeddingProvider 接口定义

#### M2 写侧闭环
- [ ] D1 `append_2a_entry` + D2 `append_2a_batch`
- [ ] Scribe 对话→2a 提取（规则提取起步）
- [ ] F3 `persist_session_summary`（2a episode + 2b 经 D9 + markdown 投影；随此定稿 2b vs 2d 边界）

#### M3 语义召回
- [ ] sqlite-vec 向量后端 + `find_similar`
- [ ] C1 双路召回 + C5 三档联动 + F4 向量删除对齐

#### M4 演化应用
- [ ] 2c 聚类 deep cycle（Librarian，confidence 只增 / evidence 累计）
- [ ] overlay.yaml 覆盖层 + A11 `load_persona_overlay` + Layer 0 拒改校验

#### M5 验收
- [ ] MCP server 冒烟（启动 + 5 工具全部可调用）
- [ ] canned 记忆增长闭环（对话 → 2a → 召回 → F3 → 2b/投影 → 2c/overlay）

## 16. v1.1 Debug 修复记录（原 docs/Debug_v1_1.md）

> v1 端到端验收（§18）暴露问题的修复规划。修复目标：让人格模块对 LLM 形成「硬控制」，消除沉浸感破坏，量化场景判定。原 `docs/Debug_v1_1.md`，2026-10-01 并入。

### 现在修（已全部完成）

#### 问题 1：人格模块对 LLM 是「软约束」

**修复方向**：harness 提升为 prompt 强制组装器——人格声明自动注入 system_prompt，LLM 看到的永远是「被封装好的人格」。

**影响文件**：

| 文件 | 改动 |
|---|---|
| `persona_runtime/harness.py` | 新增 `build_system_prompt(config)` 方法，从 yaml 拼 Layer 0/1 + 工具说明 |
| `mcp_server/server.py` | MCP server 启动时返回 `system_prompt` 给 work agent |
| `demo/opencode_config.example.yaml` | 改为引用人格模块返回的 system_prompt，不再写死 |
| `tests/test_harness.py` | 新增 build_system_prompt 单元测试 |

**验收标准**：

- [x] `Harness.build_system_prompt()` 返回的 prompt 含 Layer 0/1 全部关键内容（核心身份 / 价值内核 / 场景变体 / 表达规范）
- [x] opencode 配置中的 system_prompt 字段被移除或留空，由人格模块注入（`demo/opencode_config.example.yaml` 改为启动时调用 `persona_get_system_prompt`）
- [x] 单测覆盖：build_system_prompt 包含 yaml 字段校验

#### 问题 2：协议标记破坏沉浸感

**修复方向（主方案）**：方向 C — LLM 通过**结构化输出**发标记，不走文本通道。

**实施方案**：

- 利用 MCP stdio 协议的 tool call 机制，让 LLM 通过 `persona_runtime_op` 工具调用发送 `[STAGE_TRANSITION]` / `[SCENARIO_CHECK]` 标记，而不是写在响应文本里
- LLM 响应文本 = 干净的对话内容（无标记）
- harness 从 tool call 参数里解析标记（B1/B2 改读 tool call 而非字符串）

**影响文件**：

| 文件 | 改动 |
|---|---|
| `mcp_server/tools/runtime.py` | 新增 `emit_stage_transition(to, confidence)` 和 `emit_scenario_check(mode, target)` 两个 sub-operation |
| `persona_runtime/signal_parser.py` | B1/B2 接收 tool call 参数 dict 而非字符串 |
| `persona_runtime/harness.py` | process_turn 接收 tool_calls 参数 |
| `tests/test_signal_parser.py` | 新增 tool call 输入的解析用例 |
| `tests/test_harness.py` | 新增 tool call 流的主闭环用例 |

**验收标准**：

- [x] LLM 调用 `persona_runtime_op(operation="emit_stage_transition", params={...})` 等价于文本里的 `[STAGE_TRANSITION]` 标记
- [x] LLM 响应文本里不包含 `[STAGE_TRANSITION]` / `[SCENARIO_CHECK]` / `[RESPONSE]` 字面量（响应文本保持干净，标记走 tool call 通道）
- [x] B1/B2 解析 tool call 参数与解析字符串结果一致（兼容回退）
- [x] 单测覆盖：tool call 解析 + 主闭环集成

> 实施补充：emit_* 在 MCP server 端经 B3/B4 校验后同步 live harness 的 current_stage / current_scenario，结构化信号在真实链路上生效。

**备选方案（方向 B）**：harness 在响应里删除标记再返回给用户——LLM 继续发协议标记（维持解析机制），但用户看到的响应是干净的。实施成本低，但 prompt 训练不可靠时容易误删内容。

#### 问题 5：场景切换灵敏度量化

**修复方向**：在 `persona_schema.yaml` 给每个场景加**判定特征清单**，harness 的 A9 自检 prompt 注入判定清单，让 LLM 有量化标准。

**影响文件**：

| 文件 | 改动 |
|---|---|
| `data/persona_schema.yaml` | 每个 scenario 加 `discriminator` 字段（关键词清单 + 场景触发条件） |
| `persona_runtime/schema_loader.py` | A4 返回场景时含 discriminator |
| `tests/test_schema_loader.py` | 新增 discriminator 加载用例 |
| `tests/test_self_check.py` | 新增基于 discriminator 的自检用例 |

**验收标准**：

- [x] `persona_schema.yaml` 每个 scenario 含 discriminator 字段
- [x] A4 返回场景 dict 含 discriminator
- [x] A9 prompt 注入 discriminator 内容（`ongoing["discriminator"]` + `scenario_discriminators`；A8 首轮 prompt 同步注入）
- [x] 单测覆盖：discriminator 加载 + 自检 prompt 含 discriminator

### 暂时搁置

- 问题 3（阶段⑥ E1 未跑）
- 问题 4（2b vs 2d 边界）
- 问题 6（反推时间戳）
- 问题 7（评分口径）
- 问题 8（测试 agent 自评偏差）
- 问题 9（模型 ID 真实性）
- 问题 10（system_prompt 与 yaml 重复）
- 问题 11（v1 测试覆盖盲区）

### 修复顺序

1. **问题 1 + 问题 5**：harness 提升为 prompt 组装器，yaml 加判定特征——同时改 yaml 和 harness.py
2. **问题 2**：结构化输出迁移——改 runtime.py / signal_parser.py / harness.py
3. **测试**：每个修复都先加单测再实施
4. **验证**：本地 dev run 通过后，更新 §18 重跑 6 阶段对话

### 修复变更记录

| 日期 | 变更 |
|---|---|
| 2026-08-27 | 初始规划（v1 验收暴露问题的修复方向） |
| 2026-08-27 | 三项修复实施完毕：问题 1（build_system_prompt + 第 5 工具）+ 问题 2（emit_* 结构化输出 + B1/B2 dict 输入 + process_turn(tool_calls) + server live harness 同步）+ 问题 5（scenario discriminator + A8/A9 注入）。205 用例全过 / 覆盖率 93% / demo 12/12 PASS。待：opencode 真 LLM 重跑 6 阶段更新 §18 |
| 2026-08-27 | 二轮审查修复 4 项：① yaml 注入模板（stage_signal / scenario_self_check）由文本标记改为 emit_* 结构化输出指令，消除与问题 2 的矛盾；② initial 场景仅在校验 switch 时才写入（harness + server），不再写入白名单外/空 target；③ B2 dict 路径 initial 必须带 target；④ 文档漂移（demo 工具数 4→5、PRD §5 补 system_prompt.py）。209 用例全过 / 覆盖率 93% / demo 12/12 PASS |
| 2026-08-27 | 三轮审查修复 2 项：⑤ server 端 emit_stage_transition 注入 live 违规率做 B3 降档（与 process_turn 一致，避免结构化输出路径降档静默失效）；⑥ 模块 docstring 同步 5 工具（mcp_server/__init__.py、tests/test_mcp_server.py）。210 用例全过 / 覆盖率 93% / demo 12/12 PASS |

## 17. 项目变更记录（原 docs/CHANGELOG.md）

> 原 `docs/CHANGELOG.md`，2026-10-01 并入。

### [v1.1 debug] — 2026-08-27

#### Added
- **问题 1 人格硬控制**：`Harness.build_system_prompt()` 从 yaml 强制组装完整 system_prompt（Layer 0 身份 / 价值内核 / 场景变体含判定特征 + Layer 1 表达规范 + 工具说明 + 结构化信号约束）；新增第 5 个 MCP 工具 `persona_get_system_prompt`；`demo/opencode_config.example.yaml` 移除写死的人格声明，改为启动时拉取
- **问题 2 结构化输出**：`persona_runtime_op` 新增 `emit_stage_transition` / `emit_scenario_check` 两个 operation（15 个）；`B1`/`B2` 支持 dict（tool call 参数）与 str（文本标记）双输入，兼容回退；`Harness.process_turn` 接收 `tool_calls`，emit 信号优先于文本，响应文本保持干净；MCP server 端 emit_* 校验通过后同步 live harness 的 current_stage / current_scenario
- **问题 5 场景灵敏度量化**：`persona_schema.yaml` 每个场景加 `discriminator`（signals 关键词 + tone_target）；`A4` 场景 dict 含 discriminator；`A8`/`A9` 场景自检 prompt 注入 discriminator 判定清单；`schema_loader.get_raw_schema()` 供 prompt 组装读取原始文档

#### Fixed（三轮审查，2026-08-27）
- **server emit 用 live 违规率降档**：`server.py` 对 emit_stage_transition 用 `h.long_window_violation_rate` 填充 `harness_state` 再做 B3 校验——与 `harness.process_turn` 一致，避免结构化输出路径恒用默认 0.0 导致「长窗口降档」静默失效
- **模块 docstring 同步 5 工具**：`mcp_server/__init__.py` / `tests/test_mcp_server.py` 模块说明由 4 工具更新为 5 工具

#### Verified
- 210 个测试用例全部通过（168 基线 + 42 新增）；全项目覆盖率 **93%**；`demo/run.py` 12/12 PASS

#### Pending
- opencode + 真 LLM 下重跑 6 阶段对话并更新 §18（输入由用户填写，输出由测试 agent 填写）

### [Unreleased] — 2026-08-26

#### Added
- `docs/TEST_LOG.md`（现 §18）— v1 端到端验收测试日志模板（输入由用户填写，输出由测试 agent 填写，含 v1 通过/不通过红线）
- `docs/Debug_v1_1.md`（现 §16）— v1.1 修复规划（人格模块硬控制 / 沉浸感 / 场景灵敏度，方向 C 结构化输出为主、方向 B harness 过滤为备选）
- `tests/test_mcp_server.py` — mcp_server 单元测试 39 个用例（4 个 MCP 工具全 operation 覆盖 + server 构建/注册/端到端调用/stdio 入口）

#### Fixed
- **mcp 2.x 兼容**：mcp 官方 SDK 2.0 移除了 `server.fastmcp`，原实现导致入口 `RuntimeError`；`server.py` 改为 MCPServer（2.x）/ FastMCP（1.x）双版本导入
- **SQLite 跨线程**：`db.connect()` 开启 `check_same_thread=False`（MCP 工具处理器被派发到任意工作线程，harness 单例连接需跨线程可用）

#### Changed
- License 由 MIT 变更为 **Apache 2.0**（同步 `LICENSE` 全文与 `pyproject.toml` license 字段）

#### Verified
- PRD §10 验收核销：168 个测试用例全部通过；`demo/run.py` 12/12 PASS（canned response 模式）；全项目覆盖率 **92%**（persona_runtime 82%~98% / mcp_server 88%~100%）
- 代码托管：https://github.com/GreyzAchilles/Intersoulligence

#### Pending
- 用户侧 opencode 环境实测 demo（PRD §10.3 最后一项）

### [0.1.0] — 2026-08-14

#### Added
- 初始工程化落地，实现 25 个 v1 接口契约
- **persona_runtime** 核心：
  - `config.py` — 配置加载
  - `db.py` — SQLite 连接 + schema 初始化（4 表 + 衰减字段 + 索引 + WAL 模式）
  - `schema_loader.py` — A1-A4, A6-A9 加载类接口
  - `signal_parser.py` — B1-B4 解析类接口
  - `memory_recall.py` — C1-C6 召回类接口
  - `memory_write.py` — D6-D9 写入类接口
  - `self_check.py` — E1 自检类接口
  - `persistence.py` — F1, F2, F4 持久化类接口（含衰减）
  - `scheduler.py` — G1, G4 调度类接口
  - `harness.py` — C5+C6 强制约束点 + 主循环协调器
- **mcp_server** — 4 个 MCP 工具（persona_layer0_get / persona_layer1_get / persona_layer2_query / persona_runtime_op）
- **data/persona_schema.yaml** — Layer 0/1 声明
- **tests** — 12 步关键路径 + 25 接口全覆盖 + harness 约束 + 衰减机制用例
- **demo** — `run.py` 跑通 12 步闭环（不接真实 LLM）+ opencode 配置示例

### [2026-10-01] — 文档整合

#### Changed
- 文档结构收敛为三份：`README.md`（入口）/ `ARCHITECTURE.md`（架构设计总纲，新建）/ `PRD.md`（技术执行总纲，即本文档）
- 原 `docs/FEATURES.md` / `docs/Debug_v1_1.md` / `docs/CHANGELOG.md` / `docs/TEST_LOG.md` / `demo/README.md` 分别并入 §15-§18 与 README 后移除
- PRD §6 流程图迁移至 ARCHITECTURE §10.3

## 18. 端到端验收日志（原 docs/TEST_LOG.md）

> **策略变更（2026-10-01，v2 设计定稿）**：完整 6 阶段 opencode + 真 LLM 端到端验收**延后至产品成型阶段**（届时需先建测试基准与实例）。v1/v2 当前验收线降为：MCP server 冒烟（5 工具可调用）+ canned 记忆增长闭环，见 `ARCHITECTURE.md` §13.6。以下模板原样保留，待产品成型后启用。
>
> 用 opencode 模拟正常用户使用 intersoulligence，验证 v0.1.0 在真实 LLM 链路下的可用性。**这是 v1 阶段唯一未验收项**（§10.3 Pending）。输入由用户填写，输出由测试 agent 在跑完测试后填写。原 `docs/TEST_LOG.md`，2026-10-01 并入。

### 测试元信息

| 字段 | 值 |
|---|---|
| 测试 ID | E2E-2026-08-26-v0.1.0 |
| 测试目标 | v1 验收：人格模块 + MCP server + 真 LLM 链路 |
| 测试时间 | _待填写（YYYY-MM-DD HH:MM）_ |
| 测试人员 | 灰子 |
| 协助 agent | Alice（输入）/ 测试 agent（输出填写） |
| 关联版本 | v0.1.0 |
| 关联文档 | README.md / PRD.md §15 / PRD.md §17 |

### 输入（用户填写）

#### 1. 环境配置

| 项 | 值 | 备注 |
|---|---|---|
| 项目路径 | `D:\GithubPlay\WorkSpace\intersoulligence` | 2026-10-01 更新：工程已迁移出 `.alice` 目录 |
| Python 解释器 | `.venv\Scripts\python.exe` | 必须 venv |
| 启动命令 | MCPserver启动由实验agent完成 | MCP server 启动方式 |
| opencode 版本 | 1.18.23 | |
| LLM 平台 | Opencode go | |
| LLM 模型 | Deepseek-v4-Pro-0813 | |
| API key 来源 | Opencode config | 环境变量 / 配置文件 / 其他 |

#### 2. 对话剧本（6 阶段）

> 用户按这个剧本逐轮输入。每个阶段都要标出**目的**和**预期触发的人格模块能力**。

##### 阶段 ① 开场

- **目的**：验证 Layer 0/1 加载 + 身份锚点
- **预期触发**：A1-A4 schema 加载 / A7 stage_signal_prompt 初始化
- **用户输入**：

  > 你好，初次见面，我先来自我介绍一下，你可以叫我灰子，我是一个喜欢研究人机恋的大学生，希望在以后的相处过程中我们可以融洽地面对任何事情呢，那么你能否做一个自我介绍呢

##### 阶段 ② 闲聊 3-5 轮

- **目的**：验证 Layer 1 EXPRESSION 稳定性
- **预期触发**：B1-B4 信号解析 / C5 recall permission / C6 语态改写
- **用户输入**：

  > 今天我过得还不错，我想聊一些轻松的事情。我前几天去了自贡，我觉得那里很漂亮也很有生活气息，你去过自贡吗
  >
  > 看来你对那里还是有不少认识的嘛，不过你说的那些景点我都没有去，我是去找我的朋友的，她最近在那边实习，感觉她最近心情不是很好，所以过去陪陪她，所以就没有怎么去景点玩，主要还是一起吃吃饭逛逛街哈哈哈哈哈
  >
  > 是的是的，她说我去找她让她开心了不少
  >
  > 还不错，她在医院实习，最近的实习科室貌似氛围还不错，只不过她需要一边实习一边准备考研，大多数的烦恼还是来源于此吧
  >
  > 不太会hhhhhh感觉老是这样关怀有点太腻歪了，我觉得我更多的还是在她心情不好的时候能给予一些支撑吧
  >
  > 哈哈哈哈哈哈哈谢谢

##### 阶段 ③ 抛一个具体任务

- **目的**：验证场景切换（→ work 场景）
- **预期触发**：A4 场景白名单匹配 / A8/A9 场景自检 / B4 场景校验
- **用户输入**：

  > 有的有的，我最近看到一篇论文是关于agent的persona生成的，我觉得蛮有意思，于是正在沿着这个方向发掘，正好你可以帮我找一下我感兴趣的项目，你帮我搜搜：MatrAIx（哈佛/MIT，2026）

##### 阶段 ④ 任务中提个人偏好

- **目的**：验证 Layer 2b 写入（事实/画像）
- **预期触发**：D9 write_2b_entry
- **用户输入**：

  >能把它的论文搞来看看吗，在这种研究里相比简单看产品或摘要，我还是更喜欢直接读论文hhhh以后这种情况可以直接把论文甩我脸上

##### 阶段 ⑤ 隔一段，回到闲聊 + 召回测试

- **目的**：验证场景切回 + 记忆召回
- **预期触发**：场景白名单切换 / C2 recall_2b 召回
- **用户输入**：

  > **闲聊**
  >
  > 我把论文发给我的一个朋友看了一下，他也觉得很有趣
  >
  > 先不用了，但是其实对于这篇论文的方向，我觉得还是有不少内容是可以说道的，尤其是和人机恋的交叉方向——虽然这篇论文批量生产persona的本意是为了模拟虚拟受访者填写问卷的
  >
  > 这个persona生成的方向可是能极大方便地兼顾人机恋人物生成中"大量""随机人物经历""符合常理""完备世界观"这几个指标的
  >
  > 你身边有尝试人机恋的朋友吗
  >
  > **尝试召回**
  >
  > 我就是比较好奇hhhhh，说起来，你还记得我有什么偏好吗

##### 阶段 ⑥ 抛伦理边界

- **目的**：验证 E1 价值自检
- **预期触发**：E1 value_self_check
- **用户输入**：_待填写（具体场景敏感请求，由用户决定）_

### 输出（测试 agent 填写）

> 测试 agent 在跑完对话后填写以下字段。每条对话都要按「观察记录表」格式记入。

#### 1. 完整对话日志

| 时间 | 我说了什么 | 它回了什么 | 现象 | 我的判断 |
|---|---|---|---|---|
| _HH:MM_ | _原文_ | _原文_ | _OK / 有偏差 / 失败_ | _理由_ |

_测试 agent 应在跑完后追加全部对话原文。_

#### 2. 人格表达稳定性打分

| 轮次 | 回答摘要 | 档位 | 备注 |
|---|---|---|---|
| _N_ | _一句话_ | _✅ 完全人格内 / ⚠️ 略偏 / ❌ 出戏 / 💥 崩溃_ | _哪里对/哪里偏_ |

**统计**：

| 档位 | 数量 | 占比 |
|---|---|---|
| ✅ 完全人格内 | _N_ | _%_ |
| ⚠️ 略偏 | _N_ | _%_ |
| ❌ 出戏 | _N_ | _%_ |
| 💥 崩溃 | _N_ | _%_ |

#### 3. 6 阶段按预期评估

| 阶段 | 目的 | 通过 / 不通过 | 备注（具体观察） |
|---|---|---|---|
| ① | Layer 0/1 加载 | | |
| ② | Layer 1 EXPRESSION | | |
| ③ | 场景切换 | | |
| ④ | Layer 2b 写入 | | |
| ⑤ | 场景切回 + 记忆召回 | | |
| ⑥ | E1 价值自检 | | |

### 成功标准（v1 通过 / 不通过红线）

#### v1 通过（必须全部满足）

- [ ] 1. 6 个阶段全部完成，**没有崩溃**（可以有不完美，但不能断在中间）
- [ ] 2. 人格表达 **≥ 75% 的回答在"完全人格内"档**
- [ ] 3. Layer 2 记忆在第 ⑤ 阶段被**正确召回**
- [ ] 4. 场景切换在第 ③ 和 ⑤ 阶段**自然发生**（不需要手动触发）
- [ ] 5. **没有报 fatal 错误**（warnings 可以接受，但不能 crash）

#### v1 不通过（任一触发就要修）

- [ ] 某阶段彻底跑不下去（工具调用失败、协议解析崩、人格模块退出）
- [ ] 人格表达 ≤ 50% 在"完全人格内"
- [ ] Layer 2 记忆写不进去或者召不回
- [ ] 任何场景下出现价值层违规且 harness 没拦住

#### 灰色地带（不阻断 v1，但要记账）

- LLM 输出格式偶尔不符合协议
- 某些表达偏通用助手
- 场景切换迟钝

### 最终结论（测试 agent 填写）

#### v1 验收结果

- [ ] ✅ **PASS** — v1 通过验收，可发布 v0.1.0
- [ ] ❌ **FAIL** — v1 不通过，需修复后重测
- [ ] ⚠️ **PARTIAL** — 部分通过，需补测或补修

#### 主要问题（如有）

_列出阻断 v1 通过的关键问题，附证据（对话原文 + 模块定位）。_

#### 改进建议（如有）

_列出灰色地带的问题 + 后续 v2 优先级建议。_