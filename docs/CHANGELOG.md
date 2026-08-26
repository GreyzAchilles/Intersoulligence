# Changelog

## [Unreleased] — 2026-08-26

### Added
- `tests/test_mcp_server.py` — mcp_server 单元测试 39 个用例（4 个 MCP 工具全 operation 覆盖 + server 构建/注册/端到端调用/stdio 入口）

### Fixed
- **mcp 2.x 兼容**：mcp 官方 SDK 2.0 移除了 `server.fastmcp`，原实现导致入口 `RuntimeError`；`server.py` 改为 MCPServer（2.x）/ FastMCP（1.x）双版本导入
- **SQLite 跨线程**：`db.connect()` 开启 `check_same_thread=False`（MCP 工具处理器被派发到任意工作线程，harness 单例连接需跨线程可用）

### Changed
- License 由 MIT 变更为 **Apache 2.0**（同步 `LICENSE` 全文与 `pyproject.toml` license 字段）

### Verified
- PRD §10 验收核销：168 个测试用例全部通过；`demo/run.py` 12/12 PASS（canned response 模式）；全项目覆盖率 **92%**（persona_runtime 82%~98% / mcp_server 88%~100%）
- 代码托管：https://github.com/GreyzAchilles/Intersoulligence

### Pending
- 用户侧 opencode 环境实测 demo（PRD §10.3 最后一项）

## [0.1.0] — 2026-08-14

### Added
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