"""mcp_server.tools.layer1 — persona_layer1_get 工具

来源：PRD §11 序号 20, §7.3
       接口-v2 Layer 1 接口（2 个: stage_signal_prompt / ongoing_scenario_check）
"""

from __future__ import annotations

from typing import Any

from persona_runtime.config import Config
from persona_runtime import schema_loader

VALID_FIELDS = {"stage_signal_prompt", "ongoing_scenario_check"}


def persona_layer1_get(
    field: str,
    config: Config,
    current_scenario: str = "",
) -> dict[str, Any]:
    """persona_layer1_get — Layer 1 prompt 模板获取。

    input:
      field: enum[stage_signal_prompt, ongoing_scenario_check]
      current_scenario: string  # 仅 ongoing_scenario_check 必填
    output:
      data: 对应字段 prompt 模板
    errors:
      field 缺失 current_scenario → 拒绝
      当前场景不在白名单 → 回退到首轮
    """
    if field not in VALID_FIELDS:
        return {"error": f"field '{field}' not recognized", "valid": list(VALID_FIELDS)}
    if field == "stage_signal_prompt":
        return {"data": schema_loader.A7_get_stage_signal_prompt(config)}
    if field == "ongoing_scenario_check":
        if not current_scenario:
            return {
                "error": "current_scenario required for ongoing_scenario_check"
            }
        return {"data": schema_loader.A9_get_ongoing_scenario_check_prompt(config, current_scenario)}
    return {"error": "unknown field"}