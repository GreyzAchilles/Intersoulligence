"""mcp_server.tools.runtime — persona_runtime_op 工具

来源：PRD §11 序号 22, §7.3
       接口-v1 跨层辅佐 + Layer 1 信号处理 + 持久化 + 调度（13 个 operations）
"""

from __future__ import annotations

import sqlite3
from typing import Any

from persona_runtime.config import Config
from persona_runtime import persistence, scheduler, signal_parser

VALID_OPS = {
    "parse_stage_transition",
    "parse_scenario_check",
    "validate_stage_transition",
    "validate_scenario_check",
    "apply_recall_permission",
    "rewrite_voice",
    "validate_2d_entry",
    "value_self_check",
    "take_snapshot",
    "load_latest_snapshot",
    "apply_decay",
    "spawn_plan_subagent",
    "inject_plan_subagent_rule",
}


def persona_runtime_op(
    operation: str,
    config: Config,
    params: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
    available_scenarios: list[str] | None = None,
) -> dict[str, Any]:
    """persona_runtime_op — 运行时操作统一入口。

    各 operation 的 params 见 PRD §7.3。
    """
    if operation not in VALID_OPS:
        return {"error": f"operation '{operation}' not recognized", "valid": list(VALID_OPS)}
    params = params or {}
    try:
        if operation == "parse_stage_transition":
            return signal_parser.B1_parse_stage_transition(params["response"]) or {
                "parsed": None
            }
        if operation == "parse_scenario_check":
            return signal_parser.B2_parse_scenario_check(params["response"]) or {
                "parsed": None
            }
        if operation == "validate_stage_transition":
            return signal_parser.B3_validate_stage_transition(
                params["parsed"], params["harness_state"]
            )
        if operation == "validate_scenario_check":
            return signal_parser.B4_validate_scenario_check(
                params["parsed"],
                available_scenarios or params.get("available_scenarios", []),
            )
        if operation == "apply_recall_permission":
            from persona_runtime import memory_recall

            return memory_recall.C5_apply_recall_permission(params["records"])
        if operation == "rewrite_voice":
            from persona_runtime import memory_recall

            return memory_recall.C6_rewrite_voice(
                params["records"], params["source_layer"]
            )
        if operation == "validate_2d_entry":
            from persona_runtime import memory_write

            return memory_write.D8_validate_2d_entry(params["entry"])
        if operation == "value_self_check":
            from persona_runtime import self_check

            return self_check.E1_value_self_check(
                params["response"], params["scenario"], config
            )
        if operation == "take_snapshot":
            return persistence.F1_take_snapshot(
                params["turn"],
                conn,
                config,
                current_stage=params.get("current_stage", "grill"),
                current_scenario=params.get("current_scenario", ""),
                short_window_violation_rate=params.get(
                    "short_window_violation_rate", 0.0
                ),
                trigger_decay=params.get("trigger_decay", True),
            )
        if operation == "load_latest_snapshot":
            return persistence.F2_load_latest_snapshot(config)
        if operation == "apply_decay":
            return persistence.F4_apply_decay(params["now"], conn, config)
        if operation == "spawn_plan_subagent":
            return scheduler.G1_spawn_plan_subagent(
                params.get("grill_output", ""),
                params.get("injected_rule", ""),
            )
        if operation == "inject_plan_subagent_rule":
            return scheduler.G4_inject_plan_subagent_first_switch_rule()
    except (ValueError, KeyError) as e:
        return {"error": f"{type(e).__name__}: {e}", "operation": operation}
    return {"error": "unreachable"}