"""persona_runtime.db — 兼容 shim（v2 M1 起实现移至 storage.sqlite_adapter）

v1 的连接 + schema 初始化实现已迁移到 `persona_runtime.storage`（ADR-2
StorageBackend 抽象）。本模块仅保留旧导入路径，新代码请直接使用：

    from persona_runtime.storage import SQLiteStorage, connect, init_schema
"""

from __future__ import annotations

from .storage.base import from_json, to_json
from .storage.sqlite_adapter import (
    SCHEMA_SQL,
    connect,
    get_connection,
    init_schema,
)

__all__ = [
    "SCHEMA_SQL",
    "connect",
    "get_connection",
    "init_schema",
    "to_json",
    "from_json",
]
