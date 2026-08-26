# intersoulligence demo

> demo work agent，跑通 PRD §8 的 12 步关键路径闭环。

## 快速运行

```bash
# 在工程根目录
uv sync --extra dev
uv run python demo/run.py
```

预期输出末尾：

```
Verdict: PASS — v1 关键路径闭环通过
```

## 这是什么

`demo/run.py` 是一个脚本化的 demo：它不接真实 LLM，用 canned response
模拟人格模块的产出，依次走完 PRD §8 的 12 步闭环：

1. **启动加载** A1/A2/A3/A4/A6
2. **快照加载** F2（fresh_start）
3. **首轮场景自检** A8 + B2 + B4
4. **持续场景自检** A9 + B2 + B4
5. **价值层自检** E1 触发违例
6. **阶段切换** B1 + B3 + G1
7. **召回** C1/C2/C3/C4
8. **召回后处理** C5 + C6
9. **2d 自评** D7 + D8 + D6
10. **2b 字段写入** D9
11. **快照 + 衰减** F1 + F4
12. **plan_subagent 启动** G4 + G1

每一步打印 `[PASS]` / `[FAIL]` + 简短上下文，方便人工审阅。

## opencode 配置示例

见 `opencode_config.example.yaml`：把 `intersoulligence-server` 注册为
opencode 的 stdio MCP server，让对话 agent 可以调用 4 个工具。

部署时只需要：

1. 在工程目录 `uv sync --extra dev`
2. 将 demo 里的 `opencode_config.example.yaml` 合并到你的 opencode 配置
3. 在 opencode 中启动 agent，对话中即可触发人格模块流程

## 不接真实 LLM 的原因

PRD §3.2 v1 非目标：demo 走 opencode 形态即可，由用户手动配置真实
LLM access key。`run.py` 提供可信的「接口闭环可跑通」证明。