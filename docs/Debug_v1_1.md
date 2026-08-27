# Debug_v1_1

> v1 端到端验收（`docs/TEST_LOG.md`）暴露问题的修复规划。
> 修复目标：让人格模块对 LLM 形成"硬控制"，消除沉浸感破坏，量化场景判定。

---

## 现在修

### 问题 1：人格模块对 LLM 是"软约束"

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

---

### 问题 2：协议标记破坏沉浸感

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

---

### 问题 5：场景切换灵敏度量化

**修复方向**：在 `persona_schema.yaml` 给每个场景加**判定特征清单**，harness 的 A9 自检 prompt 注入判定清单，让 LLM 有量化标准。

**影响文件**：

| 文件 | 改动 |
|---|---|
| `data/persona_schema.yaml` | 每个 scenario 加 `discriminator` 字段（关键词清单 + 场景触发条件） |
| `persona_runtime/schema_loader.py` | A4 返回场景时含 discriminator |
| `tests/test_schema_loader.py` | 新增 discriminator 加载用例 |
| `tests/test_self_check.py` | 新增基于 discriminator 的自检用例 |

**yaml 改造示例**：

```yaml
scenarios:
  - name: chatbot_mode
    discriminator:
      signals: [闲聊, 情绪, 陪伴, "想你了"]
      tone_target: 轻松 / 生活化
    ...
  - name: work_agent_mode
    discriminator:
      signals: [任务, 数据, 效率, "帮我"]
      tone_target: 简洁 / 专业
    ...
```

**验收标准**：

- [x] `persona_schema.yaml` 每个 scenario 含 discriminator 字段
- [x] A4 返回场景 dict 含 discriminator
- [x] A9 prompt 注入 discriminator 内容（`ongoing["discriminator"]` + `scenario_discriminators`；A8 首轮 prompt 同步注入）
- [x] 单测覆盖：discriminator 加载 + 自检 prompt 含 discriminator

---

## 暂时搁置

- 问题 3（阶段⑥ E1 未跑）
- 问题 4（2b vs 2d 边界）
- 问题 6（反推时间戳）
- 问题 7（评分口径）
- 问题 8（测试 agent 自评偏差）
- 问题 9（模型 ID 真实性）
- 问题 10（system_prompt 与 yaml 重复）
- 问题 11（v1 测试覆盖盲区）

---

## 修复顺序

1. **问题 1 + 问题 5**：harness 提升为 prompt 组装器，yaml 加判定特征——同时改 yaml 和 harness.py
2. **问题 2**：结构化输出迁移——改 runtime.py / signal_parser.py / harness.py
3. **测试**：每个修复都先加单测再实施
4. **验证**：本地 dev run 通过后，更新 TEST_LOG 重跑 6 阶段对话

---

## 变更记录

| 日期 | 变更 |
|---|---|
| 2026-08-27 | 初始规划（v1 验收暴露问题的修复方向） |
| 2026-08-27 | 三项修复实施完毕：问题 1（build_system_prompt + 第 5 工具）+ 问题 2（emit_* 结构化输出 + B1/B2 dict 输入 + process_turn(tool_calls) + server live harness 同步）+ 问题 5（scenario discriminator + A8/A9 注入）。205 用例全过 / 覆盖率 93% / demo 12/12 PASS。待：opencode 真 LLM 重跑 6 阶段更新 TEST_LOG |
| 2026-08-27 | 二轮审查修复 4 项：① yaml 注入模板（stage_signal / scenario_self_check）由文本标记改为 emit_* 结构化输出指令，消除与问题 2 的矛盾；② initial 场景仅在校验 switch 时才写入（harness + server），不再写入白名单外/空 target；③ B2 dict 路径 initial 必须带 target；④ 文档漂移（demo/README 4→5 工具、PRD §5 补 system_prompt.py）。209 用例全过 / 覆盖率 93% / demo 12/12 PASS |
| 2026-08-27 | 三轮审查修复 2 项：⑤ server 端 emit_stage_transition 注入 live 违规率做 B3 降档（与 process_turn 一致，避免结构化输出路径降档静默失效）；⑥ 模块 docstring 同步 5 工具（mcp_server/__init__.py、tests/test_mcp_server.py）。210 用例全过 / 覆盖率 93% / demo 12/12 PASS |