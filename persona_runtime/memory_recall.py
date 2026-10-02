"""persona_runtime.memory_recall — C1-C6 召回类接口

Layer 2 数据读取 + 召回后处理（permission 标记 + 语态改写）。

v2 M1：C1-C4 的 SQL 实现下沉到 StorageBackend 仓储（ADR-2），
本模块只做编排（召回 + touch_access 副作用）与纯函数后处理。

来源：PRD §11 序号 12
       接口-v1 §C（6 个召回接口）+ 架构 §5.1/§5.2 全局规则
"""

from __future__ import annotations

import warnings
from datetime import datetime, timezone
from typing import Any

from .storage import StorageBackend, utc_now_iso

UTC_FMT = "%Y-%m-%dT%H:%M:%S"


# ---------------------------------------------------------------------------
# C1 recall_2a(entities, time_range, backend, semantic_query=None)
# ---------------------------------------------------------------------------
SEMANTIC_TOP_K = 5


def C1_recall_2a(
    entities: list[str],
    time_range: dict[str, str],
    backend: StorageBackend,
    semantic_query: str | None = None,
) -> dict[str, Any]:
    """C1 — 互动事实召回。召回时更新 last_accessed（重置衰减计时）。

    v2 M3 双路召回（§13.5）：entities 精确命中 ∪ find_similar 语义命中
    （backend 注入 EmbeddingProvider 且 semantic_query 非空时启用）。
    每条记录附带 recall_channels（["entity"]/["semantic"]/两者），供 C5 联动。

    entities 与 semantic_query 均为空 → 返回空列表。
    """
    if not entities and not semantic_query:
        return {"records": []}
    merged: dict[int, dict[str, Any]] = {}
    if entities:
        for rec in backend.interactions.find_by_entities(entities, time_range):
            rec = dict(rec)
            rec["recall_channels"] = ["entity"]
            merged[rec["id"]] = rec
    if semantic_query:
        provider = getattr(backend, "embedding_provider", None)
        if provider is not None:
            try:
                vector = provider.embed([semantic_query])[0]
                for rec in backend.interactions.find_similar(vector, top_k=SEMANTIC_TOP_K):
                    existing = merged.get(rec["id"])
                    if existing is not None:
                        existing["recall_channels"].append("semantic")
                    else:
                        rec = dict(rec)
                        rec["recall_channels"] = ["semantic"]
                        merged[rec["id"]] = rec
            except Exception as exc:  # noqa: BLE001 — 语义路故障降级为纯精确路
                warnings.warn(f"C1 semantic recall failed: {exc}")
        else:
            warnings.warn("C1 semantic_query given but backend has no embedding provider")
    records = sorted(merged.values(), key=lambda r: r["timestamp"], reverse=True)
    if records:
        backend.interactions.touch_access(
            [r["id"] for r in records], utc_now_iso()
        )
    return {"records": records}


# ---------------------------------------------------------------------------
# C2 recall_2b(entity, backend)
# ---------------------------------------------------------------------------
def C2_recall_2b(entity: str, backend: StorageBackend) -> dict[str, Any]:
    """C2 — 实体画像召回。entity 不存在 → 返回空 profile。"""
    profile = backend.entities.get(entity)
    if profile is None:
        profile = {
            "entity": entity,
            "facts": [],
            "current_status": [],
            "judgment": [],
            "updated_at": utc_now_iso(),
        }
    return {"profile": profile}


# ---------------------------------------------------------------------------
# C3 recall_2c(patterns, backend)
# ---------------------------------------------------------------------------
def C3_recall_2c(
    patterns: list[str] | None, backend: StorageBackend
) -> dict[str, Any]:
    """C3 — 长期模式召回。patterns 为空 → 返回所有。更新 last_accessed。"""
    records = backend.patterns.query(patterns)
    if records:
        backend.patterns.touch_access(
            [r["id"] for r in records], utc_now_iso()
        )
    return {"records": records}


# ---------------------------------------------------------------------------
# C4 recall_2d(recent, backend)
# ---------------------------------------------------------------------------
def C4_recall_2d(recent: int, backend: StorageBackend) -> dict[str, Any]:
    """C4 — 自我更新账本召回。recent=0 → 所有；recent<0 → 警告按 0 处理。"""
    if recent < 0:
        warnings.warn("C4 recent < 0 — treat as 0")
        recent = 0
    return {"records": backend.ledger.recent(recent)}


