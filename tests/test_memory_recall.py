"""tests/test_memory_recall.py — C1-C6 召回类接口测试 (6 个)

含 C5 三档 permission（harness 约束核心）+ C6 语态改写。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from persona_runtime import memory_recall
from tests.conftest import insert_entity, insert_interaction, insert_pattern


# ---------------------------------------------------------------------------
# C1 recall_2a
# ---------------------------------------------------------------------------
def test_C1_recall_2a_filters_entities(conn):
    insert_interaction(conn, entities=["豆包"], content="用户聊到豆包")
    insert_interaction(conn, entities=["元宝"], content="用户聊到元宝")
    result = memory_recall.C1_recall_2a(["豆包"], {}, conn)
    assert len(result["records"]) == 1
    assert "豆包" in result["records"][0]["entities"]


def test_C1_recall_2a_updates_last_accessed(conn):
    old_ts = "2026-08-01T10:00:00"
    rid = insert_interaction(conn, entities=["x"], last_accessed=old_ts)
    memory_recall.C1_recall_2a(["x"], {}, conn)
    row = conn.execute("SELECT last_accessed FROM interaction_memory WHERE id = ?", (rid,)).fetchone()
    assert row["last_accessed"] != old_ts


def test_C1_recall_2a_empty_entities_returns_empty(conn):
    insert_interaction(conn, entities=["豆包"])
    result = memory_recall.C1_recall_2a([], {}, conn)
    assert result["records"] == []


def test_C1_recall_2a_skips_content_wiped(conn):
    insert_interaction(conn, entities=["x"], status="content_wiped")
    result = memory_recall.C1_recall_2a(["x"], {}, conn)
    assert len(result["records"]) == 0


def test_C1_recall_2a_filters_time_range(conn):
    insert_interaction(conn, entities=["x"], timestamp="2026-07-15T10:00:00")
    insert_interaction(conn, entities=["x"], timestamp="2026-08-14T10:00:00")
    result = memory_recall.C1_recall_2a(
        ["x"], {"from": "2026-08-01T00:00:00", "to": "2026-08-31T00:00:00"}, conn
    )
    assert len(result["records"]) == 1
    assert result["records"][0]["timestamp"] == "2026-08-14T10:00:00"


# ---------------------------------------------------------------------------
# C2 recall_2b
# ---------------------------------------------------------------------------
def test_C2_recall_2b_returns_existing(conn):
    insert_entity(
        conn, entity="用户",
        facts=[{"content": "工科生", "confidence": 0.9}],
        judgment=[{"content": "产品边界感很彻底", "timestamp": "2026-08-14T10:00:00"}],
    )
    result = memory_recall.C2_recall_2b("用户", conn)
    p = result["profile"]
    assert p["entity"] == "用户"
    assert p["facts"][0]["content"] == "工科生"
    assert "产品边界感" in p["judgment"][0]["content"]


def test_C2_recall_2b_missing_entity_returns_empty(conn):
    result = memory_recall.C2_recall_2b("不存在", conn)
    assert result["profile"]["entity"] == "不存在"
    assert result["profile"]["facts"] == []


# ---------------------------------------------------------------------------
# C3 recall_2c
# ---------------------------------------------------------------------------
def test_C3_recall_2c_with_patterns(conn):
    insert_pattern(conn, pattern="用户偏好递进追问")
    insert_pattern(conn, pattern="用户爱闲聊")
    result = memory_recall.C3_recall_2c(["递进追问"], conn)
    assert len(result["records"]) == 1
    assert "递进追问" in result["records"][0]["pattern"]


def test_C3_recall_2c_no_patterns_returns_all(conn):
    insert_pattern(conn, pattern="foo")
    insert_pattern(conn, pattern="bar")
    result = memory_recall.C3_recall_2c(None, conn)
    assert len(result["records"]) == 2


def test_C3_recall_2c_updates_last_accessed(conn):
    old_ts = "2026-07-29T10:00:00"
    insert_pattern(conn, pattern="x", last_accessed=old_ts)
    memory_recall.C3_recall_2c(None, conn)
    row = conn.execute(
        "SELECT last_accessed FROM long_term_patterns WHERE pattern = 'x'"
    ).fetchone()
    assert row["last_accessed"] != old_ts


# ---------------------------------------------------------------------------
# C4 recall_2d
# ---------------------------------------------------------------------------
def test_C4_recall_2d_recent_n(conn):
    from tests.conftest import insert_ledger

    insert_ledger(conn, change="c1", timestamp="2026-08-13T10:00:00")
    insert_ledger(conn, change="c2", timestamp="2026-08-14T10:00:00")
    result = memory_recall.C4_recall_2d(1, conn)
    assert len(result["records"]) == 1
    assert result["records"][0]["change"] == "c2"


def test_C4_recall_2d_recent_zero_returns_all(conn):
    from tests.conftest import insert_ledger

    insert_ledger(conn, change="c1")
    insert_ledger(conn, change="c2")
    result = memory_recall.C4_recall_2d(0, conn)
    assert len(result["records"]) == 2


def test_C4_recall_2d_negative_treated_as_zero(conn, recwarn):
    from tests.conftest import insert_ledger

    insert_ledger(conn, change="c1")
    result = memory_recall.C4_recall_2d(-3, conn)
    assert len(result["records"]) == 1
    assert len(recwarn) >= 1


# ---------------------------------------------------------------------------
# C5 apply_recall_permission (harness C5 约束核心)
# ---------------------------------------------------------------------------
def test_C5_cite_double_channel_recent():
    recent_ts = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
    records = [{"content": "x", "entities": ["a"], "channel": "direct", "timestamp": recent_ts}]
    result = memory_recall.C5_apply_recall_permission(records)
    tagged = result["tagged_records"][0]
    assert tagged["permission"] == "cite"


def test_C5_cautious_single_channel():
    recent_ts = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
    records = [{"content": "x", "channel": "single", "timestamp": recent_ts}]
    result = memory_recall.C5_apply_recall_permission(records)
    assert result["tagged_records"][0]["permission"] == "cautious"


def test_C5_associate_only_old_age():
    old_ts = (datetime.now(timezone.utc) - timedelta(days=120)).strftime("%Y-%m-%dT%H:%M:%S")
    records = [{"content": "x", "entities": ["a"], "channel": "direct", "timestamp": old_ts}]
    result = memory_recall.C5_apply_recall_permission(records)
    assert result["tagged_records"][0]["permission"] == "associate-only"


def test_C5_missing_channel_defaults_single(recwarn):
    recent_ts = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S")
    records = [{"content": "x", "timestamp": recent_ts}]
    result = memory_recall.C5_apply_recall_permission(records)
    assert result["tagged_records"][0]["permission"] == "cautious"


def test_C5_missing_timestamp_uses_now(recwarn):
    records = [{"content": "x", "entities": ["a"], "channel": "direct"}]
    result = memory_recall.C5_apply_recall_permission(records)
    assert result["tagged_records"][0]["permission"] in ("cite", "cautious")


def test_C5_cautious_30_to_90_days():
    ts = (datetime.now(timezone.utc) - timedelta(days=45)).strftime("%Y-%m-%dT%H:%M:%S")
    records = [{"content": "x", "entities": ["a"], "channel": "direct", "timestamp": ts}]
    result = memory_recall.C5_apply_recall_permission(records)
    assert result["tagged_records"][0]["permission"] == "cautious"


# ---------------------------------------------------------------------------
# C6 rewrite_voice (harness C6 约束)
# ---------------------------------------------------------------------------
def test_C6_rewrite_2a_third_person():
    records = [{"content": "今天吃了牛肉面", "entities": ["a"], "channel": "direct"}]
    result = memory_recall.C6_rewrite_voice(records, "2a")
    assert "你记得他" in result["rewritten"][0]["content"]


def test_C6_rewrite_2c_third_person():
    records = [{"pattern": "偏好递进追问"}]
    result = memory_recall.C6_rewrite_voice(records, "2c")
    assert "你注意到他" in result["rewritten"][0]["content"]


def test_C6_rewrite_2d_keeps_first_person():
    records = [{"change": "我语气更克制"}]
    result = memory_recall.C6_rewrite_voice(records, "2d")
    assert result["rewritten"][0]["content"] == "我语气更克制"


def test_C6_invalid_source_layer_skips(recwarn):
    result = memory_recall.C6_rewrite_voice([{"content": "x"}], "bad")
    assert result["rewritten"][0]["content"] == "x"