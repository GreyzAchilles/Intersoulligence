"""persona_runtime.storage.base — StorageBackend 端口契约（v2 ADR-2）

定义人格模块的存储能力契约：后端选型交给用户，SQLite 只是参考实现。

分层（ARCHITECTURE §13.3）：
  StorageBackend（聚合根）
    ├── InteractionRepo   2a 互动事实（append / 语义查找 / 衰减原语）
    ├── EntityRepo        2b 实体画像（get / 字段级 set）
    ├── PatternRepo       2c 长期模式（query / touch / insert）
    ├── LedgerRepo        2d 自我更新账本（append / recent / TTL 原语）
    └── SnapshotStore     F1/F2 快照（JSON 文件实现，后端无关）

EmbeddingProvider 与存储解耦：向量生成（M3 sqlite-vec 落地）单独走本接口。

契约纪律：
  - 仓储方法只收发 dict（统一行协议），不透传 SQL / 方言片段
  - 时间戳一律由写入侧生成（ISO 字符串），存储层不再有 datetime('now') 默认值
  - 衰减的策略计算在 persistence.F4（后端无关），存储只提供扫描 / 应用原语
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

UTC_FMT = "%Y-%m-%dT%H:%M:%S"


class StorageNotSupported(NotImplementedError):
    """当前后端不支持该能力（如 SQLiteAdapter 未接 sqlite-vec 时的 find_similar）。"""


def utc_now_iso() -> str:
    """统一的时间戳生成入口（原 4 个模块的 _now_iso 收敛于此）。"""
    return datetime.now(timezone.utc).strftime(UTC_FMT)


def parse_ts(raw: str | None) -> datetime | None:
    """解析 ISO 时间戳（兼容 'T' / 空格分隔、带/不带时区）；失败返回 None。"""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def to_json(value: Any) -> str:
    """存储中 JSON 字段的统一编码（空列表也保留 '[]'）。"""
    return json.dumps(value, ensure_ascii=False)


def from_json(raw: str | None, default: Any = None) -> Any:
    """存储中 JSON 字段的统一解码。"""
    if raw is None:
        return default if default is not None else []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else []


# ---------------------------------------------------------------------------
# 2a InteractionRepo
# ---------------------------------------------------------------------------
@runtime_checkable
class InteractionRepo(Protocol):
    """2a 互动事实仓储。"""

    def append_entry(self, entry: dict[str, Any]) -> int:
        """写入单条互动事实，返回新 id。entry 缺省字段由实现按表默认补齐。"""
        ...

    def append_batch(self, entries: list[dict[str, Any]]) -> list[int]:
        """整批单事务写入（M2 D2 语义），返回新 id 列表；部分失败整批回滚。"""
        ...

    def find_by_entities(
        self, entities: list[str], time_range: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        """按实体精确召回（语义契约：entities 命中即返回，不含 content_wiped）。

        返回统一行协议 dict：id / content / type / source_conversation /
        timestamp / entities(list) / channel / status / last_accessed。
        按 timestamp 倒序。
        """
        ...

    def find_by_conversation(
        self, source_conversation: str, limit: int = 200
    ) -> list[dict[str, Any]]:
        """按来源会话取 2a 轨迹（F3 会话总结用），按 timestamp 正序。"""
        ...

    def find_similar(self, query_vector: list[float], top_k: int = 5) -> list[dict[str, Any]]:
        """语义召回（向量后端启用后生效）；不支持的后端抛 StorageNotSupported。"""
        ...

    def touch_access(self, ids: list[int], now: str) -> None:
        """更新 last_accessed（C1/C3 召回副作用 → 重置衰减计时）。"""
        ...

    def scan_decay_candidates(self) -> list[dict[str, Any]]:
        """返回未到终态（status != 'content_wiped'）的 2a 行，供 F4 做 Python 侧阈值计算。

        返回字段：id / status / vector_indexed / content / type / entities(list) /
        last_accessed。
        """
        ...

    def mark_status(self, ids: list[int], status: str) -> None:
        """批量更新 status（cooling 等阶段推进）。"""
        ...

    def clear_vector_index(self, ids: list[int]) -> None:
        """批量清除向量索引标记（vector_indexed → 0）。"""
        ...

    def wipe_content(self, ids: list[int]) -> None:
        """批量清空 content 并置 status='content_wiped'（保留元数据）。"""
        ...


# ---------------------------------------------------------------------------
# 2b EntityRepo
# ---------------------------------------------------------------------------
@runtime_checkable
class EntityRepo(Protocol):
    """2b 实体画像仓储。字段值以解码后的 list 读写，JSON 编解码归实现。"""

    def get(self, entity: str) -> dict[str, Any] | None:
        """返回完整画像 dict（facts / current_status / judgment 已解码）；不存在 → None。"""
        ...

    def ensure(self, entity: str, now: str) -> None:
        """不存在则创建空画像。"""
        ...

    def get_field(self, entity: str, field: str) -> list[Any]:
        """返回指定字段的解码列表；画像不存在 → 空列表。field 不识别 → ValueError。"""
        ...

    def set_field(self, entity: str, field: str, entries: list[Any], now: str) -> None:
        """整体覆写指定字段并刷新 updated_at。field 不识别 → ValueError。"""
        ...


# ---------------------------------------------------------------------------
# 2c PatternRepo
# ---------------------------------------------------------------------------
@runtime_checkable
class PatternRepo(Protocol):
    """2c 长期模式仓储。confidence 只增不减是 F4/Librarian 层的策略，存储不拦。"""

    def query(self, patterns: list[str] | None = None) -> list[dict[str, Any]]:
        """模式查询。patterns None → 全量；给定期 → 子串匹配。按 confidence 倒序。"""
        ...

    def touch_access(self, ids: list[int], now: str) -> None:
        """更新 last_accessed（C3 召回副作用 → 控制 freshness）。"""
        ...

    def insert_pattern(
        self,
        pattern: str,
        confidence: float,
        first_observed: str,
        last_accessed: str,
        evidence_count: int = 0,
    ) -> int:
        """插入新模式（M4 upsert_from_cluster 的存储原语）。pattern 重复 → 抛错。"""
        ...

    def upsert_from_cluster(
        self,
        pattern: str,
        confidence: float,
        evidence_count: int,
        last_accessed: str,
    ) -> dict[str, Any]:
        """Librarian 聚类结果落库（M4 deep cycle）。

        pattern 已存在（UNIQUE 命中）→ confidence 只增不减 + evidence_count 累计；
        不存在 → 新建。返回 {id, pattern, confidence, evidence_count, merged}。
        """
        ...


# ---------------------------------------------------------------------------
# 2d LedgerRepo
# ---------------------------------------------------------------------------
@runtime_checkable
class LedgerRepo(Protocol):
    """2d 自我更新账本仓储。"""

    def append(self, entry: dict[str, Any]) -> int:
        """写入账本条目，返回新 id。"""
        ...

    def recent(self, n: int) -> list[dict[str, Any]]:
        """最近 n 条（n<=0 → 全量），按 timestamp 倒序，排除已软删（deleted_at）。"""
        ...

    def scan_expired(self, now: str, ttl_days: int) -> list[int]:
        """返回 timestamp 距 now 超过 ttl_days 的未软删条目 id（阈值计算在 Python 侧）。"""
        ...

    def delete(self, ids: list[int]) -> None:
        """物理删除（2d TTL 路径；软删除 tombstone 为 v3 演进）。"""
        ...


# ---------------------------------------------------------------------------
# SnapshotStore
# ---------------------------------------------------------------------------
@runtime_checkable
class SnapshotStore(Protocol):
    """F1/F2 快照存储。现有 JSON 文件实现直接转正（后端无关）。"""

    def save(self, snapshot: dict[str, Any]) -> str:
        """落盘快照，返回路径。路径冲突自动备份上一份；IO 失败警告后返回预期路径。"""
        ...

    def load_latest(self) -> dict[str, Any] | None:
        """最近一份可用快照；无 → None；损坏文件警告后回退上一份。"""
        ...


# ---------------------------------------------------------------------------
# 聚合根
# ---------------------------------------------------------------------------
@runtime_checkable
class StorageBackend(Protocol):
    """人格模块存储聚合根——harness 持有并注入各 C/D/F 接口。"""

    interactions: InteractionRepo
    entities: EntityRepo
    patterns: PatternRepo
    ledger: LedgerRepo
    snapshots: SnapshotStore

    def close(self) -> None:
        """释放底层资源（连接 / 文件句柄）。"""
        ...


# ---------------------------------------------------------------------------
# EmbeddingProvider（与存储解耦，M3 落地实现）
# ---------------------------------------------------------------------------
@runtime_checkable
class EmbeddingProvider(Protocol):
    """向量生成接口。默认本地小模型（1B-7B 量化方向），可配置 API。"""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量生成向量，顺序与输入一致。"""
        ...

    @property
    def dimension(self) -> int:
        """向量维度（建 sqlite-vec 虚表时需要）。"""
        ...
