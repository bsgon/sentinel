# MCP Server Patterns — mcp==1.28.0 (FastMCP)
> Reference grounding for the build agent. All signatures verified against the installed package.
> Do NOT invent APIs. If something is not here, check the source in `.venv/lib/python3.12/site-packages/mcp/`.

---

## 1. Core import

```python
from mcp.server.fastmcp import FastMCP
```

---

## 2. FastMCP constructor

```python
FastMCP(
    name: str | None = None,          # server display name (e.g. "Sentinel")
    instructions: str | None = None,  # optional description shown to clients
    debug: bool = False,
    log_level: Literal["DEBUG","INFO","WARNING","ERROR","CRITICAL"] = "INFO",
    # HTTP transport settings (only relevant for sse/streamable-http):
    host: str = "127.0.0.1",
    port: int = 8000,
    sse_path: str = "/sse",           # SSE endpoint path
    message_path: str = "/messages/",
    streamable_http_path: str = "/mcp",
    stateless_http: bool = False,
)
```

**Minimal example:**
```python
from mcp.server.fastmcp import FastMCP

mcp_server = FastMCP("Sentinel")
```

---

## 3. Defining tools with @mcp_server.tool()

```python
@mcp_server.tool()
async def get_account(account_id: str) -> dict:
    """Docstring is shown to the LLM as the tool description — write it clearly."""
    # implementation
    return {"account_id": account_id, ...}

@mcp_server.tool()
async def get_recent_transactions(account_id: str) -> list[dict]:
    """Returns transaction history for an account, newest first."""
    ...
```

**Rules:**
- Tools must be `async def`.
- Return type should be JSON-serialisable (`dict`, `list`, `str`, `int`, `float`, `bool`).
- The function docstring becomes the tool description sent to the LLM.
- Parameter names and type annotations are exposed as the tool schema.
- Read-only tools only — no write or state-changing operations in this project.

---

## 4. Running the server

### Stdio transport (for ADK MCPToolset with StdioConnectionParams)
```python
if __name__ == "__main__":
    mcp_server.run(transport="stdio")
```

### SSE transport (HTTP, for ADK MCPToolset with SseConnectionParams)
```python
if __name__ == "__main__":
    mcp_server.run(transport="sse")
    # Listens on http://127.0.0.1:8000/sse by default
```

### Streamable HTTP transport
```python
if __name__ == "__main__":
    mcp_server.run(transport="streamable-http")
    # Listens on http://127.0.0.1:8000/mcp by default
```

---

## 5. Complete working example (Sentinel pattern)

```python
"""Sentinel MCP Server."""

import csv
import os
from mcp.server.fastmcp import FastMCP

mcp_server = FastMCP("Sentinel")

DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))

def _read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

@mcp_server.tool()
async def get_account(account_id: str) -> dict:
    """Fetch account metadata by ID. Returns error dict if not found."""
    for row in _read_csv(os.path.join(DATA_DIR, "accounts.csv")):
        if row["account_id"] == account_id:
            return {
                "account_id": row["account_id"],
                "kyc_level": int(row["kyc_level"]) if row["kyc_level"] else None,
                "country": row["country"],
                "risk_score": float(row["risk_score"]),
                "status": row["status"],
            }
    return {"error": f"Account {account_id} not found"}

@mcp_server.tool()
async def get_recent_transactions(account_id: str) -> list[dict]:
    """Fetch all transactions for an account, sorted newest-first."""
    rows = [r for r in _read_csv(os.path.join(DATA_DIR, "transactions.csv"))
            if r["account_id"] == account_id]
    for r in rows:
        r["amount"] = float(r["amount"])
    return sorted(rows, key=lambda x: x["timestamp"], reverse=True)

@mcp_server.tool()
async def get_flags(account_id: str) -> list[dict]:
    """Fetch risk flags for an account, sorted newest-first."""
    rows = [r for r in _read_csv(os.path.join(DATA_DIR, "flags.csv"))
            if r["account_id"] == account_id]
    return sorted(rows, key=lambda x: x["created_at"], reverse=True)

@mcp_server.tool()
async def get_prior_cases(account_id: str) -> list[dict]:
    """Fetch historical investigation cases for an account, sorted newest-first."""
    rows = [r for r in _read_csv(os.path.join(DATA_DIR, "cases.csv"))
            if r["account_id"] == account_id]
    return sorted(rows, key=lambda x: x["opened_at"], reverse=True)

if __name__ == "__main__":
    mcp_server.run(transport="stdio")
```

---

## 6. Wiring to ADK Agent (stdio transport)

In the ADK agent file:

```python
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioConnectionParams
from mcp import StdioServerParameters

mcp_tools = MCPToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="python",
            args=["mcp_server/server.py"],
        ),
        timeout=10.0,
    ),
)

investigation_agent = Agent(
    name="investigation_agent",
    model="gemini-2.5-flash",
    instruction="Use MCP tools to gather account context.",
    tools=[mcp_tools],
)
```

---

## 7. Testing tools directly (without the ADK runner)

```python
import asyncio

async def test():
    result = await get_account("ACC-010")
    print(result)

asyncio.run(test())
```

This is how `verify_mcp.py` works — call the async tool functions directly in asyncio without spinning up the full MCP transport.

---

## 8. What FastMCP does NOT support (avoid these)

- `@mcp_server.resource()` — resources exist but are NOT needed for this project; use tools only.
- Synchronous (`def`) tool functions — must be `async def`.
- State mutation through tools — this project is READ-ONLY; no write tools.
- `SseServerParams` — this name does NOT exist in `mcp==1.28.0`; use `SseConnectionParams` from `google.adk.tools.mcp_tool.mcp_toolset` on the ADK side.
