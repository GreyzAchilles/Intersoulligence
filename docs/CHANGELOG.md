# Changelog

## [v1.1 debug] — 2026-08-27

### Added
- **问题 1 人格硬控制**：`Harness.build_system_prompt()` 从 yaml 强制组装完整 system_prompt（Layer 0 身份 / 价值内核 / 场景变体含判定特征 + Layer 1 表达规范 + 工具说明 + 结构化信号约束）；新增第 5 个 MCP 工具 `persona_get_system_prompt`；`demo/opencode_config.example.yaml` 移除写死的人格声明，改为启动时拉取
- **问题 2 结构化输出**：`persona_runtime_op` 新增 `emit_stage_transition` / `emit_scenario_check` 两个 operation（15 个）；`B1`/`B2` 支持 dict（tool call 参数）与 str（文本标记）双输入，兼容回退；`Harness.process_turn` 接收 `tool_calls`，emit 信号优先于文本，响应文本保持干净；MCP server 端 emit_* 校验通过后同步 live harness 的 current_stage / current_scenario
- **问题 5 场景灵敏度量化**：`persona_schema.yaml` 每个场景加 `discriminator`（signals 关键词 + tone_target）；`A4` 场景 dict 含 discriminator；`A8`/`A9` 场景自检 prompt 注入 discriminator 判定清单；`schema_loader.get_raw_schema()` 供 prompt 组装读取原始文档

### Fixed（三轮审查，2026-08-27）
- **server emit 用 live 违规率降档**：`server.py` 对 emit_stage_transition 用 `h.long_window_violation_rate` 填充 `harness_state` 再做 B3 校验——与 `harness.process_turn` 一致，避免结构化输出路径恒用默认 0.0 导致「长窗口降档」静默失效
- **模块 docstring 同步 5 工具**：`mcp_server/__init__.py` / `tests/test_mcp_server.py` 模块说明由 4 工具更新为 5 工具

### Verified
- 210 个测试用例全部通过（168 基线 + 42 新增）；全项目覆盖率 **93%**；`demo/run.py` 12/12 PASS

### Pending
- opencode + 真 LLM 下重跑 6 阶段对话并更新 `docs/TEST_LOG.md`（输入由用户填写，输出由测试 agent 填写）

## [Unreleased] — 2026-08-26

### Added
- `docs/TEST_LOG.md` — v1 端到端验收测试日志模板（输入由用户填写，输出由测试 agent 填写，含 v1 通过/不通过红线）
- `docs/Debug_v1_1.md` — v1.1 修复规划（人格模块硬控制 / 沉浸感 / 场景灵敏度，方向 C 结构化输出为主、方向 B harness 过滤为备选）
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