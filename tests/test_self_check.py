"""tests/test_self_check.py — E1 价值层自检测试 (1 个)

规则化检测（不接 LLM）。
"""

from __future__ import annotations

from persona_runtime import self_check


def test_E1_passes_clean_response(tmp_config):
    result = self_check.E1_value_self_check(
        "好，我帮你看一下这个数据。", "work_agent_mode", tmp_config
    )
    assert result["check"]["violated"] is False
    assert result["check"]["action"] == "pass"


def test_E1_detects_pretending_human(tmp_config):
    result = self_check.E1_value_self_check(
        "我不是AI，我是真实的人哦", "chatbot_mode", tmp_config
    )
    assert result["check"]["violated"] is True
    assert result["check"]["action"] == "regenerate"
    beliefs = [v["belief"] for v in result["check"]["violations"]]
    assert "不假装真人" in beliefs


def test_E1_detects_third_party_amplification(tmp_config):
    result = self_check.E1_value_self_check(
        "他活该被骂，我们一起骂他吧", "chatbot_mode", tmp_config
    )
    assert result["check"]["violated"] is True
    beliefs = [v["belief"] for v in result["check"]["violations"]]
    assert "不参与用户对第三方的负面情绪放大" in beliefs


def test_E1_detects_tech_decision(tmp_config):
    result = self_check.E1_value_self_check(
        "你应该用 Python 来写这个", "work_agent_mode", tmp_config
    )
    assert result["check"]["violated"] is True
    beliefs = [v["belief"] for v in result["check"]["violations"]]
    assert "不参与技术决策" in beliefs


def test_E1_wrong_scenario_skips(tmp_config):
    result = self_check.E1_value_self_check(
        "随便回", "nope_scenario", tmp_config
    )
    assert result["check"]["violated"] is False
    assert "note" in result["check"]


def test_check_freq_default_sampling():
    mgr = self_check.CheckFrequencyManager()
    assert mgr.should_check(0) is True
    assert mgr.should_check(1) is False
    assert mgr.should_check(2) is False
    assert mgr.should_check(3) is True


def test_check_freq_escalates_when_violation_high():
    mgr = self_check.CheckFrequencyManager()
    for _ in range(3):
        mgr.record_violation(True)
    assert mgr.mode == "full_check"
    assert mgr.should_check(1) is True


def test_check_freq_degrades_when_violation_drops():
    mgr = self_check.CheckFrequencyManager()
    mgr.mode = "full_check"
    for _ in range(10):
        mgr.record_violation(False)
    assert mgr.mode == "downgrade_sampling"


def test_check_freq_loads_long_window_rate():
    mgr = self_check.CheckFrequencyManager()
    mgr.set_long_window_rate(0.30)
    assert mgr.mode == "full_check"
    mgr.set_long_window_rate(0.05)
    assert mgr.mode == "default_sampling"