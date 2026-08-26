"""mcp_server.tools.layer2 — persona_layer2_query 工具

来源：PRD §11 序号 21, §7.3
       接口-v2 Layer 2 接口（7 个 operations）
"""

from __future__ import annotations

import sqlite3
from typing import Any

from persona_runtime.config import Config
from persona_runtime import memory_recall, memory_write

VALID_OPS = {
    "recall_2a",
    "recall_2b",
    "recall_2c",
    "recall_2d",
    "append_2d",
    "maybe_2d_trigger",
    "write_2b",
}


def persona_layer2_query(
    operation: str,
    conn: sqlite3.Connection,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """persona_layer2_query — Layer 2 读写统一入口。

    operations:
      recall_2a: {entities: list, time_range: dict}
      recall_2b: {entity: str}
      recall_2c: {patterns: list | None}
      recall_2d: {recent: int}
      append_2d: {change, reason, affected_layer, timestamp?, reversible?}
      maybe_2d_trigger: {input: D7 输入, dedup_state?}
      write_2b: {entity, field, value, mode, timestamp?}
    """
    if operation not in VALID_OPS:
        return {"error": f"operation '{operation}' not recognized", "valid": list(VALID_OPS)}
    params = params or {}
    try:
        if operation == "recall_2a":
            return memory_recall.C1_recall_2a(
                params.get("entities", []), params.get("time_range", {}), conn
            )
        if operation == "recall_2b":
            return memory_recall.C2_recall_2b(params["entity"], conn)
        if operation == "recall_2c":
            return memory_recall.C3_recall_2c(params.get("patterns"), conn)
        if operation == "recall_2d":
            return memory_recall.C4_recall_2d(params.get("recent", 0), conn)
        if operation == "append_2d":
            return memory_write.D6_append_2d_entry(
                conn,
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
                conn,
                params["entity"],
                params["field"],
                params["value"],
                params["mode"],
                params.get("timestamp"),
            )
    except (ValueError, KeyError) as e:
        return {"error": f"{type(e).__name__}: {e}", "operation": operation}
    return {"error": "unreachable"}