# ---------------------------------------------------------------------------
# C5 apply_recall_permission(records)
# ---------------------------------------------------------------------------
def C5_apply_recall_permission(records: list[dict[str, Any]]) -> dict[str, Any]:
    """C5 — 三档 recall permission 标记。

    规则（架构 §5.1）：
      双通道命中 + <30 天 → cite
      单通道命中 或 30-90 天 → cautious
      >90 天 或随机召回 → associate-only

    channel_hit 判定：
      - 2a：entities 命中 + 时间窗命中 = 双通道
      - 单通道命中之一 = cautious
    """
    tagged = []
    now = datetime.now(timezone.utc)
    for rec in records:
        tagged_rec = dict(rec) if isinstance(rec, dict) else {"record": rec}
        ref = rec if isinstance(rec, dict) else {}
        ts_raw = ref.get("timestamp") or ref.get("last_accessed")
        ts = _parse_iso(ts_raw)
        if ts is None:
            warnings.warn("C5 timestamp missing — use now")
            ts = now
        age_days = (now - ts).days
        permission, voice = _compute_permission(ref, age_days)
        tagged.append(
            {
                "record": rec,
                "permission": permission,
                "voice_suggestion": voice,
            }
        )
    return {"tagged_records": tagged}


def _compute_permission(rec: dict[str, Any], age_days: int) -> tuple[str, str]:
    if age_days > 90:
        return ("associate-only", "仅作为内部参考，不向用户陈述")
    # v2 M3 C5 联动（§13.5）：仅语义命中 → 语义单路，无实体/时间锚的
    # 陈述资格不高于 cautious——记忆被错误当作事实陈述是人格崩塌的常见原因
    channels = rec.get("recall_channels")
    if channels == ["semantic"]:
        return ("cautious", "用'我好像记得……'等留口吻")
    channel = rec.get("channel", "direct")
    has_entities = bool(rec.get("entities"))
    if has_entities and channel in ("direct", "indirect"):
        double = True
    else:
        double = False
    if age_days < 30 and double:
        return ("cite", "可直接陈述为事实")
    if (30 <= age_days <= 90) or (not double):
        return ("cautious", "用'我好像记得……'等留口吻")
    return ("cite", "可直接陈述为事实")


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.strptime(s, UTC_FMT)
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, AttributeError):
            warnings.warn(f"C5 invalid timestamp: {s} — treat as now")
            return None


# ---------------------------------------------------------------------------
# C6 rewrite_voice(records, source_layer)
# ---------------------------------------------------------------------------
def C6_rewrite_voice(
    records: list[dict[str, Any]], source_layer: str
) -> dict[str, Any]:
    """C6 — 检索后语态改写（架构 §5.2）。

    2a / 2b-facts / 2c → 第三人称 "你记得他……"
    2b-judgment / 2d → 第一人称 直接用
    """
    if source_layer not in ("2a", "2b", "2c", "2d"):
        warnings.warn(f"C6 invalid source_layer {source_layer} — skip rewrite")
        return {"rewritten": [{"content": _extract_content(r)} for r in records]}

    rewritten = []
    for rec in records:
        content = _extract_content(rec)
        if source_layer == "2a":
            content = f"你记得他{content}" if content else ""
        elif source_layer == "2b":
            if "judgment" in str(rec.get("record", {}).get("affected_layer", "")):
                pass
            else:
                content = f"你记得他{content}" if content else ""
        elif source_layer == "2c":
            content = f"你注意到他{content}" if content else ""
        elif source_layer == "2d":
            rewritten.append({"content": content})
            continue
        rewritten.append({"content": content})
    return {"rewritten": rewritten}


def _extract_content(rec: Any) -> str:
    """从 record 提取可改写的文本字段。"""
    if isinstance(rec, dict):
        if "record" in rec and isinstance(rec["record"], dict):
            ref = rec["record"]
            return (
                ref.get("content")
                or ref.get("change")
                or ref.get("pattern")
                or ref.get("reason")
                or ""
            )
        return (
            rec.get("content")
            or rec.get("change")
            or rec.get("pattern")
            or rec.get("reason")
            or ""
        )
    return str(rec)