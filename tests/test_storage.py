"""tests/test_storage.py — StorageBackend 契约单测（v2 M1，ADR-2）

验证 SQLite 参考实现满足端口契约 + 方言移植点行为：
统一行协议、Python 侧时间戳、语义查找方法、快照存储转正、EmbeddingProvider 接口。
"""

from __future__ import annotations

import pytest

from persona_runtime.storage import (
    EmbeddingProvider,
    FileSnapshotStore,
    SQLiteStorage,
    StorageBackend,
    StorageNotSupported,
    utc_now_iso,
)


# ---------------------------------------------------------------------------
# 聚合根
# ---------------------------------------------------------------------------
def test_sqlite_storage_satisfies_backend_protocol(backend):
    assert isinstance(backend, StorageBackend)


def test_from_config_creates_schema_and_is_idempotent(tmp_config):
    b1 = SQLiteStorage.from_config(tmp_config)
    try:
        b2 = SQLiteStorage.from_config(tmp_config)
        b2.close()
    finally:
        b1.close()


# ---------------------------------------------------------------------------
# InteractionRepo（2a）
# ---------------------------------------------------------------------------
def test_interaction_append_and_find_roundtrip(backend):
    rid = backend.interactions.append_entry(
        {
            "content": "用户聊到豆包",
            "type": "observation",
            "source_conversation": "conv_1",
            "timestamp": "2026-08-14T10:00:00",
            "entities": ["豆包"],
        }
    )
    assert isinstance(rid, int)
    records = backend.interactions.find_by_entities(["豆包"], None)
    assert len(records) == 1
    rec = records[0]
    # 统一行协议：列名改名 + JSON 解码
    assert rec["id"] == rid
    assert rec["source_conversation"] == "conv_1"
    assert rec["entities"] == ["豆包"]
    assert rec["channel"] == "direct"
    assert rec["status"] == "active"
    assert rec["last_accessed"] == "2026-08-14T10:00:00"


def test_interaction_append_batch_is_atomic(backend):
    entries = [
        {"content": f"事实{i}", "type": "observation", "timestamp": "2026-08-14T10:00:00"}
        for i in range(3)
    ]
    # 中间夹一条缺 type 的坏数据 → 整批回滚
    entries.insert(1, {"content": "坏数据", "timestamp": "2026-08-14T10:00:00"})
    with pytest.raises(Exception):
        backend.interactions.append_batch(entries)
    assert backend.interactions.find_by_entities(["豆包"], None) == []


def test_interaction_find_excludes_content_wiped(backend):
    backend.interactions.append_entry(
        {"content": "旧", "type": "event", "timestamp": "2026-08-14T10:00:00",
         "entities": ["x"], "status": "content_wiped"}
    )
    assert backend.interactions.find_by_entities(["x"], None) == []


def test_interaction_find_time_range(backend):
    backend.interactions.append_entry(
        {"content": "七月", "type": "event", "timestamp": "2026-07-15T10:00:00", "entities": ["x"]}
    )
    backend.interactions.append_entry(
        {"content": "八月", "type": "event", "timestamp": "2026-08-14T10:00:00", "entities": ["x"]}
    )
    records = backend.interactions.find_by_entities(
        ["x"], {"from": "2026-08-01T00:00:00", "to": "2026-08-31T00:00:00"}
    )
    assert [r["content"] for r in records] == ["八月"]


def test_interaction_touch_access(backend):
    rid = backend.interactions.append_entry(
        {"content": "x", "type": "event", "timestamp": "2026-08-14T10:00:00", "entities": ["x"]}
    )
    now = utc_now_iso()
    backend.interactions.touch_access([rid], now)
    rec = backend.interactions.find_by_entities(["x"], None)[0]
    assert rec["last_accessed"] == now


def test_interaction_find_similar_not_supported(tmp_config):
    no_vec = SQLiteStorage.from_config(tmp_config, embedding_provider=None)
    try:
        with pytest.raises(StorageNotSupported):
            no_vec.interactions.find_similar([0.1, 0.2], top_k=3)
    finally:
        no_vec.close()


# ---------------------------------------------------------------------------
# EntityRepo（2b）
# ---------------------------------------------------------------------------
def test_entity_get_missing_returns_none(backend):
    assert backend.entities.get("不存在") is None


def test_entity_ensure_get_set_field_roundtrip(backend):
    now = utc_now_iso()
    backend.entities.ensure("用户", now)
    assert backend.entities.get_field("用户", "facts") == []
    backend.entities.set_field("用户", "facts", [{"content": "工科生"}], now)
    profile = backend.entities.get("用户")
    assert profile["facts"][0]["content"] == "工科生"
    assert profile["updated_at"] == now


