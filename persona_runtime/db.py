"""persona_runtime.db — SQLite 连接 + schema 初始化

实现 PRD §7.1 的 SQLite schema：
- 4 张表（interaction_memory / entity_profile / long_term_patterns / self_growth_ledger）
- 2a 衰减字段（status / last_accessed）
- 2d TTL 衰减（物理 DELETE）
- 索引
- WAL 模式（PRD §12 并发风险回退）

来源：PRD §11 序号 9
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .config import Config

# PRD §7.1 完整 schema（4 表 + 衰减字段 + 索引）
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
    last_accessed TEXT NOT NULL DEFAULT (datetime('now')),
    vector_indexed INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS entity_profile (
    entity TEXT PRIMARY KEY,
    facts TEXT NOT NULL DEFAULT '[]',
    current_status TEXT NOT NULL DEFAULT '[]',
    judgment TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS long_term_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL UNIQUE,
    confidence REAL NOT NULL DEFAULT 0.0,
    first_observed TEXT NOT NULL,
    last_accessed TEXT NOT NULL,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS self_growth_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    change TEXT NOT NULL,
    reason TEXT NOT NULL,
    affected_layer TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    reversible INTEGER NOT NULL DEFAULT 1,
    deleted_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_interaction_timestamp ON interaction_memory(timestamp);
CREATE INDEX IF NOT EXISTS idx_interaction_channel ON interaction_memory(channel);
CREATE INDEX IF NOT EXISTS idx_interaction_status ON interaction_memory(status);
CREATE INDEX IF NOT EXISTS idx_interaction_last_accessed ON interaction_memory(last_accessed);
CREATE INDEX IF NOT EXISTS idx_patterns_confidence ON long_term_patterns(confidence);
CREATE INDEX IF NOT EXISTS idx_ledger_timestamp ON self_growth_ledger(timestamp);
"""


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


def get_connection(config: Config) -> sqlite3.Connection:
    """便捷入口：建立连接 + 初始化 schema。"""
    conn = connect(config.db_path)
    init_schema(conn)
    return conn


def to_json(value: Any) -> str:
    """SQLite 中 JSON 字段的统一编码（空列表也保留 '[]'）。"""
    import json

    return json.dumps(value, ensure_ascii=False)


def from_json(raw: str | None, default: Any = None) -> Any:
    """SQLite 中 JSON 字段的统一解码。"""
    import json

    if raw is None:
        return default if default is not None else []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else []