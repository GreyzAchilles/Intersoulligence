"""persona_runtime.scribe — 对话 → 2a 提取（v2 M2，Scribe 组件）

v1 缺口（ARCHITECTURE §13.1）：2a 在生产运行时零写入路径。Scribe 是
「记忆生命线」的入口组件——每轮响应后从对话中提取候选互动事实，
经 D2 批量写入 2a，使其进入召回 / F4 衰减 / 2c 聚类的正常生命周期。

实现定位（如实声明）：
  - M2 交付为**规则提取起步**：偏好 / 事实 / 事件三类关键词模式 +
    实体白名单扫描，零 LLM 依赖、可单测
  - LLM 提取的挂点：`extract_entries(..., extract_fn=...)`——接入
    人格 LLM 后由调用方注入更强的提取函数，规则实现作为回退
"""

from __future__ import annotations

import re
import warnings
from typing import Any, Callable

from .memory_write import D2_append_2a_batch
from .storage import StorageBackend, utc_now_iso

# 每轮最多提取条数（防止刷屏）
MAX_PER_TURN = 3

# 提取规则：模式 → 2a type
_PREFERENCE_PATTERNS = (
    re.compile(r"我(喜欢|偏爱|偏好|更喜欢|爱)([^。！？；\n]{1,60})"),
)
_FACT_PATTERNS = (
    re.compile(r"我是([^。！？；\n，,]{1,40})"),
    re.compile(r"我(正在|在)([^。！？；\n]{1,50})"),
    re.compile(r"我最近([^。！？；\n]{1,50})"),
)
_EVENT_PATTERNS = (
    re.compile(r"(今天|昨天|前天|上周|上周末|这周末)([^。！？；\n]{1,60})"),
)


def extract_entries(
    user_message: str,
    ai_response: str,
    known_entities: list[str] | None = None,
    extract_fn: Callable[[str, str], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """从一轮对话提取候选 2a 条目（不写库）。

    extract_fn：LLM 提取挂点——传入后完全接管提取，规则实现不再参与。
    """
    if extract_fn is not None:
        entries = extract_fn(user_message, ai_response)
        return [e for e in entries if isinstance(e, dict)][:MAX_PER_TURN]

    candidates: list[dict[str, Any]] = []
    # 用户消息是事实 / 偏好 / 事件的主要来源；AI 响应仅扫偏好（人格自述调整）
    for source, patterns, typ in (
        (user_message, _PREFERENCE_PATTERNS, "preference"),
        (user_message, _FACT_PATTERNS, "observation"),
        (user_message, _EVENT_PATTERNS, "event"),
    ):
        if not source:
            continue
        for pat in patterns:
            for match in pat.finditer(source):
                content = match.group(0).strip()
                if content:
                    candidates.append(
                        {
                            "content": content[:80],
                            "type": typ,
                            "entities": _match_entities(content, known_entities),
                            "channel": "direct",
                        }
                    )
    # 去重（同轮同内容只留一条）+ 截断
    seen: set[str] = set()
    entries = []
    for cand in candidates:
        key = f"{cand['type']}:{cand['content']}"
        if key not in seen:
            seen.add(key)
            entries.append(cand)
    return entries[:MAX_PER_TURN]


def _match_entities(text: str, known_entities: list[str] | None) -> list[str]:
    if not known_entities:
        return []
    return [e for e in known_entities if e and e in text]


def scribe_turn(
    backend: StorageBackend,
    user_message: str,
    ai_response: str,
    session_id: str | None = None,
    known_entities: list[str] | None = None,
    extract_fn: Callable[[str, str], list[dict[str, Any]]] | None = None,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """每轮响应后调用：提取 + D2 批量写入（source_conversation = session_id）。

    提取为空 → 不写库。写入失败警告不抛（Scribe 故障不得打断主循环）。
    """
    entries = extract_entries(user_message, ai_response, known_entities, extract_fn)
    if not entries:
        return {"scribe": {"extracted": 0, "appended": []}}
    for e in entries:
        e["source_conversation"] = session_id
    try:
        out = D2_append_2a_batch(backend, entries, timestamp=timestamp or utc_now_iso())
        return {"scribe": {"extracted": len(entries), "appended": out["appended"]["ids"]}}
    except Exception as exc:  # noqa: BLE001 — 提取内容不可控，失败隔离
        warnings.warn(f"Scribe write failed: {exc}")
        return {"scribe": {"extracted": len(entries), "appended": [], "error": str(exc)}}
