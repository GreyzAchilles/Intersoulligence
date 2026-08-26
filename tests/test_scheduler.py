"""tests/test_scheduler.py — G1, G4 调度类接口测试 (2 个)"""

from __future__ import annotations

from persona_runtime import scheduler


# ---------------------------------------------------------------------------
# G1 spawn_plan_subagent
# ---------------------------------------------------------------------------
def test_G1_spawns_returns_subagent_id():
    result = scheduler.G1_spawn_plan_subagent("grill output here")
    spawned = result["spawned"]
    assert spawned["subagent_id"].startswith("plan_subagent_")
    assert spawned["initial_state"] == "processing"
    assert "plan subagent" in spawned["injected_prompt"]


def test_G1_with_custom_rule():
    custom = "custom rule here"
    result = scheduler.G1_spawn_plan_subagent("x", injected_rule=custom)
    assert result["spawned"]["injected_prompt"] == custom


def test_G1_subagent_ids_unique():
    a = scheduler.G1_spawn_plan_subagent("x")
    b = scheduler.G1_spawn_plan_subagent("x")
    assert a["spawned"]["subagent_id"] != b["spawned"]["subagent_id"]


# ---------------------------------------------------------------------------
# G4 inject_plan_subagent_first_switch_rule
# ---------------------------------------------------------------------------
def test_G4_returns_first_switch_rule():
    result = scheduler.G4_inject_plan_subagent_first_switch_rule()
    rule = result["injected"]["rule"]
    assert "你是 plan subagent" in rule
    assert "grill agent 发布" in rule
    assert result["injected"]["permanent"] is True


def test_G4_rule_matches_v6_spec():
    """G4 注入文本须包含 v6 §10 的关键语句。"""
    result = scheduler.G4_inject_plan_subagent_first_switch_rule()
    rule = result["injected"]["rule"]
    assert "你是 plan subagent" in rule
    assert "你的所有产出都返回 grill agent" in rule
    assert "开始分发任务的指令只能由 grill agent 发布" in rule
    assert "你只处理任务并返回结果" in rule


def test_try_inject_with_retry_fallback():
    out = scheduler.try_inject_with_retry()
    assert "injected" in out