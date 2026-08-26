"""tests/test_persistence.py — F1, F2, F4 持久化类接口测试 (3 个)

含 F4 衰减机制 4 个用例（PRD §10.2 要求）。
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
def test_F1_writes_snapshot_file(tmp_config, conn):
    result = persistence.F1_take_snapshot(20, conn, tmp_config)
    assert result["snapshot"]["turn"] == 20
    path = result["snapshot"]["path"]
    assert "snap_20_" in path
    snap = json.loads(open(path, encoding="utf-8").read())
    assert snap["turn"] == 20


def test_F1_triggers_decay(tmp_config, conn):
    insert_interaction(conn, entities=["x"], last_accessed=_days_ago(20))
    result = persistence.F1_take_snapshot(20, conn, tmp_config)
    assert result["snapshot"]["decay_report"] is not None


def test_F1_backup_existing(tmp_config, conn):
    persistence.F1_take_snapshot(20, conn, tmp_config, current_scenario="a")
    persistence.F1_take_snapshot(20, conn, tmp_config, current_scenario="b")


# ---------------------------------------------------------------------------
# F2 load_latest_snapshot
# ---------------------------------------------------------------------------
def test_F2_no_snapshot_returns_fresh_start(tmp_config):
    result = persistence.F2_load_latest_snapshot(tmp_config)
    assert result["loaded"]["snapshot"] is None
    assert result["loaded"]["recovery_action"] == "fresh_start"


def test_F2_loads_existing(tmp_config, conn):
    persistence.F1_take_snapshot(20, conn, tmp_config, current_scenario="work_agent_mode")
    result = persistence.F2_load_latest_snapshot(tmp_config)
    assert result["loaded"]["snapshot"]["current_scenario"] == "work_agent_mode"
    assert result["loaded"]["recovery_action"] == "rewind"


def test_F2_corrupted_falls_back(tmp_config, conn, recwarn):
    snap_dir = tmp_config.snapshot_dir
    snap_dir.mkdir(parents=True, exist_ok=True)
    (snap_dir / "snap_5_xxx.json").write_text("not json", encoding="utf-8")
    result = persistence.F2_load_latest_snapshot(tmp_config)
    assert result["loaded"]["snapshot"] is None


# ---------------------------------------------------------------------------
# F4 apply_decay (PRD §10.2 要求至少 4 用例)
# ---------------------------------------------------------------------------
def test_F4_2a_cooling_14_days(tmp_config, conn):
    insert_interaction(conn, entities=["x"], last_accessed=_days_ago(20), status="active")
    report = persistence.F4_apply_decay(_now(), conn, tmp_config)
    assert len(report["layer_2a"]["cooling"]) == 1
    assert len(report["layer_2a"]["vector_deleted"]) == 0
    row = conn.execute("SELECT status FROM interaction_memory WHERE id = 1").fetchone()
    assert row["status"] == "cooling"


def test_F4_2a_vector_deleted_30_days(tmp_config, conn):
    insert_interaction(conn, entities=["x"], last_accessed=_days_ago(45), status="cooling")
    report = persistence.F4_apply_decay(_now(), conn, tmp_config)
    assert len(report["layer_2a"]["vector_deleted"]) == 1
    row = conn.execute("SELECT vector_indexed FROM interaction_memory WHERE id = 1").fetchone()
    assert row["vector_indexed"] == 0


def test_F4_2a_content_wiped_90_days(tmp_config, conn):
    insert_interaction(
        conn, entities=["x"], last_accessed=_days_ago(120),
        status="cooling", vector_indexed=0, content="内容"
    )
    report = persistence.F4_apply_decay(_now(), conn, tmp_config)
    assert len(report["layer_2a"]["content_wiped"]) == 1
    row = conn.execute("SELECT content, status FROM interaction_memory WHERE id = 1").fetchone()
    assert row["content"] is None
    assert row["status"] == "content_wiped"


def test_F4_2d_ttl_180_days(tmp_config, conn):
    insert_ledger(conn, change="c", timestamp=_days_ago(200))
    report = persistence.F4_apply_decay(_now(), conn, tmp_config)
    assert len(report["layer_2d"]["ttl_expired"]) == 1
    row = conn.execute("SELECT COUNT(*) AS n FROM self_growth_ledger").fetchone()
    assert row["n"] == 0


def test_F4_idempotent(tmp_config, conn):
    insert_interaction(conn, entities=["x"], last_accessed=_days_ago(20), status="active")
    persistence.F4_apply_decay(_now(), conn, tmp_config)
    report = persistence.F4_apply_decay(_now(), conn, tmp_config)
    assert report["layer_2a"]["cooling"] == []


def test_F4_access_resets_skips_decay(tmp_config, conn):
    """被 C1 召回后 last_accessed 重置 → 跳过衰减。"""
    insert_interaction(conn, entities=["x"], last_accessed=_now(), status="active")
    report = persistence.F4_apply_decay(_now(), conn, tmp_config)
    assert report["layer_2a"]["cooling"] == []


def test_F4_partial_failure_isolated(tmp_config, conn, recwarn, monkeypatch):
    """单条失败不影响整体。模拟 2d delete 失败 → 2a 仍生效。

    sqlite3.Connection.execute 是只读属性，无法直接 setattr。
    改为对 persistence 模块 monkeypatch：
    在 2d 衰减阶段调用 conn.execute 路径之前注入一个 wrapper 类。
    """
    insert_interaction(conn, entities=["a"], last_accessed=_days_ago(20), status="active")

    class FlakyConn:
        def __init__(self, real):
            self._real = real

        def execute(self, sql, params=()):
            if "DELETE FROM self_growth_ledger" in sql:
                raise RuntimeError("mocked failure")
            return self._real.execute(sql, params)

        def executemany(self, sql, params):
            if "DELETE FROM self_growth_ledger" in sql:
                raise RuntimeError("mocked failure")
            return self._real.executemany(sql, params)

        def commit(self):
            return self._real.commit()

    original_connect = tmp_config
    flaky = FlakyConn(conn)

    class FakePersistence:
        pass

    # 调用 F4 时直接拿 conn 替身
    insert_ledger(conn, change="c", timestamp=_days_ago(200))
    report = persistence.F4_apply_decay(_now(), flaky, tmp_config)
    assert len(report["layer_2a"]["cooling"]) == 1
    assert len(recwarn) >= 1


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")