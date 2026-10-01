"""persona_runtime.persistence — F1, F2, F4 持久化类接口

快照 + 衰减机制。每 20 轮触发 F1（触发 F4）。

v2 M1：文件 IO 下沉到 SnapshotStore 端口、衰减日期算术从 SQL 下推
改为 Python 侧阈值计算（ADR-2 方言移植点 ②）。策略（14/30/90/180 天
与失败隔离粒度）保持 v1 语义不变。

来源：PRD §11 序号 15
       接口-v1 §F / Layer2 遗忘机制 §6
       PRD §7.1 schema + §12 风险回退（WAL + 简化滑动窗口）
"""

from __future__ import annotations

import warnings
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import Config
from .storage import StorageBackend, parse_ts, utc_now_iso


# ---------------------------------------------------------------------------
# F1 take_snapshot(turn, backend, config, ...)
# ---------------------------------------------------------------------------
def F1_take_snapshot(
    turn: int,
    backend: StorageBackend,
    config: Config,
    current_stage: str = "grill",
    current_scenario: str = "",
    short_window_violation_rate: float = 0.0,
    trigger_decay: bool = True,
) -> dict[str, Any]:
    """F1 — 每 20 轮落盘快照。副作用：触发 F4 apply_decay。"""
    decay_report: dict[str, Any] | None = None
    if trigger_decay:
        decay_report = F4_apply_decay(utc_now_iso(), backend, config)

    snapshot = {
        "id": f"snap_{turn}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "turn": turn,
        "timestamp": utc_now_iso(),
        "short_window_violation_rate": short_window_violation_rate,
        "current_stage": current_stage,
        "current_scenario": current_scenario,
        "decay_report": decay_report,
    }

    snapshot["path"] = backend.snapshots.save(snapshot)
    return {"snapshot": snapshot}


# ---------------------------------------------------------------------------
# F2 load_latest_snapshot(backend)
# ---------------------------------------------------------------------------
def F2_load_latest_snapshot(backend: StorageBackend) -> dict[str, Any]:
    """F2 — 启动时加载最近快照。无 → null，fresh_start。"""
    snap = backend.snapshots.load_latest()
    if snap is None:
        return {"loaded": {"snapshot": None, "recovery_action": "fresh_start"}}
    return {"loaded": {"snapshot": snap, "recovery_action": "rewind"}}


# ---------------------------------------------------------------------------
# F4 apply_decay(now, backend, config)
# ---------------------------------------------------------------------------
def _compute_2a_transitions(
    candidates: list[dict[str, Any]],
    now: str,
    config: Config,
) -> tuple[list[int], list[int], list[int]]:
    """按架构 §8.1 阈值在 Python 侧计算 2a 三阶段迁移（替代 v1 的 SQL 日期算术）。

    语义与 v1 SQL 严格一致（datetime(last_accessed) < datetime(now, '-N days')）：
      - cooling:        status='active' 且 距今 > cooling_days
      - vector_deleted: status='cooling' 且 vector_indexed=1 且 距今 > vector_delete_days
      - content_wiped:  vector_indexed=0 且 content 非空 且 距今 > content_wipe_days
    """
    now_dt = parse_ts(now)
    if now_dt is None:
        raise ValueError(f"invalid now: {now}")
    cutoff_cool = now_dt - timedelta(days=config.cooling_days)
    cutoff_vec = now_dt - timedelta(days=config.vector_delete_days)
    cutoff_wipe = now_dt - timedelta(days=config.content_wipe_days)

    cooling: list[int] = []
    vector: list[int] = []
    wipe: list[int] = []
    for row in candidates:
        ts = parse_ts(row["last_accessed"])
        if ts is None:
            continue
        if row["status"] == "active" and ts < cutoff_cool:
            cooling.append(row["id"])
        if row["status"] == "cooling" and row["vector_indexed"] == 1 and ts < cutoff_vec:
            vector.append(row["id"])
        if row["vector_indexed"] == 0 and row["content"] is not None and ts < cutoff_wipe:
            wipe.append(row["id"])
    return cooling, vector, wipe


def F4_apply_decay(
    now: str,
    backend: StorageBackend,
    config: Config,
) -> dict[str, Any]:
    """F4 — 2a 三阶段衰减 + 2d TTL 衰减。

    幂等；失败隔离粒度与 v1 一致（按阶段 try/except，单阶段失败警告后继续）；
    access 重置（C1/C3 召回时已更新 last_accessed → 自动跳过）。
    """
    cooling: list[int] = []
    vector_deleted: list[int] = []
    content_wiped: list[int] = []
    ttl_expired: list[int] = []

    # 候选扫描 + 阈值计算（Python 侧，方言无关）
    try:
        candidates = backend.interactions.scan_decay_candidates()
        cooling_ids, vector_ids, wipe_ids = _compute_2a_transitions(
            candidates, now, config
        )
    except Exception as e:
        warnings.warn(f"F4 2a scan failed: {e}")
        cooling_ids, vector_ids, wipe_ids = [], [], []

    # 2a cooling: 14-30 天
    try:
        if cooling_ids:
            backend.interactions.mark_status(cooling_ids, "cooling")
        cooling = cooling_ids
    except Exception as e:
        warnings.warn(f"F4 2a cooling update failed: {e}")

    # 2a vector 删除: 30-90 天
    try:
        if vector_ids:
            backend.interactions.clear_vector_index(vector_ids)
        vector_deleted = vector_ids
    except Exception as e:
        warnings.warn(f"F4 2a vector delete failed: {e}")

    # 2a content wiped: ≥ 90 天
    try:
        if wipe_ids:
            backend.interactions.wipe_content(wipe_ids)
        content_wiped = wipe_ids
    except Exception as e:
        warnings.warn(f"F4 2a content wipe failed: {e}")

    # 2d TTL 衰减（物理 DELETE，≥ 180 天）
    try:
        expired = backend.ledger.scan_expired(now, config.ledger_ttl_days)
        backend.ledger.delete(expired)
        ttl_expired = expired
    except Exception as e:
        warnings.warn(f"F4 2d TTL delete failed: {e}")

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
