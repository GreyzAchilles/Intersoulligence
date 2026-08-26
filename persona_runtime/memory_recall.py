"""persona_runtime.memory_recall — C1-C6 召回类接口

Layer 2 数据读取 + 召回后处理（permission 标记 + 语态改写）。

来源：PRD §11 序号 12
       接口-v1 §C（6 个召回接口）+ 架构 §5.1/§5.2 全局规则
"""

from __future__ import annotations

import sqlite3
import warnings
from datetime import datetime, timezone
from typing import Any

from .db import from_json, to_json

UTC_FMT = "%Y-%m-%dT%H:%M:%S"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime(UTC_FMT)


# ---------------------------------------------------------------------------
# C1 recall_2a(entities, time_range, conn)
# ---------------------------------------------------------------------------
def C1_recall_2a(
    entities: list[str],
    time_range: dict[str, str],
    conn: sqlite3.Connection,
) -> dict[str, Any]:
    """C1 — 互动事实召回。召回时更新 last_accessed（重置衰减计时）。

    entities 为空 → 返回空列表（PRD A1：entities 为空 → 空列表）。
    """
    if not entities:
        return {"records": []}
    rows = _query_2a(entities, time_range, conn)
    if rows:
        ids = [r["id"] for r in rows]
        conn.executemany(
            "UPDATE interaction_memory SET last_accessed = ? WHERE id = ?",
            [(_now_iso(), i) for i in ids],
        )
        conn.commit()
    records = [_row_to_2a(r) for r in rows]
    return {"records": records}


def _query_2a(
    entities: list[str], time_range: dict[str, str], conn: sqlite3.Connection
) -> list[sqlite3.Row]:
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
        return list(conn.execute(sql, params))
    except Exception as e:
        warnings.warn(f"C1 query invalid time_range: {e}")
        return []


def _row_to_2a(row: sqlite3.Row) -> dict[str, Any]:
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
# C2 recall_2b(entity, conn)
# ---------------------------------------------------------------------------
def C2_recall_2b(entity: str, conn: sqlite3.Connection) -> dict[str, Any]:
    """C2 — 实体画像召回。entity 不存在 → 返回空 profile。"""
    row = conn.execute(
        "SELECT * FROM entity_profile WHERE entity = ?", (entity,)
    ).fetchone()
    if row is None:
        return {
            "profile": {
                "entity": entity,
                "facts": [],
                "current_status": [],
                "judgment": [],
                "updated_at": _now_iso(),
            }
        }
    return {
        "profile": {
            "entity": row["entity"],
            "facts": from_json(row["facts"]),
            "current_status": from_json(row["current_status"]),
            "judgment": from_json(row["judgment"]),
            "updated_at": row["updated_at"],
        }
    }


# ---------------------------------------------------------------------------
# C3 recall_2c(patterns, conn)
# ---------------------------------------------------------------------------
def C3_recall_2c(
    patterns: list[str] | None, conn: sqlite3.Connection
) -> dict[str, Any]:
    """C3 — 长期模式召回。patterns 为空 → 返回所有。更新 last_accessed。"""
    if patterns:
        ors = " OR ".join(["pattern LIKE ?" for _ in patterns])
        sql = f"SELECT * FROM long_term_patterns WHERE {ors} ORDER BY confidence DESC"
        params: list[Any] = [f"%{p}%" for p in patterns]
    else:
        sql = "SELECT * FROM long_term_patterns ORDER BY confidence DESC"
        params = []
    rows = list(conn.execute(sql, params))
    if rows:
        ids = [r["id"] for r in rows]
        conn.executemany(
            "UPDATE long_term_patterns SET last_accessed = ? WHERE id = ?",
            [(_now_iso(), i) for i in ids],
        )
        conn.commit()
    records = [
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
    return {"records": records}


# ---------------------------------------------------------------------------
# C4 recall_2d(recent, conn)
# ---------------------------------------------------------------------------
def C4_recall_2d(recent: int, conn: sqlite3.Connection) -> dict[str, Any]:
    """C4 — 自我更新账本召回。recent=0 → 所有；recent<0 → 警告按 0 处理。"""
    if recent < 0:
        warnings.warn("C4 recent < 0 — treat as 0")
        recent = 0
    sql = (
        "SELECT * FROM self_growth_ledger WHERE deleted_at IS NULL ORDER BY timestamp DESC"
    )
    if recent > 0:
        sql += f" LIMIT {int(recent)}"
    rows = list(conn.execute(sql))
    records = [
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
    return {"records": records}


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