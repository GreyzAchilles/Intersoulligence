"""tests/conftest.py — pytest 共享 fixture

每个测试用临时 schema + 临时 SQLite，相互隔离。
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from persona_runtime import schema_loader
from persona_runtime.config import Config, load_config
from persona_runtime.db import connect, init_schema


REPO_DATA = Path(__file__).resolve().parent.parent / "data" / "persona_schema.yaml"


@pytest.fixture
def tmp_config(tmp_path: Path) -> Config:
    """临时 Config：data 目录 + schema + db + snapshots 全部在 tmp_path。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    schema_path = data_dir / "persona_schema.yaml"
    shutil.copy(REPO_DATA, schema_path)
    cfg = load_config(
        data_dir=data_dir,
        schema_path=schema_path,
        db_path=data_dir / "persona.db",
        snapshot_dir=data_dir / "snapshots",
    )
    schema_loader.reset_cache()
    return cfg


@pytest.fixture
def conn(tmp_config: Config) -> sqlite3.Connection:
    """已初始化 schema 的 SQLite 连接。"""
    c = connect(tmp_config.db_path)
    init_schema(c)
    yield c
    c.close()


@pytest.fixture
def harness(tmp_config: Config):
    """已初始化的 Harness。"""
    from persona_runtime import create_harness

    h = create_harness(tmp_config)
    h.init()
    schema_loader.reset_cache()
    yield h
    if h.conn is not None:
        h.conn.close()


def insert_interaction(
    conn: sqlite3.Connection,
    content: str = "事实",
    typ: str = "observation",
    entities: list[str] | None = None,
    timestamp: str = "2026-08-14T10:00:00",
    channel: str = "direct",
    last_accessed: str | None = None,
    status: str = "active",
    vector_indexed: int = 1,
) -> int:
    import json

    cur = conn.execute(
        "INSERT INTO interaction_memory (content, type, source_conv, timestamp, entities, channel, "
        "status, last_accessed, vector_indexed) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            content,
            typ,
            "test_conv",
            timestamp,
            json.dumps(entities or [], ensure_ascii=False),
            channel,
            status,
            last_accessed or timestamp,
            vector_indexed,
        ),
    )
    conn.commit()
    return int(cur.lastrowid)


def insert_ledger(
    conn: sqlite3.Connection,
    change: str = "改了",
    reason: str = "用户反馈",
    affected_layer: str = "Layer 1",
    timestamp: str = "2026-08-14T10:00:00",
    reversible: int = 1,
) -> int:
    cur = conn.execute(
        "INSERT INTO self_growth_ledger (change, reason, affected_layer, timestamp, reversible) "
        "VALUES (?, ?, ?, ?, ?)",
        (change, reason, affected_layer, timestamp, reversible),
    )
    conn.commit()
    return int(cur.lastrowid)


def insert_pattern(
    conn: sqlite3.Connection,
    pattern: str = "偏好递进追问",
    confidence: float = 0.5,
    first_observed: str = "2026-07-29T10:00:00",
    last_accessed: str = "2026-08-13T10:00:00",
    evidence_count: int = 1,
) -> int:
    cur = conn.execute(
        "INSERT INTO long_term_patterns (pattern, confidence, first_observed, last_accessed, "
        "evidence_count) VALUES (?, ?, ?, ?, ?)",
        (pattern, confidence, first_observed, last_accessed, evidence_count),
    )
    conn.commit()
    return int(cur.lastrowid)


def insert_entity(
    conn: sqlite3.Connection,
    entity: str = "用户",
    facts: list | None = None,
    current_status: list | None = None,
    judgment: list | None = None,
) -> None:
    import json

    conn.execute(
        "INSERT INTO entity_profile (entity, facts, current_status, judgment) "
        "VALUES (?, ?, ?, ?)",
        (
            entity,
            json.dumps(facts or [], ensure_ascii=False),
            json.dumps(current_status or [], ensure_ascii=False),
            json.dumps(judgment or [], ensure_ascii=False),
        ),
    )
    conn.commit()