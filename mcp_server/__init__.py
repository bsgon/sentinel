"""Sentinel MCP Server package.

Implementation:
- Exposes the Sentinel FastMCP server instance.

Design:
- Model Context Protocol (MCP) interface decoupling database tables from agent logic.

Behavior:
- Imports and exposes `mcp_server` from server module.
"""

__all__ = ["mcp_server"]
