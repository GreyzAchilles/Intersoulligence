"""tests/test_memory_write.py — D6-D9 写入类接口测试 (4 个)

含 D9 字段分流 + D8 伦理约束（harness D8 约束核心）。
"""

from __future__ import annotations

import json

import pytest

from persona_runtime import memory_write
from tests.conftest import insert_entity, insert_interaction


# ---------------------------------------------------------------------------
# D6 append_2d_entry
# ---------------------------------------------------------------------------
def test_D6_append_writes_row(conn):
    result = memory_write.D6_append_2d_entry(
        conn, "语气更克制", "用户反馈我话太多", "Layer 1"
    )
    assert "appended" in result
    assert "id" in result["appended"]
    row = conn.execute(
        "SELECT change, reason, affected_layer FROM self_growth_ledger WHERE id = ?",
        (result["appended"]["id"],),
    ).fetchone()
    assert row["change"] == "语气更克制"


def test_D6_missing_required_refused():
    with pytest.raises(ValueError):
        memory_write.D6_append_2d_entry(conn=None, change="", reason="x", affected_layer="Layer 1")


def test_D6_protected_layer_refused():
    result = memory_write.D6_append_2d_entry(
        conn=None, change="x", reason="y", affected_layer="Layer 0.2"
    )
    assert result.get("refused") is True
    assert result["conflict_clauses"][0]["layer"] == "Layer 0"


def test_D6_strips_user_judgment_content(conn, recwarn):
    result = memory_write.D6_append_2d_entry(
        conn, "他喜欢甜食", "用户反馈", "Layer 1"
    )
    row = conn.execute(
        "SELECT change FROM self_growth_ledger WHERE id = ?",
        (result["appended"]["id"],),
    ).fetchone()
    assert "stripped" in row["change"]
    assert "他喜欢" not in row["change"]


def test_D6_explicit_timestamp_used(conn):
    result = memory_write.D6_append_2d_entry(
        conn, "x", "y", "Layer 1", timestamp="2026-01-01T00:00:00"
    )
    assert result["appended"]["timestamp"] == "2026-01-01T00:00:00"


# ---------------------------------------------------------------------------
# D7 maybe_2d_trigger
# ---------------------------------------------------------------------------
def test_D7_trigger_user_feedback():
    out = memory_write.D7_maybe_2d_trigger(
        {"user_message": "辛苦了这次", "ai_response": "好的", "turn": 1}
    )
    assert out["trigger"]["triggered"] is True
    assert out["trigger"]["reason"] == "user_feedback"


def test_D7_trigger_explicit_remember():
    out = memory_write.D7_maybe_2d_trigger(
        {"user_message": "记住一下", "ai_response": "好", "turn": 1}
    )
    assert out["trigger"]["triggered"] is True
    assert out["trigger"]["reason"] == "explicit_remember"


def test_D7_trigger_value_violation():
    out = memory_write.D7_maybe_2d_trigger(
        {"user_message": "hi", "ai_response": "", "value_violation_detected": True, "turn": 1}
    )
    assert out["trigger"]["triggered"] is True
    assert out["trigger"]["reason"] == "value_violation"


def test_D7_no_trigger_no_match():
    out = memory_write.D7_maybe_2d_trigger(
        {"user_message": "随便说", "ai_response": "hi", "turn": 1}
    )
    assert out["trigger"]["triggered"] is False


def test_D7_dedup_within_5_turns():
    state = {"last_trigger_map": {"user_feedback": 1}, "last_self_eval_turn": -999}
    out = memory_write.D7_maybe_2d_trigger(
        {"user_message": "辛苦了", "ai_response": "x", "turn": 3}, state
    )
    assert out["trigger"]["triggered"] is False
    assert "duplicate" in out["trigger"]["reason"]


def test_D7_dedup_self_eval_started():
    state = {"last_trigger_map": {}, "last_self_eval_turn": 2}
    out = memory_write.D7_maybe_2d_trigger(
        {"user_message": "辛苦了", "ai_response": "x", "turn": 4}, state
    )
    assert out["trigger"]["triggered"] is False
    assert "self-eval" in out["trigger"]["reason"]


