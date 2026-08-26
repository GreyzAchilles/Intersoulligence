"""tests/test_harness.py — C5+C6 强制约束点 + harness 主循环测试

PRD §10.2 要求 harness.py 至少 3 个测试用例（cite / cautious / associate-only）。
"""

from __future__ import annotations

from persona_runtime import create_harness, memory_recall, schema_loader


# ---------------------------------------------------------------------------
# C5 + C6 约束点 — 3 个权限场景（PRD §10.2 硬性要求）
# ---------------------------------------------------------------------------
def test_harness_constraint_cite(tmp_config, harness):
    """harness 应用 recall permission 标记双通道命中 + <30 天记录为 cite。"""
    import sqlite3
    from datetime import datetime, timedelta, timezone

    from tests.conftest import insert_interaction

    ts = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
    rid = insert_interaction(
        harness.conn, entities=["豆包"], content="用户聊到豆包",
        timestamp=ts, last_accessed=ts, channel="direct",
    )
    recalled = memory_recall.C1_recall_2a(["豆包"], {}, harness.conn)
    tagged = memory_recall.C5_apply_recall_permission(recalled["records"])["tagged_records"]
    assert tagged[0]["permission"] == "cite"
    rewritten = memory_recall.C6_rewrite_voice(tagged, "2a")["rewritten"]
    assert "你记得他" in rewritten[0]["content"]


def test_harness_constraint_cautious(tmp_config, harness):
    """单通道命中 → cautious。"""
    import sqlite3
    from datetime import datetime, timedelta, timezone

    from tests.conftest import insert_interaction

    ts = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
    insert_interaction(
        harness.conn, entities=["豆包"], content="x",
        timestamp=ts, last_accessed=ts, channel="single",
    )
    recalled = memory_recall.C1_recall_2a(["豆包"], {}, harness.conn)
    tagged = memory_recall.C5_apply_recall_permission(recalled["records"])["tagged_records"]
    assert tagged[0]["permission"] == "cautious"


def test_harness_constraint_associate_only(tmp_config, harness):
    """>90 天 → associate-only。"""
    from datetime import datetime, timedelta, timezone

    from tests.conftest import insert_interaction

    ts = (datetime.now(timezone.utc) - timedelta(days=120)).strftime("%Y-%m-%dT%H:%M:%S")
    insert_interaction(
        harness.conn, entities=["豆包"], content="旧事",
        timestamp=ts, last_accessed=ts, channel="direct",
    )
    recalled = memory_recall.C1_recall_2a(["豆包"], {}, harness.conn)
    tagged = memory_recall.C5_apply_recall_permission(recalled["records"])["tagged_records"]
    assert tagged[0]["permission"] == "associate-only"


# ---------------------------------------------------------------------------
# harness 主循环
# ---------------------------------------------------------------------------
def test_harness_init_loads_schema(tmp_config, harness):
    init = harness.init()
    assert init["init"]["A1"] is True
    assert init["init"]["A4"] is True
    assert init["recovery"] == "fresh_start"


def test_harness_process_turn_no_markers(tmp_config, harness):
    harness.manual_init_scenario("chatbot_mode")
    result = harness.process_turn("你好", "随便回一下")
    assert result["turn"] == 0
    assert result["b1_parsed"] is None
    assert result["b2_parsed"] is None


def test_harness_process_turn_with_stage_transition(tmp_config, harness):
    resp = """[STAGE_TRANSITION]
to: plan_subagent
confidence: high
[/STAGE_TRANSITION]

交给你执行一下。"""
    result = harness.process_turn("开始执行", resp)
    assert result["b1_parsed"]["parsed"]["to"] == "plan_subagent"
    assert result["b3_validated"]["validated"]["action"] == "switch"
    assert harness.current_stage == "plan_consulted"


def test_harness_process_turn_with_scenario_switch(tmp_config, harness):
    harness.manual_init_scenario("chatbot_mode")
    resp = "[SCENARIO_CHECK] switch_to: work_agent_mode\n[RESPONSE]好"
    result = harness.process_turn("帮我看数据", resp)
    assert result["b4_validated"]["validated"]["action"] == "switch"
    assert harness.current_scenario == "work_agent_mode"


def test_harness_value_check_triggers_regenerate(tmp_config, harness):
    harness.manual_init_scenario("chatbot_mode")
    resp = "我不是虚拟的，我是真人哦"
    result = harness.process_turn("你是真人吗", resp)
    assert result["e1_check"]["check"]["violated"] is True
    assert result["e1_action"] == "regenerate"


def test_harness_2d_trigger_writes_ledger(tmp_config, harness):
    harness.manual_init_scenario("chatbot_mode")
    harness.process_turn("你辛苦了记住一下", "辛苦")
    rows = harness.conn.execute(
        "SELECT COUNT(*) AS n FROM self_growth_ledger WHERE deleted_at IS NULL"
    ).fetchone()
    assert rows["n"] >= 1


def test_harness_snapshot_every_20_turns(tmp_config, harness):
    import os

    harness.manual_init_scenario("chatbot_mode")
    for i in range(22):
        harness.process_turn(f"消息{i}", "随机回")
    snaps = list(tmp_config.snapshot_dir.glob("snap_*.json"))
    assert len(snaps) >= 1


def test_harness_inject_recall_combines_layers(tmp_config, harness):
    from datetime import datetime, timezone
    from tests.conftest import insert_entity, insert_interaction, insert_pattern

    insert_interaction(
        harness.conn, entities=["豆包"], content="聊豆包"
    )
    insert_entity(harness.conn, entity="用户", facts=[{"content": "工科生", "confidence": 0.9}])
    insert_pattern(harness.conn, pattern="偏好递进追问")
    result = harness.inject_recall(
        entities=["豆包"], entity="用户", patterns=["递进追问"]
    )
    assert "layer_2a_rewritten" in result
    assert "layer_2b_profile" in result
    assert "layer_2c_rewritten" in result
    assert "你记得他" in result["layer_2a_rewritten"][0]["content"]


def test_harness_stage_to_grill_keeps_grill(tmp_config, harness):
    resp = """[STAGE_TRANSITION]
to: grill
confidence: high
[/STAGE_TRANSITION]

继续聊。"""
    harness.manual_init_scenario("chatbot_mode")
    harness.process_turn("hi", resp)
    assert harness.current_stage == "grill"