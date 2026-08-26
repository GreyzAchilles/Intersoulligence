"""persona_runtime.signal_parser — B1-B4 解析类接口

解析人格输出中的协议标记 + 校验合法性。纯字符串处理，无 LLM 调用。

来源：PRD §11 序号 11
       接口-v1 §B（阶段切换信号 v6 协议）
"""

from __future__ import annotations

import re
import warnings
from typing import Any

VALID_STAGES_FOR_TO = {"grill", "plan_subagent"}
CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}
RANK_TO_CONFIDENCE = {3: "high", 2: "medium", 1: "low"}

_STAGE_RE = re.compile(
    r"\[STAGE_TRANSITION\]\s*"
    r"to:\s*(\S+)\s*"
    r"confidence:\s*(\S+)\s*"
    r"\[/STAGE_TRANSITION\]",
    re.IGNORECASE,
)

_SCENARIO_INITIAL_RE = re.compile(
    r"\[SCENARIO_CHECK\]\s*initial:\s*(\S+)", re.IGNORECASE
)
_SCENARIO_ONGOING_RE = re.compile(
    r"\[SCENARIO_CHECK\]\s*(?:switch_to|stay(?::\s*\S+)?)\s*:?\s*(\S*)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# B1 parse_stage_transition(response)
# ---------------------------------------------------------------------------
def B1_parse_stage_transition(response: str) -> dict[str, Any] | None:
    """B1 — 解析 [STAGE_TRANSITION] 标记。缺失/不合法 → None。多个取最后一个。"""
    matches = list(_STAGE_RE.finditer(response))
    if not matches:
        return None
    last = matches[-1]
    to_raw = last.group(1).strip()
    conf_raw = last.group(2).strip().lower()
    if to_raw not in VALID_STAGES_FOR_TO:
        warnings.warn(f"B1 invalid to: {to_raw} — ignored")
        return None
    if conf_raw not in CONFIDENCE_RANK:
        warnings.warn(f"B1 invalid confidence: {conf_raw} — ignored")
        return None
    return {"parsed": {"to": to_raw, "confidence": conf_raw}}


# ---------------------------------------------------------------------------
# B2 parse_scenario_check(response)
# ---------------------------------------------------------------------------
def B2_parse_scenario_check(response: str) -> dict[str, Any] | None:
    """B2 — 解析 [SCENARIO_CHECK] 标记。无标记 → None（harness 保持当前场景）。"""
    initial_match = _SCENARIO_INITIAL_RE.search(response)
    if initial_match:
        target = initial_match.group(1).strip()
        return {"parsed": {"mode": "initial", "action": "initial", "target": target}}

    ongoing_matches = list(_SCENARIO_ONGOING_RE.finditer(response))
    if not ongoing_matches:
        return None
    last = ongoing_matches[-1]
    line = last.group(0)
    target = last.group(1).strip() if last.group(1) else ""
    # target 是下一行 [RESPONSE] 误捕获的情况，剔除 tag 前缀
    if target.startswith("[") or target.lower() == "response" or target.lower().startswith("response"):
        target = ""
    # 真正的 stay：标记行含 stay 关键字；target 可空（直接 stay）或为当前场景名
    if re.search(r"\bstay\b", line, re.IGNORECASE):
        if not target:
            target = ""
            warnings.warn("B2 stay with empty target — keep current scenario")
        return {"parsed": {"mode": "ongoing", "action": "stay", "target": target}}
    # switch_to 但没有 target → 忽略（无意义）
    if not target:
        warnings.warn("B2 switch_to without target — ignored")
        return None
    return {"parsed": {"mode": "ongoing", "action": "switch_to", "target": target}}


# ---------------------------------------------------------------------------
# B3 validate_stage_transition(parsed, harness_state)
# ---------------------------------------------------------------------------
def B3_validate_stage_transition(
    parsed: dict[str, Any], harness_state: dict[str, Any]
) -> dict[str, Any]:
    """B3 — 长窗口违规率降档校验。

    long_window_violation_rate:
      >= 25% → 降两档 (high→low, medium→low)
      >= 10% → 降一档 (high→medium, medium→low)
      <  10% → 不变
    """
    rate = harness_state.get("long_window_violation_rate", 0.0)
    to = parsed["to"]
    conf = parsed["confidence"]
    rank = CONFIDENCE_RANK[conf]
    if rate >= 0.25:
        rank = max(rank - 2, 1)
    elif rate >= 0.10:
        rank = max(rank - 1, 1)
    new_conf = RANK_TO_CONFIDENCE[rank]
    if new_conf == "high":
        action = "switch"
    elif new_conf == "medium":
        action = "no_switch_with_exposure"
    else:
        action = "no_switch"
    return {
        "validated": {
            "to": to,
            "confidence": new_conf,
            "action": action,
        }
    }


# ---------------------------------------------------------------------------
# B4 validate_scenario_check(parsed, available_scenarios)
# ---------------------------------------------------------------------------
def B4_validate_scenario_check(
    parsed: dict[str, Any], available_scenarios: list[str]
) -> dict[str, Any]:
    """B4 — 场景白名单校验。target 不在白名单 → 警告，忽略切换。"""
    mode = parsed.get("mode", "ongoing")
    if mode == "initial":
        target = parsed.get("target", "")
        if target not in available_scenarios:
            warnings.warn(f"B4 initial target {target} not in whitelist")
            return {"validated": {"action": "stay", "target": target}}
        return {"validated": {"action": "switch", "target": target}}

    action = parsed.get("action", "stay")
    target = parsed.get("target", "")
    if action == "switch_to":
        if target not in available_scenarios:
            warnings.warn(f"B4 switch target {target} not in whitelist — ignored")
            return {"validated": {"action": "stay", "target": target}}
        return {"validated": {"action": "switch", "target": target}}
    return {"validated": {"action": "stay", "target": target}}