def test_entity_unknown_field_refused(backend):
    with pytest.raises(ValueError):
        backend.entities.get_field("用户", "nope")
    with pytest.raises(ValueError):
        backend.entities.set_field("用户", "nope", [], utc_now_iso())


# ---------------------------------------------------------------------------
# PatternRepo（2c）
# ---------------------------------------------------------------------------
def test_pattern_insert_query_substring_match(backend):
    backend.patterns.insert_pattern("用户偏好递进追问", 0.5, "2026-07-29T10:00:00", "2026-08-13T10:00:00")
    backend.patterns.insert_pattern("用户爱闲聊", 0.4, "2026-07-29T10:00:00", "2026-08-13T10:00:00")
    records = backend.patterns.query(["递进追问"])
    assert len(records) == 1
    assert "递进追问" in records[0]["pattern"]
    assert len(backend.patterns.query(None)) == 2


def test_pattern_touch_access(backend):
    backend.patterns.insert_pattern("x", 0.5, "2026-07-29T10:00:00", "2026-08-13T10:00:00")
    now = utc_now_iso()
    rec = backend.patterns.query(None)[0]
    backend.patterns.touch_access([rec["id"]], now)
    assert backend.patterns.query(None)[0]["last_accessed"] == now


def test_pattern_duplicate_refused(backend):
    backend.patterns.insert_pattern("x", 0.5, "2026-07-29T10:00:00", "2026-08-13T10:00:00")
    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        backend.patterns.insert_pattern("x", 0.6, "2026-07-29T10:00:00", "2026-08-13T10:00:00")


# ---------------------------------------------------------------------------
# LedgerRepo（2d）
# ---------------------------------------------------------------------------
def test_ledger_append_and_recent(backend):
    backend.ledger.append({"change": "c1", "reason": "r", "affected_layer": "Layer 1",
                           "timestamp": "2026-08-13T10:00:00"})
    backend.ledger.append({"change": "c2", "reason": "r", "affected_layer": "Layer 1",
                           "timestamp": "2026-08-14T10:00:00"})
    records = backend.ledger.recent(1)
    assert len(records) == 1
    assert records[0]["change"] == "c2"
    assert records[0]["reversible"] is True
    assert len(backend.ledger.recent(0)) == 2


def test_ledger_scan_expired_python_side_threshold(backend):
    backend.ledger.append({"change": "old", "reason": "r", "affected_layer": "Layer 1",
                           "timestamp": "2026-01-01T00:00:00"})
    backend.ledger.append({"change": "new", "reason": "r", "affected_layer": "Layer 1",
                           "timestamp": utc_now_iso()})
    expired = backend.ledger.scan_expired(utc_now_iso(), 180)
    assert len(expired) == 1
    backend.ledger.delete(expired)
    assert len(backend.ledger.recent(0)) == 1


# ---------------------------------------------------------------------------
# SnapshotStore（F1/F2 文件实现转正）
# ---------------------------------------------------------------------------
def test_snapshot_store_roundtrip(tmp_path):
    store = FileSnapshotStore(tmp_path / "snapshots")
    snap = {"id": "snap_20_x", "turn": 20, "current_stage": "grill"}
    path = store.save(snap)
    assert path.endswith("snap_20_x.json")
    loaded = store.load_latest()
    assert loaded["turn"] == 20


def test_snapshot_store_backup_on_conflict(tmp_path):
    import os

    store = FileSnapshotStore(tmp_path / "snapshots")
    store.save({"id": "snap_20_x", "turn": 20})
    # 快照 id 相同 → 第二次保存触发备份；显式拉开 mtime，避免同精度排序歧义
    import time

    time.sleep(0.02)
    store.save({"id": "snap_20_x", "turn": 21})
    bak = tmp_path / "snapshots" / "snap_20_x.bak.json"
    assert bak.exists()
    os.utime(bak, (1_000_000_000, 1_000_000_000))
    assert store.load_latest()["turn"] == 21


def test_snapshot_store_corrupted_returns_none(tmp_path, recwarn):
    d = tmp_path / "snapshots"
    d.mkdir()
    (d / "snap_5_x.json").write_text("not json", encoding="utf-8")
    store = FileSnapshotStore(d)
    assert store.load_latest() is None


# ---------------------------------------------------------------------------
# EmbeddingProvider（M1 只定接口，M3 落地实现）
# ---------------------------------------------------------------------------
def test_embedding_provider_protocol():
    class DummyProvider:
        @property
        def dimension(self) -> int:
            return 8

        def embed(self, texts):
            return [[0.0] * 8 for _ in texts]

    assert isinstance(DummyProvider(), EmbeddingProvider)