def test_D7_repeated_keyword_above_threshold():
    state = {"keyword_counts": {"记住": 4}, "last_trigger_map": {}, "last_self_eval_turn": -999, "recent_turns": []}
    out = memory_write.D7_maybe_2d_trigger(
        {"user_message": "再记一下", "ai_response": "x", "turn": 5, "recent_5_turns": ["记一下"] * 3}, state
    )
    assert out["trigger"]["triggered"] is True
    assert out["trigger"]["reason"] == "repeated_command"


# ---------------------------------------------------------------------------
# D8 validate_2d_entry (harness D8 约束核心)
# ---------------------------------------------------------------------------
def test_D8_valid_entry_passes():
    result = memory_write.D8_validate_2d_entry(
        {"change": "更简洁", "reason": "用户反馈", "affected_layer": "Layer 1"}
    )
    assert result["validated"]["passed"] is True


def test_D8_protected_layer_rejected():
    result = memory_write.D8_validate_2d_entry(
        {"change": "x", "reason": "y", "affected_layer": "Layer 0.2"}
    )
    assert result["validated"]["passed"] is False
    assert result["validated"]["conflicts"][0]["layer"] == "Layer 0"


def test_D8_user_judgment_stripped():
    result = memory_write.D8_validate_2d_entry(
        {"change": "他喜欢随性", "reason": "ok", "affected_layer": "Layer 1"}
    )
    assert "change" in result["validated"]["stripped_sections"]
    assert result["validated"]["passed"] is False


def test_D8_missing_required():
    result = memory_write.D8_validate_2d_entry({"change": "", "reason": "", "affected_layer": ""})
    assert result["validated"]["passed"] is False


# ---------------------------------------------------------------------------
# D9 write_2b_entry (Layer 2b 字段分流核心)
# ---------------------------------------------------------------------------
def test_D9_overwrite_facts_creates_profile_if_missing(conn):
    result = memory_write.D9_write_2b_entry(
        conn, "新实体", "facts", "工科生", "overwrite"
    )
    assert result["written"]["entity"] == "新实体"
    row = conn.execute(
        "SELECT facts FROM entity_profile WHERE entity = '新实体'"
    ).fetchone()
    assert json.loads(row["facts"]) == ["工科生"]


def test_D9_facts_requires_overwrite(conn):
    with pytest.raises(ValueError):
        memory_write.D9_write_2b_entry(conn, "用户", "facts", "x", "append")


def test_D9_current_status_covering_update_replaces_old(conn):
    insert_entity(conn, entity="用户", current_status=[
        {"content": "旧", "timestamp": "2026-08-01T10:00:00"}
    ])
    memory_write.D9_write_2b_entry(
        conn, "用户", "current_status", {"content": "新", "timestamp": "2026-08-14T10:00:00"},
        "covering_update",
    )
    row = conn.execute(
        "SELECT current_status FROM entity_profile WHERE entity = '用户'"
    ).fetchone()
    statuses = json.loads(row["current_status"])
    assert len(statuses) == 1
    assert statuses[0]["content"] == "新"


def test_D9_judgment_append_keeps_history(conn):
    insert_entity(conn, entity="用户", judgment=[
        {"content": "old impression", "timestamp": "2026-08-01T10:00:00"}
    ])
    memory_write.D9_write_2b_entry(
        conn, "用户", "judgment", {"content": "new impression", "timestamp": "2026-08-14T10:00:00"},
        "append",
    )
    row = conn.execute(
        "SELECT judgment FROM entity_profile WHERE entity = '用户'"
    ).fetchone()
    judgments = json.loads(row["judgment"])
    assert len(judgments) == 2
    assert judgments[0]["content"] == "old impression"
    assert judgments[1]["content"] == "new impression"


def test_D9_judgment_requires_append(conn):
    with pytest.raises(ValueError):
        memory_write.D9_write_2b_entry(conn, "x", "judgment", "y", "overwrite")


def test_D9_unknown_field_refused(conn):
    with pytest.raises(ValueError):
        memory_write.D9_write_2b_entry(conn, "x", "nope", "y", "overwrite")


def test_D9_unknown_mode_refused(conn):
    with pytest.raises(ValueError):
        memory_write.D9_write_2b_entry(conn, "x", "facts", "y", "wrong_mode")