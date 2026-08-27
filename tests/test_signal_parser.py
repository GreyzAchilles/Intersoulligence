"""tests/test_signal_parser.py — B1-B4 解析类接口测试 (4 个)

覆盖阶段切换信号 + 场景自检信号的解析与校验。
"""

from __future__ import annotations

from persona_runtime import signal_parser


# ---------------------------------------------------------------------------
# B1 parse_stage_transition
# ---------------------------------------------------------------------------
def test_B1_parses_high_confidence():
    resp = """[STAGE_TRANSITION]
to: plan_subagent
confidence: high
[/STAGE_TRANSITION]

我大概理解了，让我把它交给 plan 那边。"""
    out = signal_parser.B1_parse_stage_transition(resp)
    assert out == {"parsed": {"to": "plan_subagent", "confidence": "high"}}


def test_B1_parses_low_confidence():
    resp = "[STAGE_TRANSITION]\nto: grill\nconfidence: low\n[/STAGE_TRANSITION]"
    assert signal_parser.B1_parse_stage_transition(resp) == {
        "parsed": {"to": "grill", "confidence": "low"}
    }


def test_B1_missing_returns_none():
    assert signal_parser.B1_parse_stage_transition("no markers") is None


def test_B1_invalid_to_ignored(recwarn):
    resp = "[STAGE_TRANSITION]\nto: invalid_stage\nconfidence: high\n[/STAGE_TRANSITION]"
    assert signal_parser.B1_parse_stage_transition(resp) is None
    assert len(recwarn) >= 1


def test_B1_multiple_takes_last():
    resp = (
        "[STAGE_TRANSITION]\nto: grill\nconfidence: low\n[/STAGE_TRANSITION]\n"
        "[STAGE_TRANSITION]\nto: plan_subagent\nconfidence: high\n[/STAGE_TRANSITION]"
    )
    out = signal_parser.B1_parse_stage_transition(resp)
    assert out["parsed"]["to"] == "plan_subagent"


# ---------------------------------------------------------------------------
# B1 dict（tool call 参数）输入 — 问题 2 结构化输出
# ---------------------------------------------------------------------------
def test_B1_parses_tool_call_dict():
    out = signal_parser.B1_parse_stage_transition(
        {"to": "plan_subagent", "confidence": "high"}
    )
    assert out == {"parsed": {"to": "plan_subagent", "confidence": "high"}}


def test_B1_tool_call_dict_equals_string_result():
    d = signal_parser.B1_parse_stage_transition(
        {"to": "grill", "confidence": "low"}
    )
    s = signal_parser.B1_parse_stage_transition(
        "[STAGE_TRANSITION]\nto: grill\nconfidence: low\n[/STAGE_TRANSITION]"
    )
    assert d == s


def test_B1_tool_call_invalid_to_ignored(recwarn):
    out = signal_parser.B1_parse_stage_transition(
        {"to": "invalid_stage", "confidence": "high"}
    )
    assert out is None
    assert len(recwarn) >= 1


def test_B1_tool_call_invalid_confidence_ignored(recwarn):
    out = signal_parser.B1_parse_stage_transition(
        {"to": "grill", "confidence": "uber"}
    )
    assert out is None
    assert len(recwarn) >= 1


def test_B1_none_returns_none():
    assert signal_parser.B1_parse_stage_transition(None) is None


# ---------------------------------------------------------------------------
# B2 parse_scenario_check
# ---------------------------------------------------------------------------
def test_B2_parses_initial():
    resp = "[SCENARIO_CHECK] initial: work_agent_mode\n[RESPONSE]好的"
    out = signal_parser.B2_parse_scenario_check(resp)
    assert out["parsed"]["mode"] == "initial"
    assert out["parsed"]["target"] == "work_agent_mode"


def test_B2_parses_switch_to():
    resp = "[SCENARIO_CHECK] switch_to: work_agent_mode\n[RESPONSE]好的"
    out = signal_parser.B2_parse_scenario_check(resp)
    assert out["parsed"]["action"] == "switch_to"
    assert out["parsed"]["target"] == "work_agent_mode"


def test_B2_parses_stay():
    resp = "[SCENARIO_CHECK] stay: chatbot_mode\n[RESPONSE]好的"
    out = signal_parser.B2_parse_scenario_check(resp)
    assert out["parsed"]["action"] == "stay"


def test_B2_missing_returns_none():
    assert signal_parser.B2_parse_scenario_check("no markers") is None


def test_B2_switch_without_target_ignored(recwarn):
    resp = "[SCENARIO_CHECK] switch_to:\n[RESPONSE]好的"
    assert signal_parser.B2_parse_scenario_check(resp) is None


