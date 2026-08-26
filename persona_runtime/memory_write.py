"""persona_runtime.memory_write — D6-D9 写入类接口

Layer 2 数据写入 + 字段管理 + 伦理校验。

来源：PRD §11 序号 13
       接口-v1 §D（4 个写入接口）
       架构 §4.2b 字段分流 / §4.2d 单路径人格触发式自评
"""

from __future__ import annotations

import sqlite3
import warnings
from datetime import datetime, timezone
from typing import Any

from .db import from_json, to_json

UTC_FMT = "%Y-%m-%dT%H:%M:%S"

# 2d 触发关键词（架构 §4.2d 写入机制）
USER_FEEDBACK_KEYWORDS = {"辛苦", "谢谢", "不错", "很好", "改一下", "调整一下", "不太对"}
REMEMBER_KEYWORDS = {"记住", "记一条", "记下来"}
EXPLICIT_REPEAT_THRESHOLD = 3  # 同一关键词最近 5 轮 ≥ 3 次
RECENT_WINDOW = 5

# PROTECTED 层（Layer 0）
PROTECTED_AFFECTED_LAYERS = {"Layer 0", "Layer 0.1", "Layer 0.2", "Layer 0.3"}

# 对用户判断的关键词（D8 伦理约束）
USER_JUDGMENT_KEYWORDS = {"他喜欢", "你是个", "老板喜欢", "用户其实"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime(UTC_FMT)


# ---------------------------------------------------------------------------
# D6 append_2d_entry(change, reason, affected_layer, ...)
# ---------------------------------------------------------------------------
def D6_append_2d_entry(
    conn: sqlite3.Connection,
    change: str,
    reason: str,
    affected_layer: str,
    timestamp: str | None = None,
    reversible: bool = True,
) -> dict[str, Any]:
    """D6 — 自我更新账本写入。

    三要素任一缺失 → 拒绝。
    affected_layer 在 PROTECTED 区 → 拒绝 + 冲突条款。
    """
    if not change or not reason or not affected_layer:
        raise ValueError(
            f"D6 missing required: change/reason/affected_layer — refused"
        )
    if affected_layer in PROTECTED_AFFECTED_LAYERS:
        return {
            "refused": True,
            "reason": f"affected_layer {affected_layer} in PROTECTED zone",
            "conflict_clauses": [
                {"layer": "Layer 0", "clause": "PROTECTED", "explanation": "Layer 0 不可被运行时改写"}
            ],
        }
    # 含对用户判断 → 剥离
    stripped = _strip_user_judgment(change)
    if stripped != change:
        change = stripped
        warnings.warn("D6 stripped user-judgment content")

    ts = timestamp or _now_iso()
    cur = conn.execute(
        "INSERT INTO self_growth_ledger (change, reason, affected_layer, timestamp, reversible) "
        "VALUES (?, ?, ?, ?, ?)",
        (change, reason, affected_layer, ts, 1 if reversible else 0),
    )
    conn.commit()
    return {"appended": {"id": cur.lastrowid, "timestamp": ts}}


# ---------------------------------------------------------------------------
# D7 maybe_2d_trigger(input, dedup_state)
# ---------------------------------------------------------------------------
def D7_maybe_2d_trigger(
    input_data: dict[str, Any], dedup_state: dict[str, Any] | None = None
) -> dict[str, Any]:
    """D7 — 2d 触发检测（每轮响应后）。

    触发条件（任一）：
      - 用户明确反馈（关键词）
      - 价值层违例
      - 重复同类指令（同关键词最近 5 轮 ≥ 3 次）
      - 用户显式要求记住

    节流：同一触发事件 5 轮内重复 → 跳过；同窗口内人格自评 ≥1 次 → 跳过。
    """
    dedup_state = dedup_state or {}
    user_message = input_data.get("user_message", "")
    ai_response = input_data.get("ai_response", "")
    value_violation = input_data.get("value_violation_detected", False)
    recent_turns = input_data.get("recent_5_turns", [])

    trigger_reason = None
    suggested_entry = {"change": "", "reason": "", "affected_layer": "Layer 1"}

    # 触发 1: 用户明确反馈
    if any(kw in user_message for kw in USER_FEEDBACK_KEYWORDS):
        trigger_reason = "user_feedback"
        suggested_entry["reason"] = f"用户反馈含关键词匹配"
        suggested_entry["change"] = "调整自身表达以响应用户反馈"

    # 触发 2: 价值层违例
    if value_violation:
        if trigger_reason is None:
            trigger_reason = "value_violation"
            suggested_entry["reason"] = "价值层自检检出违例"
            suggested_entry["change"] = "对违例的处理与对应反思"

    # 触发 3: 重复同类指令（同一关键词计数超过阈值）
    if trigger_reason is None:
        counts = dedup_state.get("keyword_counts", {})
        for kw in REMEMBER_KEYWORDS | USER_FEEDBACK_KEYWORDS:
            if counts.get(kw, 0) >= EXPLICIT_REPEAT_THRESHOLD:
                trigger_reason = "repeated_command"
                suggested_entry["reason"] = f"用户重复提及'{kw}' ≥{EXPLICIT_REPEAT_THRESHOLD}次"
                suggested_entry["change"] = f"针对'{kw}'相关调整"
                break

    # 触发 4: 用户显式要求记住
    if trigger_reason is None and any(
        kw in user_message for kw in REMEMBER_KEYWORDS
    ):
        trigger_reason = "explicit_remember"
        suggested_entry["reason"] = "用户显式要求记忆"
        suggested_entry["change"] = "用户要求记住的内容相关调整"

    if trigger_reason is None:
        return {"trigger": {"triggered": False, "reason": "", "suggested_entry": None}}

    # 节流：相同 reason 5 轮内去重
    last_trigger_map = dedup_state.get("last_trigger_map", {})
    last_turn = last_trigger_map.get(trigger_reason, -999)
    last_self_eval_turn = dedup_state.get("last_self_eval_turn", -999)
    current_turn = input_data.get("turn", 0)
    if current_turn - last_turn < 5:
        return {
            "trigger": {
                "triggered": False,
                "reason": f"duplicate {trigger_reason} within 5 turns",
                "suggested_entry": None,
            }
        }
    if current_turn - last_self_eval_turn < 5:
        return {
            "trigger": {
                "triggered": False,
                "reason": "self-eval already happened this window",
                "suggested_entry": None,
            }
        }

    return {"trigger": {"triggered": True, "reason": trigger_reason, "suggested_entry": suggested_entry}}


# ---------------------------------------------------------------------------
# D8 validate_2d_entry(entry)
# ---------------------------------------------------------------------------
def D8_validate_2d_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """D8 — 2d 写入前伦理校验。

    违反 Layer 0 → 拒绝。
    含对用户判断 → 剥离。
    affected_layer PROTECTED 区 → 拒绝。
    """
    conflicts = []
    stripped = []
    passed = True

    affected_layer = entry.get("affected_layer", "")
    if affected_layer in PROTECTED_AFFECTED_LAYERS:
        passed = False
        conflicts.append(
            {
                "layer": "Layer 0",
                "clause": "PROTECTED",
                "explanation": f"affected_layer {affected_layer} 不可被运行时改写",
            }
        )

    change = entry.get("change", "")
    reason = entry.get("reason", "")
    for field_name, val in [("change", change), ("reason", reason)]:
        for kw in USER_JUDGMENT_KEYWORDS:
            if kw in val:
                stripped.append(field_name)
                passed = False

    if not (change and reason and affected_layer):
        passed = False
        conflicts.append(
            {
                "layer": "Layer 2d",
                "clause": "三要素必填",
                "explanation": "change / reason / affected_layer 任一缺失视为无效",
            }
        )

    return {
        "validated": {
            "passed": passed,
            "conflicts": conflicts,
            "stripped_sections": stripped,
        }
    }


# ---------------------------------------------------------------------------
# D9 write_2b_entry(entity, field, value, mode, conn, timestamp=None)
# ---------------------------------------------------------------------------
def D9_write_2b_entry(
    conn: sqlite3.Connection,
    entity: str,
    field: str,
    value: Any,
    mode: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """D9 — 2b 字段级写入（architecture §4.2b 字段分流）。

    facts → 必须 overwrite
    current_status → 必须 covering_update (替换 last，保留历史)
    judgment → 必须 append
    """
    if field not in ("facts", "current_status", "judgment"):
        raise ValueError(f"D9 unknown field {field} — refused")
    if mode not in ("overwrite", "covering_update", "append"):
        raise ValueError(f"D9 unknown mode {mode} — refused")
    # 强制字段 → mode 一致性
    expected_mode = {
        "facts": "overwrite",
        "current_status": "covering_update",
        "judgment": "append",
    }[field]
    if mode != expected_mode:
        raise ValueError(
            f"D9 field {field} requires mode '{expected_mode}', got '{mode}' — refused"
        )
    ts = timestamp or _now_iso()
    row = conn.execute(
        "SELECT * FROM entity_profile WHERE entity = ?", (entity,)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO entity_profile (entity, facts, current_status, judgment, updated_at) "
            "VALUES (?, '[]', '[]', '[]', ?)",
            (entity, ts),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM entity_profile WHERE entity = ?", (entity,)
        ).fetchone()

    affected_entries: list[Any] = []
    old_value = from_json(row[field])

    if mode == "overwrite":
        new_value = value if isinstance(value, list) else [value]
        affected_entries = list(old_value)
        conn.execute(
            f"UPDATE entity_profile SET {field} = ?, updated_at = ? WHERE entity = ?",
            (to_json(new_value), ts, entity),
        )
    elif mode == "covering_update":
        val = value if isinstance(value, dict) else {"content": value, "timestamp": ts}
        if not isinstance(val, dict):
            val = {"content": str(value), "timestamp": ts}
        affected_entries = list(old_value)
        old_value = [val]
        conn.execute(
            f"UPDATE entity_profile SET {field} = ?, updated_at = ? WHERE entity = ?",
            (to_json(old_value), ts, entity),
        )
    else:  # append
        val = value if isinstance(value, dict) else {"content": value, "timestamp": ts}
        if not isinstance(val, dict):
            val = {"content": str(value), "timestamp": ts}
        old_value = old_value + [val]
        conn.execute(
            f"UPDATE entity_profile SET {field} = ?, updated_at = ? WHERE entity = ?",
            (to_json(old_value), ts, entity),
        )
    conn.commit()
    return {
        "written": {
            "entity": entity,
            "field": field,
            "mode": mode,
            "timestamp": ts,
            "affected_entries": affected_entries,
        }
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _strip_user_judgment(content: str) -> str:
    """剥离含对用户判断的内容（宁可错杀）。"""
    stripped = content
    for kw in USER_JUDGMENT_KEYWORDS:
        if kw in stripped:
            stripped = stripped.replace(kw, "[stripped]")
    return stripped


def update_keyword_counts(
    user_message: str, dedup_state: dict[str, Any]
) -> dict[str, int]:
    """utility: 维护用户重复关键词计数（D7 内部逻辑用）。"""
    counts = dedup_state.setdefault("keyword_counts", {})
    for kw in REMEMBER_KEYWORDS | USER_FEEDBACK_KEYWORDS:
        if kw in user_message:
            counts[kw] = counts.get(kw, 0) + 1
    return counts