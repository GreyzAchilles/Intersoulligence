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

import re
import warnings
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
# F3 persist_session_summary(session_id, backend, config)（v2 §13.5）
# ---------------------------------------------------------------------------
def F3_persist_session_summary(
    session_id: str,
    backend: StorageBackend,
    config: Config,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """F3 — 会话正常结束时把会话轨迹沉淀为长期记忆。

    三路落点（ARCHITECTURE §13.5）：
      ① 2a episode 条目（经 D2，type='episode'）
      ② 2b 实体画像 current_status 更新（经 D9 covering_update）
      ③ content/sessions/{session_id}.md  markdown 投影（DB 为源、投影可读）

    边界（随本契约定稿 v1.1 问题 4）：F3 只产 2a/2b，**永不产 2d**——
    会话级事实与画像归 2b，人格自指的变化才归 2d。
    """
    from .memory_write import D2_append_2a_batch, D9_write_2b_entry

    if not session_id:
        raise ValueError("F3 session_id missing — refused")
    ts = timestamp or utc_now_iso()
    trajectory = backend.interactions.find_by_conversation(session_id)
    if not trajectory:
        return {"persisted": False, "reason": "no interaction records for session"}

    by_type = dict(Counter(r["type"] for r in trajectory))
    entities = sorted({e for r in trajectory for e in (r.get("entities") or [])})
    highlights = [r["content"] for r in trajectory[-5:]]
    summary = {
        "session_id": session_id,
        "records": len(trajectory),
        "started_at": trajectory[0]["timestamp"],
        "ended_at": trajectory[-1]["timestamp"],
        "by_type": by_type,
        "entities": entities,
        "highlights": highlights,
    }

    # ① 2a episode 条目
    type_brief = "、".join(f"{k}×{v}" for k, v in by_type.items())
    episode_content = (
        f"会话 {session_id}：{len(trajectory)} 条互动（{type_brief}），"
        f"涉及 {'、'.join(entities) if entities else '无实体'}"
    )[:80]
    episode = D2_append_2a_batch(
        backend,
        [{
            "content": episode_content,
            "type": "episode",
            "entities": entities,
            "channel": "direct",
            "source_conversation": session_id,
            "timestamp": ts,
        }],
        timestamp=ts,
    )
    episode_id = episode["appended"]["ids"][0]

    # ② 2b current_status 更新（每个涉事实体一条 covering_update，最多 10 个）
    entity_updates: dict[str, Any] = {}
    for entity in entities[:10]:
        try:
            out = D9_write_2b_entry(
                backend,
                entity,
                "current_status",
                {"content": f"会话 {session_id}：{len(trajectory)} 条相关互动", "timestamp": ts},
                "covering_update",
                timestamp=ts,
            )
            entity_updates[entity] = out["written"]["timestamp"]
        except (ValueError, KeyError) as e:
            warnings.warn(f"F3 2b update failed for {entity}: {e}")

    # ③ markdown 投影（写失败警告，不阻断）
    markdown_path: str | None = None
    try:
        markdown_path = _write_session_markdown(config, summary)
    except OSError as e:
        warnings.warn(f"F3 markdown projection failed: {e}")

    return {
        "persisted": True,
        "summary": summary,
        "episode_id": episode_id,
        "entity_updates": entity_updates,
        "markdown_path": markdown_path,
    }


def _write_session_markdown(config: Config, summary: dict[str, Any]) -> str:
    session_dir = Path(config.content_dir) / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^\w\-.]", "_", summary["session_id"])
    path = session_dir / f"{safe_id}.md"
    lines = [
        f"# 会话总结 — {summary['session_id']}",
        "",
        f"- 记录数：{summary['records']}（{summary['started_at']} → {summary['ended_at']}）",
        f"- 类型分布：{'、'.join(f'{k}×{v}' for k, v in summary['by_type'].items()) or '—'}",
        f"- 涉及实体：{'、'.join(summary['entities']) or '—'}",
        "",
        "## 轨迹要点",
        "",
    ]
    lines += [f"- {h}" for h in summary["highlights"]]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


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