# ---------------------------------------------------------------------------
# B2 dict（tool call 参数）输入 — 问题 2 结构化输出
# ---------------------------------------------------------------------------
def test_B2_parses_tool_call_initial():
    out = signal_parser.B2_parse_scenario_check(
        {"mode": "initial", "target": "chatbot_mode"}
    )
    assert out["parsed"]["mode"] == "initial"
    assert out["parsed"]["action"] == "initial"
    assert out["parsed"]["target"] == "chatbot_mode"


def test_B2_parses_tool_call_switch_to():
    out = signal_parser.B2_parse_scenario_check(
        {"mode": "switch_to", "target": "work_agent_mode"}
    )
    assert out["parsed"]["action"] == "switch_to"
    assert out["parsed"]["target"] == "work_agent_mode"


def test_B2_parses_tool_call_stay():
    out = signal_parser.B2_parse_scenario_check({"mode": "stay", "target": ""})
    assert out["parsed"]["action"] == "stay"


def test_B2_tool_call_switch_without_target_ignored(recwarn):
    out = signal_parser.B2_parse_scenario_check(
        {"mode": "switch_to", "target": ""}
    )
    assert out is None
    assert len(recwarn) >= 1


def test_B2_tool_call_invalid_mode_ignored(recwarn):
    out = signal_parser.B2_parse_scenario_check(
        {"mode": "nope", "target": "chatbot_mode"}
    )
    assert out is None


def test_B2_tool_call_initial_without_target_ignored(recwarn):
    out = signal_parser.B2_parse_scenario_check({"mode": "initial", "target": ""})
    assert out is None
    assert len(recwarn) >= 1


def test_B2_none_returns_none():
    assert signal_parser.B2_parse_scenario_check(None) is None


def test_B2_tool_call_dict_equals_string_result():
    d = signal_parser.B2_parse_scenario_check(
        {"mode": "switch_to", "target": "work_agent_mode"}
    )
    s = signal_parser.B2_parse_scenario_check(
        "[SCENARIO_CHECK] switch_to: work_agent_mode\n[RESPONSE]好的"
    )
    assert d == s


# ---------------------------------------------------------------------------
# B3 validate_stage_transition
# ---------------------------------------------------------------------------
def test_B3_no_degradation_when_low_rate():
    parsed = {"to": "plan_subagent", "confidence": "high"}
    state = {"long_window_violation_rate": 0.05}
    out = signal_parser.B3_validate_stage_transition(parsed, state)
    assert out["validated"]["confidence"] == "high"
    assert out["validated"]["action"] == "switch"


def test_B3_degrade_one_at_10pct():
    parsed = {"to": "plan_subagent", "confidence": "high"}
    state = {"long_window_violation_rate": 0.10}
    out = signal_parser.B3_validate_stage_transition(parsed, state)
    assert out["validated"]["confidence"] == "medium"
    assert out["validated"]["action"] == "no_switch_with_exposure"


def test_B3_degrade_two_at_25pct():
    parsed = {"to": "plan_subagent", "confidence": "high"}
    state = {"long_window_violation_rate": 0.25}
    out = signal_parser.B3_validate_stage_transition(parsed, state)
    assert out["validated"]["confidence"] == "low"
    assert out["validated"]["action"] == "no_switch"


def test_B3_low_stays_low():
    parsed = {"to": "grill", "confidence": "low"}
    state = {"long_window_violation_rate": 0.25}
    out = signal_parser.B3_validate_stage_transition(parsed, state)
    assert out["validated"]["confidence"] == "low"


# ---------------------------------------------------------------------------
# B4 validate_scenario_check
# ---------------------------------------------------------------------------
def test_B4_target_in_whitelist_switches():
    parsed = {"mode": "ongoing", "action": "switch_to", "target": "work_agent_mode"}
    out = signal_parser.B4_validate_scenario_check(parsed, ["chatbot_mode", "work_agent_mode"])
    assert out["validated"]["action"] == "switch"


def test_B4_target_not_in_whitelist_stays(recwarn):
    parsed = {"mode": "ongoing", "action": "switch_to", "target": "nope"}
    out = signal_parser.B4_validate_scenario_check(parsed, ["chatbot_mode"])
    assert out["validated"]["action"] == "stay"


def test_B4_initial_target_in_whitelist_switches():
    parsed = {"mode": "initial", "action": "initial", "target": "chatbot_mode"}
    out = signal_parser.B4_validate_scenario_check(parsed, ["chatbot_mode", "work_agent_mode"])
    assert out["validated"]["action"] == "switch"


def test_B4_stay_action_keeps():
    parsed = {"mode": "ongoing", "action": "stay", "target": "chatbot_mode"}
    out = signal_parser.B4_validate_scenario_check(parsed, ["chatbot_mode"])
    assert out["validated"]["action"] == "stay"