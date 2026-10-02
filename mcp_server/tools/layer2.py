"""mcp_server.tools.layer2 — persona_layer2_query 工具

来源：PRD §11 序号 21, §7.3
       接口-v2 Layer 2 接口（7 个 operations）

v2 M1：conn → backend（StorageBackend，ADR-2）。
"""

from __future__ import annotations

from typing import Any

from persona_runtime.config import Config
from persona_runtime import librarian, memory_recall, memory_write, persistence
from persona_runtime.storage import StorageBackend

VALID_OPS = {
    "recall_2a",
    "recall_2b",
    "recall_2c",
    "recall_2d",
    "append_2d",
    "maybe_2d_trigger",
    "write_2b",
    # v2 M2-M4（§13.5 MCP 映射原则：不加第 6 工具）
    "append_2a",
    "append_2a_batch",
    "persist_session_summary",
    "cluster_patterns",
}


def persona_layer2_query(
    operation: str,
    backend: StorageBackend,
    params: dict[str, Any] | None = None,
    config: Config | None = None,
) -> dict[str, Any]:
    """persona_layer2_query — Layer 2 读写统一入口。

    operations:
      recall_2a: {entities: list, time_range: dict, semantic_query?: str}
      recall_2b: {entity: str}
      recall_2c: {patterns: list | None}
      recall_2d: {recent: int}
      append_2d: {change, reason, affected_layer, timestamp?, reversible?}
      maybe_2d_trigger: {input: D7 输入, dedup_state?}
      write_2b: {entity, field, value, mode, timestamp?}
      append_2a: {entry: dict, timestamp?}                     # v2 M2
      append_2a_batch: {entries: list, timestamp?}             # v2 M2
      persist_session_summary: {session_id, timestamp?}        # v2 M2（F3，需 config）
      cluster_patterns: {}                                     # v2 M4（Librarian）
    """
    if operation not in VALID_OPS:
        return {"error": f"operation '{operation}' not recognized", "valid": list(VALID_OPS)}
    params = params or {}
    try:
        if operation == "recall_2a":
            return memory_recall.C1_recall_2a(
                params.get("entities", []),
                params.get("time_range", {}),
                backend,
                semantic_query=params.get("semantic_query"),
            )
        if operation == "recall_2b":
            return memory_recall.C2_recall_2b(params["entity"], backend)
        if operation == "recall_2c":
            return memory_recall.C3_recall_2c(params.get("patterns"), backend)
        if operation == "recall_2d":
            return memory_recall.C4_recall_2d(params.get("recent", 0), backend)
        if operation == "append_2d":
            return memory_write.D6_append_2d_entry(
                backend,
                params["change"],
                params["reason"],
                params["affected_layer"],
                params.get("timestamp"),
                params.get("reversible", True),
            )
        if operation == "maybe_2d_trigger":
            return memory_write.D7_maybe_2d_trigger(
                params.get("input", {}), params.get("dedup_state")
            )
        if operation == "write_2b":
            return memory_write.D9_write_2b_entry(
                backend,
                params["entity"],
                params["field"],
                params["value"],
                params["mode"],
                params.get("timestamp"),
            )
        # ---- v2 M2-M4 ----
        if operation == "append_2a":
            return memory_write.D1_append_2a_entry(
                backend, params["entry"], params.get("timestamp")
            )
        if operation == "append_2a_batch":
            return memory_write.D2_append_2a_batch(
                backend, params["entries"], params.get("timestamp")
            )
        if operation == "persist_session_summary":
            return persistence.F3_persist_session_summary(
                params["session_id"], backend, config, params.get("timestamp")
            )
        if operation == "cluster_patterns":
            return librarian.cluster_cooling_patterns(backend)
    except (ValueError, KeyError) as e:
        return {"error": f"{type(e).__name__}: {e}", "operation": operation}
    return {"error": "unreachable"}