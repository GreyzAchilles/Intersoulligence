"""persona_runtime.storage — 存储抽象（v2 ADR-2）

StorageBackend Port/Adapter 契约 + SQLite 参考实现 + JSON 文件快照存储。
后端选型交给用户；契约定义见 ARCHITECTURE §13.3。
"""

from .base import (
    EmbeddingProvider,
    EntityRepo,
    InteractionRepo,
    LedgerRepo,
    PatternRepo,
    SnapshotStore,
    StorageBackend,
    StorageNotSupported,
    from_json,
    parse_ts,
    to_json,
    utc_now_iso,
)
from .embedding import HashingEmbeddingProvider
from .file_snapshot import FileSnapshotStore
from .sqlite_adapter import (
    SCHEMA_SQL,
    SQLiteStorage,
    connect,
    get_connection,
    init_schema,
)

__all__ = [
    "EmbeddingProvider",
    "EntityRepo",
    "FileSnapshotStore",
    "HashingEmbeddingProvider",
    "InteractionRepo",
    "LedgerRepo",
    "PatternRepo",
    "SCHEMA_SQL",
    "SQLiteStorage",
    "SnapshotStore",
    "StorageBackend",
    "StorageNotSupported",
    "connect",
    "from_json",
    "get_connection",
    "init_schema",
    "parse_ts",
    "to_json",
    "utc_now_iso",
]
