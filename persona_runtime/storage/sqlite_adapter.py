"""persona_runtime.storage.sqlite_adapter — SQLite 参考实现（v2 ADR-2）

把 v1 的 persona_runtime.db 连接 + DDL 收敛为 StorageBackend 的第一个适配器。
对上层暴露统一行协议 dict；SQL / 方言细节不越过本模块边界。

方言移植点（相对 v1，ARCHITECTURE §13.3）：
  1. 列默认值不再用 datetime('now')——时间戳一律由写入侧 Python 生成
  2. 衰减日期算术不再下推 SQL（datetime(?, '-N days')）——scan_* 返回候选行，
     阈值计算在 persistence.F4 的 Python 侧
  3. 实体匹配是语义方法 find_by_entities——LIKE 模拟 JSON 包含只是本适配器的
     实现细节，不进入契约
  4. row_factory / lastrowid 不越过边界——出口统一 dict，id 生成归仓储方法
"""

from __future__ import annotations

import sqlite3
import warnings
from pathlib import Path
from typing import Any

from .base import StorageNotSupported, from_json, to_json

# PRD §7.1 schema（v2 M1：去掉 datetime('now') 默认值，时间戳由写入侧提供）
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS interaction_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT,
    type TEXT NOT NULL,
    source_conv TEXT,
    timestamp TEXT NOT NULL,
    entities TEXT NOT NULL DEFAULT '[]',
    channel TEXT NOT NULL DEFAULT 'direct',
    status TEXT NOT NULL DEFAULT 'active',
    last_accessed TEXT NOT NULL,
    vector_indexed INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entity_profile (
    entity TEXT PRIMARY KEY,
    facts TEXT NOT NULL DEFAULT '[]',
    current_status TEXT NOT NULL DEFAULT '[]',
    judgment TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS long_term_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    confidence REAL NOT NULL DEFAULT 0.0,
    first_observed TEXT NOT NULL,
    last_accessed TEXT NOT NULL,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS self_growth_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    change TEXT NOT NULL,
    reason TEXT NOT NULL,
    affected_layer TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    reversible INTEGER NOT NULL DEFAULT 1,
    deleted_at TEXT,
    created_at TEXT NOT NULL
);

