"""mcp_server.tools.layer0 — persona_layer0_get 工具

来源：PRD §11 序号 19, §7.3
       接口-v2 Layer 0 接口（6 个: schema/anchors/value_kernel/scenarios/self_check_policy/initial_scenario_check）
"""

from __future__ import annotations

from typing import Any

from persona_runtime.config import Config
from persona_runtime import schema_loader

VALID_FIELDS = {
    "schema",
    "anchors",
    "value_kernel",
    "scenarios",
    "self_check_policy",
    "initial_scenario_check",
}


def persona_layer0_get(field: str, config: Config) -> dict[str, Any]:
    """persona_layer0_get — Layer 0 数据一次性获取。

    input:
      field: enum[schema, anchors, value_kernel, scenarios, self_check_policy, initial_scenario_check]
    output:
      data: 对应字段完整数据
    errors:
      field 不识别 → 拒绝
      数据未初始化 → 拒绝
    """
    if field not in VALID_FIELDS:
        return {"error": f"field '{field}' not recognized", "valid": list(VALID_FIELDS)}
    dispatch = {
        "schema": schema_loader.A1_load_persona_schema,
        "anchors": schema_loader.A2_get_identity_anchors,
        "value_kernel": schema_loader.A3_get_value_kernel,
        "scenarios": schema_loader.A4_get_available_scenarios,
        "self_check_policy": schema_loader.A6_get_self_check_policy,
        "initial_scenario_check": schema_loader.A8_get_initial_scenario_check_prompt,
    }
    try:
        result = dispatch[field](config)
        return {"data": result}
    except (ValueError, FileNotFoundError) as e:
        return {"error": str(e)}