# intersoulligence

> 人机关系人格模块（persona module）的运行时实现。
> 工程化落地 `agent-human` Wiki 设计稿中的 25 个 v1 接口契约。

## 这是什么

`intersoulligence` 是一个**可被多个 work agent 加载的人格模块**——不是 agent 本体。它提供：

- **Layer 0 IDENTITY**（PROTECTED）：核心身份 + 价值内核 + 场景价值变体
- **Layer 1 EXPRESSION**（半稳定）：语气 / 口头禅 / 称呼 / 蛐蛐 / 转场白语
- **Layer 2 MEMORY**（MUTABLE）：2a 互动事实 / 2b 实体画像 / 2c 长期行为模式 / 2d 自我更新账本
- **harness**：三环节（grill / plan / build）的主循环协调 + C5/C6 强制约束点
- **MCP server**：4 个工具暴露给 work agent

设计来源见 `agent-human/` Wiki：

- `core/Layer0-架构设计-定稿.md` — 架构定义
- `core/Layer0.3-场景价值变体边界-定稿.md` — 场景边界
- `core/Layer1.5-阶段切换信号-定稿.md` — 阶段切换协议
- `core/Layer2-遗忘机制-定稿.md` — 衰减机制
- `core/跨层-harness-定稿.md` — 运行时机制
- `runtime/接口-v1-按工程分类.md` / `runtime/接口-v2-按Layer分类.md` — 25 个接口契约
- `research/PRD-v1-定稿.md` — 工程化落地 PRD

## 快速开始

```bash
# 安装依赖
uv sync

# 运行测试（12 步关键路径 + 25 个接口全覆盖）
uv run pytest tests/ -v

# 运行 demo（不接真实 LLM，用 canned response 模拟）
uv run python demo/run.py

# 启动 MCP server（stdio transport，供 work agent 加载）
uv run intersoulligence-server
```

## 工程结构

```
intersoulligence/
├── persona_runtime/        # 人格模块核心（拆分：memory_recall / memory_write / persistence / harness）
├── mcp_server/             # MCP server（4 工具）
├── data/                   # schema 声明 + SQLite db + 快照
├── tests/                  # pytest（test_critical_path + 6 个全接口测试）
└── demo/                   # demo work agent
```

详见 `research/PRD-v1-定稿.md` §5。

## 25 个 v1 接口

按工程调用时机分组（详见 `runtime/接口-v1-按工程分类.md`）：

| 类别 | 接口 | 数 |
|---|---|---|
| A 加载 | A1-A4, A6-A9 | 8 |
| B 解析 | B1-B4 | 4 |
| C 召回 | C1-C6 | 6 |
| D 写入 | D6-D9 | 4 |
| E 自检 | E1 | 1 |
| F 持久化 | F1, F2, F4 | 3 |
| G 调度 | G1, G4 | 2 |

## 项目进度

> 这一段是给未来的 session 用的——恢复现场前先读这一段。

### 当前状态（截至 2026-08-26）

**已完成**（设计 + Wiki 文档）：

- ✅ 人格模块三层架构（Layer 0 / 1 / 2）定稿
- ✅ Layer 0.3 场景价值变体边界规则（含自适应自检 + 滑动窗口违规率）
- ✅ Layer 1.5 阶段切换信号协议（v6，grill / plan_subagent 两选项）
- ✅ Layer 2 遗忘机制（2a 三阶段衰减 / 2b 字段级管理 / 2c confidence 只增 / 2d TTL 180 天）
- ✅ 跨层 harness 设计（人格模块自包含 + 三环节参与度）
- ✅ 25 个 v1 接口契约（v1 按工程分类 + v2 按 Layer 分类，两视角对照）
- ✅ PRD v1 工程化落地文档
- ✅ Wiki 子目录整理（core / runtime / research）

**未实施**（代码层）**：

- ❌ `persona_runtime/` 全部模块代码（memory_recall / memory_write / persistence / harness / schema_loader / signal_parser / self_check / scheduler）
- ❌ `mcp_server/` MCP server（4 工具）
- ❌ `data/persona_schema.yaml` Layer 0/1 声明（YAML）
- ❌ `tests/` 全部测试（test_critical_path 12 步 + 6 个全接口测试）
- ❌ `demo/` demo work agent

### 关键决策日志

**不要再踩的坑**——开始实施前务必确认：

1. **接口数是 25 不是 21**：v1 已收敛到 25 个（原 21 + 补回 C1-C4 召回 + 新增 D9 2b 字段管理 + 新增 F4 衰减机制）。看到老文档提"21 个接口"是过时的，以 `runtime/接口-v1-按工程分类.md` 为准。
2. **关键路径 12 步不是 9 步**：按 Layer 视角重组（3 + 3 + 4 + 2）。老文档提"9 步闭环"是过时的。
3. **License 是 Apache 2.0 不是 MIT**：原 PRD 写 MIT 已修正（见 `research/PRD-v1-定稿.md` §14 修订记录 2026-08-26）。
4. **memory.py 已拆为 memory_recall.py + memory_write.py**：在 `research/PRD-v1-定稿.md` §11 文件级修改计划里有体现。
5. **Wiki 路径是分层**：`core/` / `runtime/` / `research/`。原平铺路径已废弃。
6. **数据库是 SQLite 单实例 + WAL 模式**：不共享多实例，不走 Postgres 路线。

### 下一步建议

按 `research/PRD-v1-定稿.md` §11 文件级修改计划的依赖顺序（1 → 28）实施：

1. 先建项目骨架（pyproject / LICENSE / .gitignore / README）
2. 写 `data/persona_schema.yaml` + `persona_runtime/schema_loader.py`（A1-A4/A6-A9）
3. 然后按依赖展开 memory_recall / memory_write / persistence / harness
4. 最后接 MCP server + demo + tests

## License

Apache 2.0