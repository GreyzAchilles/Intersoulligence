"""persona_runtime.persistence — F1, F2, F4 持久化类接口

快照 + 衰减机制。每 20 轮触发 F1（触发 F4）。

来源：PRD §11 序号 15
       接口-v1 §F / Layer2 遗忘机制 §6
       PRD §7.1 schema + §12 风险回退（WAL + 简化滑动窗口）
"""

from __future__ import annotations

import json
import sqlite3
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Config

UTC_FMT = "%Y-%m-%dT%H:%M:%S"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime(UTC_FMT)


# ---------------------------------------------------------------------------
# F1 take_snapshot(turn, conn, config, ...)
# ---------------------------------------------------------------------------
def F1_take_snapshot(
    turn: int,
    conn: sqlite3.Connection,
    config: Config,
    current_stage: str = "grill",
    current_scenario: str = "",
    short_window_violation_rate: float = 0.0,
    trigger_decay: bool = True,
) -> dict[str, Any]:
    """F1 — 每 20 轮落盘快照。副作用：触发 F4 apply_decay。"""
    decay_report: dict[str, Any] | None = None
    if trigger_decay:
        decay_report = F4_apply_decay(_now_iso(), conn, config)

    snapshot = {
        "id": f"snap_{turn}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "turn": turn,
        "timestamp": _now_iso(),
        "short_window_violation_rate": short_window_violation_rate,
        "current_stage": current_stage,
        "current_scenario": current_scenario,
        "decay_report": decay_report,
    }

    snap_dir = config.snapshot_dir
    snap_dir.mkdir(parents=True, exist_ok=True)
    path = snap_dir / f"{snapshot['id']}.json"
    if path.exists():
        backup = snap_dir / f"{snapshot['id']}.bak.json"
        try:
            path.rename(backup)
        except OSError as e:
            warnings.warn(f"F1 backup failed: {e}")
    try:
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as e:
        warnings.warn(f"F1 snapshot write failed: {e} — keep in-memory")
    snapshot["path"] = str(path)
    return {"snapshot": snapshot}


# ---------------------------------------------------------------------------
# F2 load_latest_snapshot(config)
# ---------------------------------------------------------------------------
def F2_load_latest_snapshot(config: Config) -> dict[str, Any]:
    """F2 — 启动时加载最近快照。无 → null，fresh_start。"""
    snap_dir = config.snapshot_dir
    if not snap_dir.exists():
        return {"loaded": {"snapshot": None, "recovery_action": "fresh_start"}}

    snapshots = sorted(
        [p for p in snap_dir.glob("snap_*.json")],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not snapshots:
        return {"loaded": {"snapshot": None, "recovery_action": "fresh_start"}}

    snap: dict[str, Any] | None = None
    for path in snapshots:
        try:
            snap = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as e:
            warnings.warn(f"F2 snapshot {path.name} corrupted: {e} — try previous")
            continue
        break
    if snap is None:
        return {"loaded": {"snapshot": None, "recovery_action": "fresh_start"}}
    return {"loaded": {"snapshot": snap, "recovery_action": "rewind"}}


# ---------------------------------------------------------------------------
# F4 apply_decay(now, conn, config)
# ---------------------------------------------------------------------------
def _norm_iso(s: str) -> str:
    """SQLite datetime() 仅接受 'YYYY-MM-DD HH:MM:SS' 形式。

    将带 T 的 ISO datetime 归一化为带空格的形式，使 SQLite 日期算术正确生效。
    """
    if not s:
        return s
    s = s.strip()
    if "T" in s:
        s = s.replace("T", " ")
    return s


def F4_apply_decay(
    now: str,
    conn: sqlite3.Connection,
    config: Config,
) -> dict[str, Any]:
    """F4 — 2a 三阶段衰减 + 2d TTL 衰减。

    幂等；单条失败隔离；access 重置（C1 召回时已更新 last_accessed → 自动跳过）。
    """
    cooling: list[int] = []
    vector_deleted: list[int] = []
    content_wiped: list[int] = []
    ttl_expired: list[int] = []
    now_norm = _norm_iso(now)

    # 2a cooling: 14-30 天（last_accessed < now - 14 days，且 status = active）
    try:
        rows = conn.execute(
            "SELECT id FROM interaction_memory "
            "WHERE status = 'active' "
            "AND datetime(last_accessed) < datetime(?, '-{} days')".format(config.cooling_days),
            (now_norm,),
        ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            conn.executemany(
                "UPDATE interaction_memory SET status = 'cooling' WHERE id = ?",
                [(i,) for i in ids],
            )
            cooling = ids
    except Exception as e:
        warnings.warn(f"F4 2a cooling update failed: {e}")

    # 2a vector 删除: 30-90 天
    try:
        rows = conn.execute(
            "SELECT id FROM interaction_memory "
            "WHERE status = 'cooling' AND vector_indexed = 1 "
            "AND datetime(last_accessed) < datetime(?, '-{} days')".format(config.vector_delete_days),
            (now_norm,),
        ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            conn.executemany(
                "UPDATE interaction_memory SET vector_indexed = 0 WHERE id = ?",
                [(i,) for i in ids],
            )
            vector_deleted = ids
    except Exception as e:
        warnings.warn(f"F4 2a vector delete failed: {e}")

    # 2a content wiped: ≥ 90 天
    try:
        rows = conn.execute(
            "SELECT id FROM interaction_memory "
            "WHERE vector_indexed = 0 AND content IS NOT NULL "
            "AND datetime(last_accessed) < datetime(?, '-{} days')".format(config.content_wipe_days),
            (now_norm,),
        ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            conn.executemany(
                "UPDATE interaction_memory SET content = NULL, status = 'content_wiped' WHERE id = ?",
                [(i,) for i in ids],
            )
            content_wiped = ids
    except Exception as e:
        warnings.warn(f"F4 2a content wipe failed: {e}")

    # 2d TTL 衰减（物理 DELETE，≥ 180 天）
    try:
        rows = conn.execute(
            "SELECT id FROM self_growth_ledger "
            "WHERE deleted_at IS NULL "
            "AND datetime(timestamp) < datetime(?, '-{} days')".format(config.ledger_ttl_days),
            (now_norm,),
        ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            conn.executemany(
                "DELETE FROM self_growth_ledger WHERE id = ?",
                [(i,) for i in ids],
            )
            ttl_expired = ids
    except Exception as e:
        warnings.warn(f"F4 2d TTL delete failed: {e}")

    conn.commit()

    return {
        "layer_2a": {
            "cooling": cooling,
            "vector_deleted": vector_deleted,
            "content_wiped": content_wiped,
        },
        "layer_2b": None,
        "layer_2c": None,
        "layer_2d": {
            "ttl_expired": ttl_expired,
            "manual_deleted": [],
        },
    }