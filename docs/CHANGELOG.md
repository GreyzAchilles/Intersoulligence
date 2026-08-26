# Changelog

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