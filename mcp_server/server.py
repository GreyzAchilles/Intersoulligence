"""mcp_server.server — MCP server 入口

注册 4 个工具（persona_layer0_get / persona_layer1_get /
persona_layer2_query / persona_runtime_op），通过 stdio transport 暴露给 work agent。

来源：PRD §11 序号 23, §7.3
       mcp 官方 Python SDK（2.x: MCPServer / 1.x: FastMCP，用法兼容）
"""

from __future__ import annotations

import sys
from typing import Any

from persona_runtime import create_harness
from persona_runtime.config import load_config
from persona_runtime.harness import Harness

from .tools import (
    persona_layer0_get,
    persona_layer1_get,
    persona_layer2_query,
    persona_runtime_op,
)

try:
    # mcp >= 2.0：官方 SDK 将 FastMCP 更名为 MCPServer（@tool / run / stdio 用法兼容）
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:  # pragma: no cover - 依赖 mcp 1.x 时走此分支
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:  # pragma: no cover
        FastMCP = None  # type: ignore[assignment]


def _ensure_harness(state: dict[str, Any]) -> Harness:
    """惰性创建并缓存 harness 单例（每个 MCP server 实例一个）。"""
    if state.get("harness") is None:
        config = load_config()
        h = create_harness(config)
        h.init()
        state["harness"] = h
    return state["harness"]


_STATE: dict[str, Any] = {}


def _build_server() -> Any:
    """构造 FastMCP server 并注册 4 个工具。

    用 lazy harness，避免模块导入就开 SQLite 连接。
    """
    if FastMCP is None:
        raise RuntimeError(
            "mcp SDK not installed. install with `uv sync --extra dev` 或添加 `mcp` 到 dependencies"
        )

    mcp = FastMCP("intersoulligence")

    @mcp.tool()
    def persona_layer0_get_tool(field: str) -> dict[str, Any]:
        """获取 Layer 0 字段: schema / anchors / value_kernel / scenarios /
        self_check_policy / initial_scenario_check"""
        h = _ensure_harness(_STATE)
        return persona_layer0_get(field, h.config)

    @mcp.tool()
    def persona_layer1_get_tool(
        field: str, current_scenario: str = ""
    ) -> dict[str, Any]:
        """获取 Layer 1 prompt: stage_signal_prompt / ongoing_scenario_check

        Args:
            field: 见 PRD §7.3。
            current_scenario: ongoing_scenario_check 必填。
        """
        h = _ensure_harness(_STATE)
        return persona_layer1_get(field, h.config, current_scenario)

    @mcp.tool()
    def persona_layer2_query_tool(
        operation: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Layer 2 查询/写入: recall_2a / 2b / 2c / 2d, append_2d,
        maybe_2d_trigger, write_2b

        Args:
            operation: 见 PRD §7.3。
            params: 各 operation 不同。
        """
        h = _ensure_harness(_STATE)
        return persona_layer2_query(operation, h.conn, params)

    @mcp.tool()
    def persona_runtime_op_tool(
        operation: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """运行时操作: parse / validate / self_check / snapshot / decay / spawn。

        Args:
            operation: 见 PRD §7.3（13 个）。
            params: 各 operation 不同。
        """
        h = _ensure_harness(_STATE)
        return persona_runtime_op(operation, h.config, params, conn=h.conn)

    return mcp


def main() -> None:
    """stdio transport 入口：被 intersoulligence-server 脚本调用。"""
    mcp = _build_server()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()