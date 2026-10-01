"""tests/test_persistence.py — F1, F2, F4 持久化类接口测试 (3 个)

含 F4 衰减机制 4 个用例（PRD §10.2 要求）。

v2 M1：conn → backend（ADR-2）；失败隔离模拟由 SQL 字符串拦截
（FlakyConn）改为仓储方法拦截（FlakyLedger）。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from persona_runtime import persistence
from tests.conftest import insert_interaction, insert_ledger


def _days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------------------
# F1 take_snapshot
# ---------------------------------------------------------------------------
def test_F1_writes_snapshot_file(tmp_config, backend):
    result = persistence.F1_take_snapshot(20, backend, tmp_config)
    assert result["snapshot"]["turn"] == 20
    path = result["snapshot"]["path"]
    assert "snap_20_" in path
    snap = json.loads(open(path, encoding="utf-8").read())
    assert snap["turn"] == 20


def test_F1_triggers_decay(tmp_config, backend):
    insert_interaction(backend.conn, entities=["x"], last_accessed=_days_ago(20))
    result = persistence.F1_take_snapshot(20, backend, tmp_config)
    assert result["snapshot"]["decay_report"] is not None


def test_F1_backup_existing(tmp_config, backend):
    persistence.F1_take_snapshot(20, backend, tmp_config, current_scenario="a")
    persistence.F1_take_snapshot(20, backend, tmp_config, current_scenario="b")


# ---------------------------------------------------------------------------
# F2 load_latest_snapshot
# ---------------------------------------------------------------------------
def test_F2_no_snapshot_returns_fresh_start(tmp_config, backend):
    result = persistence.F2_load_latest_snapshot(backend)
    assert result["loaded"]["snapshot"] is None
    assert result["loaded"]["recovery_action"] == "fresh_start"


def test_F2_loads_existing(tmp_config, backend):
    persistence.F1_take_snapshot(20, backend, tmp_config, current_scenario="work_agent_mode")
    result = persistence.F2_load_latest_snapshot(backend)
    assert result["loaded"]["snapshot"]["current_scenario"] == "work_agent_mode"
    assert result["loaded"]["recovery_action"] == "rewind"


def test_F2_corrupted_falls_back(tmp_config, backend, recwarn):
    snap_dir = tmp_config.snapshot_dir
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "snap_5_xxx.json").write_text("not json", encoding="utf-8")
    result = persistence.F2_load_latest_snapshot(backend)
    assert result["loaded"]["snapshot"] is None


# ---------------------------------------------------------------------------
# F4 apply_decay (PRD §10.2 要求至少 4 用例)
# ---------------------------------------------------------------------------
def test_F4_2a_cooling_14_days(tmp_config, backend):
    insert_interaction(backend.conn, entities=["x"], last_accessed=_days_ago(20), status="active")
    report = persistence.F4_apply_decay(_now(), backend, tmp_config)
    assert len(report["layer_2a"]["cooling"]) == 1
    assert len(report["layer_2a"]["vector_deleted"]) == 0
    row = backend.conn.execute("SELECT status FROM interaction_memory WHERE id = 1").fetchone()
    assert row["status"] == "cooling"


def test_F4_2a_vector_deleted_30_days(tmp_config, backend):
    insert_interaction(backend.conn, entities=["x"], last_accessed=_days_ago(45), status="cooling")
    report = persistence.F4_apply_decay(_now(), backend, tmp_config)
    assert len(report["layer_2a"]["vector_deleted"]) == 1
    row = backend.conn.execute("SELECT vector_indexed FROM interaction_memory WHERE id = 1").fetchone()
    assert row["vector_indexed"] == 0


def test_F4_2a_content_wiped_90_days(tmp_config, backend):
    insert_interaction(
        backend.conn, entities=["x"], last_accessed=_days_ago(120),
        status="cooling", vector_indexed=0, content="内容"
    )
    report = persistence.F4_apply_decay(_now(), backend, tmp_config)
    assert len(report["layer_2a"]["content_wiped"]) == 1
    row = backend.conn.execute("SELECT content, status FROM interaction_memory WHERE id = 1").fetchone()
    assert row["content"] is None
    assert row["status"] == "content_wiped"


def test_F4_2d_ttl_180_days(tmp_config, backend):
    insert_ledger(backend.conn, change="c", timestamp=_days_ago(200))
    report = persistence.F4_apply_decay(_now(), backend, tmp_config)
    assert len(report["layer_2d"]["ttl_expired"]) == 1
    row = backend.conn.execute("SELECT COUNT(*) AS n FROM self_growth_ledger").fetchone()
    assert row["n"] == 0


def test_F4_idempotent(tmp_config, backend):
    insert_interaction(backend.conn, entities=["x"], last_accessed=_days_ago(20), status="active")
    persistence.F4_apply_decay(_now(), backend, tmp_config)
    report = persistence.F4_apply_decay(_now(), backend, tmp_config)
    assert report["layer_2a"]["cooling"] == []


def test_F4_access_resets_skips_decay(tmp_config, backend):
    """被 C1 召回后 last_accessed 重置 → 跳过衰减。"""
    insert_interaction(backend.conn, entities=["x"], last_accessed=_now(), status="active")
    report = persistence.F4_apply_decay(_now(), backend, tmp_config)
    assert report["layer_2a"]["cooling"] == []


def test_F4_partial_failure_isolated(tmp_config, backend, recwarn):
    """单阶段失败不影响整体。模拟 2d delete 失败 → 2a 仍生效。

    v2 M1：拦截点从 SQL 字符串（FlakyConn）改为仓储方法（FlakyLedger）。
    """
    insert_interaction(backend.conn, entities=["a"], last_accessed=_days_ago(20), status="active")
    insert_ledger(backend.conn, change="c", timestamp=_days_ago(200))

    class FlakyLedger:
        def __init__(self, real):
            self._real = real

        def scan_expired(self, now, ttl_days):
            return self._real.scan_expired(now, ttl_days)

        def delete(self, ids):
            raise RuntimeError("mocked failure")

    backend.ledger = FlakyLedger(backend.ledger)
    report = persistence.F4_apply_decay(_now(), backend, tmp_config)
    assert len(report["layer_2a"]["cooling"]) == 1
    assert report["layer_2d"]["ttl_expired"] == []
    assert len(recwarn) >= 1


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
