# Features 追踪

> v1 工程化落地的功能状态追踪。

## v1.0 — 初始工程化落地

### Layer 0 / 1 加载（A 类接口）
- [x] A1 `load_persona_schema()` — 读取 schema 文件返回结构化声明
- [x] A2 `get_identity_anchors()` — 返回场景对应的身份锚点
- [x] A3 `get_value_kernel()` — 返回价值内核（beliefs / refusals / judgment_principles）
- [x] A4 `get_available_scenarios()` — 返回可用场景白名单
- [x] A6 `get_self_check_policy()` — 返回自检机制归属（harness_managed）
- [x] A7 `get_stage_signal_prompt()` — 返回阶段切换信号 prompt 模板
- [x] A8 `get_initial_scenario_check_prompt()` — 返回首轮场景自检 prompt
- [x] A9 `get_ongoing_scenario_check_prompt()` — 返回持续场景自检 prompt

### Layer 1 信号解析（B 类接口）
- [x] B1 `parse_stage_transition()` — 解析 `[STAGE_TRANSITION]` 标记
- [x] B2 `parse_scenario_check()` — 解析 `[SCENARIO_CHECK]` 标记
- [x] B3 `validate_stage_transition()` — 长窗口违规率降档校验
- [x] B4 `validate_scenario_check()` — 场景白名单校验

### Layer 2 召回（C 类接口）
- [x] C1 `recall_2a()` — 互动事实召回（更新 last_accessed）
- [x] C2 `recall_2b()` — 实体画像召回
- [x] C3 `recall_2c()` — 长期模式召回（更新 last_accessed）
- [x] C4 `recall_2d()` — 自我更新账本召回
- [x] C5 `apply_recall_permission()` — 三档 recall permission 标记
- [x] C6 `rewrite_voice()` — 检索后语态改写

### Layer 2 写入（D 类接口）
- [x] D6 `append_2d_entry()` — 自我更新账本写入
- [x] D7 `maybe_2d_trigger()` — 2d 触发检测
- [x] D8 `validate_2d_entry()` — 2d 条目伦理校验
- [x] D9 `write_2b_entry()` — 2b 字段级写入（facts / current_status / judgment 分流）

### 自检（E 类接口）
- [x] E1 `value_self_check()` — 价值层自检（规则化）

### 持久化（F 类接口）
- [x] F1 `take_snapshot()` — 每 20 轮落盘快照
- [x] F2 `load_latest_snapshot()` — 启动时加载最近快照
- [x] F4 `apply_decay()` — 2a 三阶段衰减 + 2d TTL 衰减

### 调度（G 类接口）
- [x] G1 `spawn_plan_subagent()` — 启动 plan subagent + 注入规则
- [x] G4 `inject_plan_subagent_first_switch_rule()` — 首次切换注入 first switch rule

### harness
- [x] C5 + C6 强制约束点
- [x] 主循环协调器（每轮响应闭环）

### MCP server
- [x] `persona_layer0_get` 工具
- [x] `persona_layer1_get` 工具
- [x] `persona_layer2_query` 工具
- [x] `persona_runtime_op` 工具
- [x] `persona_get_system_prompt` 工具（v1.1）

### v1.1 debug 修复（见 `docs/Debug_v1_1.md`）
- [x] 问题 1 — `Harness.build_system_prompt()` prompt 强制组装器 + MCP 第 5 工具下发
- [x] 问题 2 — 结构化输出：`emit_stage_transition` / `emit_scenario_check` + B1/B2 dict 输入 + `process_turn(tool_calls)` + server 端 live harness 状态同步
- [x] 问题 5 — 场景 `discriminator` 判定特征 + A8/A9 prompt 注入

### 数据
- [x] SQLite schema（4 张表 + 衰减字段 + 索引）
- [x] `persona_schema.yaml` — Layer 0/1 声明（含场景 discriminator 判定特征）

### 测试
- [x] 12 步关键路径闭环
- [x] 25 个接口全覆盖
- [x] harness C5/C6 约束 3 用例
- [x] F4 衰减 4 用例
- [x] 210 用例全过（168 基线 + 42 v1.1 新增），覆盖率 93%
- [ ] opencode 端到端实测（v1 验收唯一未完成项）— 见 `docs/TEST_LOG.md`
- [ ] v1.1 重跑 6 阶段对话验收 — 见 `docs/Debug_v1_1.md` / `docs/TEST_LOG.md`

### demo
- [x] `demo/run.py` — 12 步闭环
- [x] opencode 配置示例