"""mcp_server — intersoulligence MCP server

暴露 4 个 MCP 工具给 work agent（opencode / Claude Code 等）：
- persona_layer0_get
- persona_layer1_get
- persona_layer2_query
- persona_runtime_op

入口：`python -m mcp_server.server` 或 console script `intersoulligence-server`
"""

from .server import main

__all__ = ["main"]