-- v2 M3：语义召回向量表（sqlite-vec 虚表的纯 Python 前身，暴力余弦；
-- 万行量级在 ADR-1 延迟预算内，性能升级留作后续选项）
CREATE TABLE IF NOT EXISTS interaction_embeddings (
    interaction_id INTEGER PRIMARY KEY,
    dim INTEGER NOT NULL,
    vector TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_interaction_timestamp ON interaction_memory(timestamp);
CREATE INDEX IF NOT EXISTS idx_interaction_channel ON interaction_memory(channel);
CREATE INDEX IF NOT EXISTS idx_interaction_status ON interaction_memory(status);
CREATE INDEX IF NOT EXISTS idx_interaction_last_accessed ON interaction_memory(last_accessed);
CREATE INDEX IF NOT EXISTS idx_patterns_confidence ON long_term_patterns(confidence);
CREATE INDEX IF NOT EXISTS idx_ledger_timestamp ON self_growth_ledger(timestamp);
"""

ENTITY_FIELDS = ("facts", "current_status", "judgment")


def connect(db_path: Path | str) -> sqlite3.Connection:
    """建立 SQLite 连接，开启 WAL 模式 + 外键 + row factory。

    check_same_thread=False：MCP stdio 模式下工具处理器被派发到
    任意工作线程执行，harness 单例连接必须跨线程可用；
    写入串行化由 PRD §12（WAL + 单实例）保证。
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """创建所有表和索引（IF NOT EXISTS，幂等）。"""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


# ---------------------------------------------------------------------------
# 2a
# ---------------------------------------------------------------------------
class SQLiteInteractions:
    def __init__(self, conn: sqlite3.Connection, embedding_provider=None) -> None:
        self._conn = conn
        self._embedding = embedding_provider

    def append_entry(self, entry: dict[str, Any]) -> int:
        rid = self._insert_one(entry)
        self._conn.commit()
        return rid

    def append_batch(self, entries: list[dict[str, Any]]) -> list[int]:
        ids: list[int] = []
        try:
            for entry in entries:
                ids.append(self._insert_one(entry))
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return ids

    def _insert_one(self, entry: dict[str, Any]) -> int:
        ts = entry["timestamp"]
        # 向量同步生成（ADR-2 §13.5：D1/D2 写入时经 EmbeddingProvider 入索引）
        vector_indexed = 1 if entry.get("vector_indexed") is None and self._embedding else 0
        if entry.get("vector_indexed") is not None:
            vector_indexed = 1 if entry["vector_indexed"] else 0
        cur = self._conn.execute(
            "INSERT INTO interaction_memory "
            "(content, type, source_conv, timestamp, entities, channel, status, "
            "last_accessed, vector_indexed, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                entry.get("content"),
                entry["type"],
                entry.get("source_conversation"),
                ts,
                to_json(entry.get("entities") or []),
                entry.get("channel", "direct"),
                entry.get("status", "active"),
                entry.get("last_accessed") or ts,
                vector_indexed,
                entry.get("created_at") or ts,
            ),
        )
        rid = int(cur.lastrowid)
        if vector_indexed and entry.get("content"):
            self._store_vector(rid, entry["content"])
        return rid

    def _store_vector(self, interaction_id: int, content: str) -> None:
        if not self._embedding:
            return
        vec = self._embedding.embed([content])[0]
        self._conn.execute(
            "INSERT OR REPLACE INTO interaction_embeddings (interaction_id, dim, vector) "
            "VALUES (?, ?, ?)",
            (interaction_id, len(vec), to_json(vec)),
        )

    def find_by_entities(
        self, entities: list[str], time_range: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        where = ["status != 'content_wiped'"]
        params: list[Any] = []
        if entities:
            ors = " OR ".join(["entities LIKE ?" for _ in entities])
            where.append(f"({ors})")
            params.extend([f'%"{e}"%' for e in entities])
        if time_range:
            if time_range.get("from"):
                where.append("timestamp >= ?")
                params.append(time_range["from"])
            if time_range.get("to"):
                where.append("timestamp <= ?")
                params.append(time_range["to"])
        sql = (
            "SELECT * FROM interaction_memory WHERE "
            + " AND ".join(where)
            + " ORDER BY timestamp DESC"
        )
        try:
            rows = list(self._conn.execute(sql, params))
        except Exception as e:
            warnings.warn(f"C1 query invalid time_range: {e}")
            return []
        return [self._to_domain(r) for r in rows]

    def find_similar(self, query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        raise StorageNotSupported(
            "SQLiteInteractions.find_similar 需要 sqlite-vec 向量后端（v2 M3 交付）"
        )

    def find_by_conversation(
        self, source_conversation: str, limit: int = 200
    ) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM interaction_memory WHERE source_conv = ? "
            "ORDER BY timestamp ASC, id ASC LIMIT ?",
            (source_conversation, int(limit)),
        ).fetchall()
        return [self._to_domain(r) for r in rows]

    def find_similar(self, query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        if not self._embedding:
            raise StorageNotSupported(
                "SQLiteInteractions.find_similar 需要注入 EmbeddingProvider"
            )
        rows = self._conn.execute(
            "SELECT e.interaction_id, e.vector FROM interaction_embeddings e "
            "JOIN interaction_memory m ON m.id = e.interaction_id "
            "WHERE m.status != 'content_wiped'"
        ).fetchall()
        if not rows:
            return []
        q = list(query_vector)
        q_norm = _norm(q)
        if q_norm == 0:
            return []
        scored = []
        for r in rows:
            vec = from_json(r["vector"])
            n = _norm(vec)
            if n == 0:
                continue
            sim = sum(a * b for a, b in zip(q, vec)) / (q_norm * n)
            scored.append((sim, r["interaction_id"]))
        scored.sort(key=lambda t: (-t[0], t[1]))
        top = [iid for _, iid in scored[: max(1, int(top_k))]]
        result = []
        for iid in top:
            row = self._conn.execute(
                "SELECT * FROM interaction_memory WHERE id = ?", (iid,)
            ).fetchone()
            if row is not None:
                result.append(self._to_domain(row))
        return result

    def touch_access(self, ids: list[int], now: str) -> None:
        if not ids:
            return
        self._conn.executemany(
            "UPDATE interaction_memory SET last_accessed = ? WHERE id = ?",
            [(now, i) for i in ids],
        )
        self._conn.commit()

    def scan_decay_candidates(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, status, vector_indexed, content, type, entities, last_accessed "
            "FROM interaction_memory WHERE status != 'content_wiped' ORDER BY id"
        ).fetchall()
        return [
            {
                "id": r["id"],
                "status": r["status"],
                "vector_indexed": r["vector_indexed"],
                "content": r["content"],
                "type": r["type"],
                "entities": from_json(r["entities"]),
                "last_accessed": r["last_accessed"],
            }
            for r in rows
        ]

    def mark_status(self, ids: list[int], status: str) -> None:
        if not ids:
            return
        self._conn.executemany(
            "UPDATE interaction_memory SET status = ? WHERE id = ?",
            [(status, i) for i in ids],
        )
        self._conn.commit()

    def clear_vector_index(self, ids: list[int]) -> None:
        if not ids:
            return
        self._conn.executemany(
            "UPDATE interaction_memory SET vector_indexed = 0 WHERE id = ?",
            [(i,) for i in ids],
        )
        # §13.5 F4 对齐：向量删除阶段同步删向量行
        self._conn.executemany(
            "DELETE FROM interaction_embeddings WHERE interaction_id = ?",
            [(i,) for i in ids],
        )
        self._conn.commit()

    def wipe_content(self, ids: list[int]) -> None:
        if not ids:
            return
        self._conn.executemany(
            "UPDATE interaction_memory SET content = NULL, status = 'content_wiped' WHERE id = ?",
            [(i,) for i in ids],
        )
        self._conn.executemany(
            "DELETE FROM interaction_embeddings WHERE interaction_id = ?",
            [(i,) for i in ids],
        )
        self._conn.commit()

    @staticmethod
    def _to_domain(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "content": row["content"],
            "type": row["type"],
            "source_conversation": row["source_conv"],
            "timestamp": row["timestamp"],
            "entities": from_json(row["entities"]),
            "channel": row["channel"],
            "status": row["status"],
            "last_accessed": row["last_accessed"],
        }


# ---------------------------------------------------------------------------
# 2b
# ---------------------------------------------------------------------------
class SQLiteEntities:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, entity: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM entity_profile WHERE entity = ?", (entity,)
        ).fetchone()
        if row is None:
            return None
        return {
            "entity": row["entity"],
            "facts": from_json(row["facts"]),
            "current_status": from_json(row["current_status"]),
            "judgment": from_json(row["judgment"]),
            "updated_at": row["updated_at"],
        }

    def ensure(self, entity: str, now: str) -> None:
        self._conn.execute(
            "INSERT INTO entity_profile (entity, facts, current_status, judgment, updated_at) "
            "VALUES (?, '[]', '[]', '[]', ?)",
            (entity, now),
        )
        self._conn.commit()

    def get_field(self, entity: str, field: str) -> list[Any]:
        self._check_field(field)
        row = self._conn.execute(
            f"SELECT {field} FROM entity_profile WHERE entity = ?", (entity,)
        ).fetchone()
        if row is None:
            return []
        return from_json(row[field])

    def set_field(self, entity: str, field: str, entries: list[Any], now: str) -> None:
        self._check_field(field)
        self._conn.execute(
            f"UPDATE entity_profile SET {field} = ?, updated_at = ? WHERE entity = ?",
            (to_json(entries), now, entity),
        )
        self._conn.commit()

    @staticmethod
    def _check_field(field: str) -> None:
        if field not in ENTITY_FIELDS:
            raise ValueError(f"unknown entity_profile field {field} — refused")


# ---------------------------------------------------------------------------
# 2c
# ---------------------------------------------------------------------------
class SQLitePatterns:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def query(self, patterns: list[str] | None = None) -> list[dict[str, Any]]:
        if patterns:
            ors = " OR ".join(["pattern LIKE ?" for _ in patterns])
            sql = f"SELECT * FROM long_term_patterns WHERE {ors} ORDER BY confidence DESC"
            params: list[Any] = [f"%{p}%" for p in patterns]
        else:
            sql = "SELECT * FROM long_term_patterns ORDER BY confidence DESC"
            params = []
        rows = list(self._conn.execute(sql, params))
        return [
            {
                "id": r["id"],
                "pattern": r["pattern"],
                "confidence": r["confidence"],
                "first_observed": r["first_observed"],
                "last_accessed": r["last_accessed"],
                "evidence_count": r["evidence_count"],
            }
            for r in rows
        ]

    def touch_access(self, ids: list[int], now: str) -> None:
        if not ids:
            return
        self._conn.executemany(
            "UPDATE long_term_patterns SET last_accessed = ? WHERE id = ?",
            [(now, i) for i in ids],
        )
        self._conn.commit()

    def insert_pattern(
        self,
        pattern: str,
        confidence: float,
        first_observed: str,
        last_accessed: str,
        evidence_count: int = 0,
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO long_term_patterns (pattern, confidence, first_observed, "
            "last_accessed, evidence_count, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (pattern, confidence, first_observed, last_accessed, evidence_count, last_accessed),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def upsert_from_cluster(
        self,
        pattern: str,
        confidence: float,
        evidence_count: int,
        last_accessed: str,
    ) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT id, confidence, evidence_count FROM long_term_patterns WHERE pattern = ?",
            (pattern,),
        ).fetchone()
        if row is None:
            new_id = self.insert_pattern(pattern, confidence, last_accessed, last_accessed, evidence_count)
            return {
                "id": new_id,
                "pattern": pattern,
                "confidence": confidence,
                "evidence_count": evidence_count,
                "merged": False,
            }
        # §7.3 原则：confidence 只增不减；evidence_count 累计
        new_conf = max(float(row["confidence"]), float(confidence))
        new_evidence = int(row["evidence_count"]) + int(evidence_count)
        self._conn.execute(
            "UPDATE long_term_patterns SET confidence = ?, evidence_count = ?, "
            "last_accessed = ? WHERE id = ?",
            (new_conf, new_evidence, last_accessed, row["id"]),
        )
        self._conn.commit()
        return {
            "id": row["id"],
            "pattern": pattern,
            "confidence": new_conf,
            "evidence_count": new_evidence,
            "merged": True,
        }


# ---------------------------------------------------------------------------
# 2d
# ---------------------------------------------------------------------------
class SQLiteLedger:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(self, entry: dict[str, Any]) -> int:
        cur = self._conn.execute(
            "INSERT INTO self_growth_ledger (change, reason, affected_layer, timestamp, reversible, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                entry["change"],
                entry["reason"],
                entry["affected_layer"],
                entry["timestamp"],
                1 if entry.get("reversible", True) else 0,
                entry.get("created_at") or entry["timestamp"],
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def recent(self, n: int) -> list[dict[str, Any]]:
        sql = "SELECT * FROM self_growth_ledger WHERE deleted_at IS NULL ORDER BY timestamp DESC"
        params: list[Any] = []
        if n > 0:
            sql += " LIMIT ?"
            params.append(int(n))
        rows = list(self._conn.execute(sql, params))
        return [
            {
                "id": r["id"],
                "change": r["change"],
                "reason": r["reason"],
                "affected_layer": r["affected_layer"],
                "timestamp": r["timestamp"],
                "reversible": bool(r["reversible"]),
            }
            for r in rows
        ]

    def scan_expired(self, now: str, ttl_days: int) -> list[int]:
        from datetime import datetime, timedelta
        from .base import parse_ts

        now_dt = parse_ts(now)
        if now_dt is None:
            raise ValueError(f"invalid now: {now}")
        rows = self._conn.execute(
            "SELECT id, timestamp FROM self_growth_ledger WHERE deleted_at IS NULL"
        ).fetchall()
        cutoff = now_dt - timedelta(days=ttl_days)
        ids = []
        for r in rows:
            ts = parse_ts(r["timestamp"])
            if ts is not None and ts < cutoff:
                ids.append(r["id"])
        return ids

    def delete(self, ids: list[int]) -> None:
        if not ids:
            return
        self._conn.executemany(
            "DELETE FROM self_growth_ledger WHERE id = ?",
            [(i,) for i in ids],
        )
        self._conn.commit()


# ---------------------------------------------------------------------------
# 聚合根
# ---------------------------------------------------------------------------
class SQLiteStorage:
    """StorageBackend 的 SQLite 参考实现。

    .conn 仅供测试 / 白盒检查使用，业务代码不得直接下发 SQL。
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        snapshot_dir: Path | str | None = None,
        embedding_provider=None,
    ) -> None:
        self.conn = conn
        self.embedding_provider = embedding_provider
        self.interactions = SQLiteInteractions(conn, embedding_provider)
        self.entities = SQLiteEntities(conn)
        self.patterns = SQLitePatterns(conn)
        self.ledger = SQLiteLedger(conn)
        self.snapshots = None
        if snapshot_dir is not None:
            from .file_snapshot import FileSnapshotStore

            self.snapshots = FileSnapshotStore(Path(snapshot_dir))

    @classmethod
    def from_config(cls, config, embedding_provider="__default__") -> "SQLiteStorage":
        """默认注入 HashingEmbeddingProvider（本地、零依赖、确定性）；
        显式传 None 关闭向量写入；传自定义 provider 接入本地小模型 / API。"""
        if embedding_provider == "__default__":
            from .embedding import HashingEmbeddingProvider

            embedding_provider = HashingEmbeddingProvider()
        conn = connect(config.db_path)
        init_schema(conn)
        return cls(conn, config.snapshot_dir, embedding_provider)

    def close(self) -> None:
        self.conn.close()


def _norm(vec: list[float]) -> float:
    return sum(x * x for x in vec) ** 0.5


def get_connection(config) -> sqlite3.Connection:
    """兼容入口（v1 db.get_connection）：连接 + 初始化 schema。"""
    conn = connect(config.db_path)
    init_schema(conn)
    return conn
