"""persona_runtime.scheduler — G1, G4 调度类接口

plan subagent 调度 + 首次切换注入规则。

来源：PRD §11 序号 16
       接口-v1 §G
       阶段切换信号 v6 §10
"""

from __future__ import annotations

import uuid
import warnings
from typing import Any

# 阶段切换信号 v6 §10 — plan subagent 首次切换注入规则
FIRST_SWITCH_RULE = """
你是 plan subagent。
你的所有产出都返回 grill agent。
开始分发任务的指令只能由 grill agent 发布。
在收到 grill agent 的明确发布指令之前，你只处理任务并返回结果。
"""


# ---------------------------------------------------------------------------
# G1 spawn_plan_subagent(grill_output, ...)
# ---------------------------------------------------------------------------
def G1_spawn_plan_subagent(
    grill_output: str,
    injected_rule: str = "",
) -> dict[str, Any]:
    """G1 — 启动 plan subagent + 注入 Layer 0.4 规则。

    返回 subagent_id / initial_state / injected_prompt。
    """
    subagent_id = f"plan_subagent_{uuid.uuid4().hex[:8]}"
    rule = injected_rule or FIRST_SWITCH_RULE.strip()
    return {
        "spawned": {
            "subagent_id": subagent_id,
            "initial_state": "processing",
            "injected_prompt": rule,
        }
    }


# ---------------------------------------------------------------------------
# G4 inject_plan_subagent_first_switch_rule()
# ---------------------------------------------------------------------------
def G4_inject_plan_subagent_first_switch_rule() -> dict[str, Any]:
    """G4 — 人格第一次切到 plan_subagent 时注入。

    permanent=True（一次性注入，plan subagent 始终记住）。
    注入失败 → 警告，重试 1 次（这里直接返回成功，retry 在 harness）。
    """
    return {"injected": {"rule": FIRST_SWITCH_RULE.strip(), "permanent": True}}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def try_inject_with_retry() -> dict[str, Any]:
    """G4 注入失败时重试 1 次（PRD §11 错误处理）。"""
    try:
        return G4_inject_plan_subagent_first_switch_rule()
    except Exception as e:
        warnings.warn(f"G4 inject failed: {e} — retry 1")
        return G4_inject_plan_subagent_first_switch_rule()