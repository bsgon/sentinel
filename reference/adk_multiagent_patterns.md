# ADK Multi-Agent Patterns — google-adk==2.3.0
> Reference grounding for the build agent. All signatures verified against the installed package.
> Do NOT invent APIs. If something is not here, check the source in `.venv/lib/python3.12/site-packages/google/adk/`.

---

## 1. Core imports (verified)

```python
from google.adk.agents import Agent          # alias: LlmAgent
from google.adk.workflow import Workflow, node
from google.adk.agents.context import Context
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool.mcp_toolset import (
    MCPToolset,
    StdioConnectionParams,
    StdioServerParameters,   # from mcp package
    SseConnectionParams,
)
import google.genai.types as types
```

---

## 2. Agent (LlmAgent)

```python
Agent(
    name: str,
    description: str = "",
    model: str = "",           # e.g. "gemini-2.5-flash"
    instruction: str | Callable[[ReadonlyContext], str] = "",
    tools: list[Callable | BaseTool | BaseToolset] = [],
    sub_agents: list[BaseAgent] = [],
    output_schema: type | dict | None = None,
    output_key: str | None = None,
    input_schema: type[BaseModel] | None = None,
    # callbacks
    before_agent_callback: Callable | None = None,
    after_agent_callback: Callable | None = None,
    before_model_callback: Callable | None = None,
    after_model_callback: Callable | None = None,
    before_tool_callback: Callable | None = None,
    after_tool_callback: Callable | None = None,
    # flow control
    disallow_transfer_to_parent: bool = False,
    disallow_transfer_to_peers: bool = False,
    rerun_on_resume: bool = False,
    wait_for_output: bool = False,
    mode: Literal["chat", "task", "single_turn"] | None = None,
    parallel_worker: bool | None = None,
)
```

**Minimal working example:**
```python
from google.adk.agents import Agent

triage_agent = Agent(
    name="triage_agent",
    model="gemini-2.5-flash",
    description="Classifies T&S flags.",
    instruction="You are a triage agent. Classify flags as low/med/high.",
    tools=[],
)
```

---

## 3. Workflow + @node

`Workflow` is a graph-based orchestrator. Nodes are async generator functions decorated with `@node`.

```python
from google.adk.workflow import Workflow, node
from google.adk.agents.context import Context

@node(rerun_on_resume=True)   # rerun_on_resume: re-executes this node when workflow resumes after a pause
async def my_node(ctx: Context, some_input: str) -> dict:
    # yield events (e.g. RequestInput) OR just return
    return {"result": "done"}

my_workflow = Workflow(
    name="my_workflow",
    edges=[
        ("START", my_node),      # "START" is the reserved entry point
        (my_node, "END"),        # "END" is the reserved exit point
        # (node_a, node_b),      # sequential edge
        # ([node_a, node_b], node_c),  # fan-in
    ],
)
```

**Edges cheat-sheet:**
- `("START", node_fn)` — graph entry
- `(node_a, node_b)` — node_a → node_b
- `(node_a, "END")` or just omit the last edge (auto-terminates)
- Parallel fan-out: `(node_a, [node_b, node_c])`
- Fan-in: `([node_b, node_c], node_d)`

---

## 4. Human-in-the-loop: RequestInput

To pause a workflow and wait for human input, `yield` a `RequestInput` event inside a `@node`.

```python
from google.adk.workflow import node
from google.adk.agents.context import Context
from google.adk.events import RequestInput   # correct import path

@node(rerun_on_resume=False)  # False: do NOT re-run this node on resume (avoids double-pause)
async def approval_gate(ctx: Context, action: str, account_id: str):
    yield RequestInput(
        message=f"Approve '{action}' for account '{account_id}'? (approve/deny)"
    )
    # Execution resumes here after human provides input.
    # The human's response is available via ctx.user_content or the runner's resume mechanism.
```

**Important:** `rerun_on_resume=False` on the gate node; `rerun_on_resume=True` on the orchestrator node that called the gate (so the orchestrator re-enters and reads the gate's output).

---

## 5. Runner + InMemorySessionService

```python
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
import google.genai.types as types

session_service = InMemorySessionService()

runner = Runner(
    app_name="sentinel",          # arbitrary string identifier
    agent=root_agent,             # Agent or Workflow instance
    session_service=session_service,
    # optional:
    # artifact_service=InMemoryArtifactService(),
    # memory_service=InMemoryMemoryService(),
)

# Create a session
session = session_service.create_session(
    app_name="sentinel",
    user_id="operator-1",
    # session_id="custom-id",   # optional; auto-generated if omitted
    # state={"key": "value"},   # optional initial state
)

# Run (async)
async def run_agent(message: str):
    content = types.Content(role="user", parts=[types.Part.from_text(text=message)])
    async for event in runner.run_async(
        user_id=session.user_id,
        session_id=session.id,
        new_message=content,
    ):
        if event.is_final_response():
            print(event.content.parts[0].text)

# Run (sync alternative)
for event in runner.run(
    user_id=session.user_id,
    session_id=session.id,
    new_message=types.Content(role="user", parts=[types.Part.from_text(text="FLAG-001")]),
):
    pass
```

---

## 6. MCPToolset — wiring an MCP server to an Agent

Use `MCPToolset` when the MCP server is launched as a **subprocess** (stdio transport).

```python
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioConnectionParams
from mcp import StdioServerParameters

mcp_tools = MCPToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="python",
            args=["-m", "mcp_server.server"],   # or path to server script
            env=None,                            # inherits current env by default
        ),
        timeout=10.0,   # seconds to wait for server startup
    ),
    # tool_filter=["get_account", "get_flags"],  # optional: whitelist specific tools
)

investigation_agent = Agent(
    name="investigation_agent",
    model="gemini-2.5-flash",
    instruction="Use the MCP tools to build an account dossier.",
    tools=[mcp_tools],   # pass MCPToolset directly in tools list
)
```

**SSE transport (if server runs as HTTP):**
```python
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, SseConnectionParams

mcp_tools = MCPToolset(
    connection_params=SseConnectionParams(
        url="http://localhost:8000/sse",
        headers={"Authorization": "Bearer ..."},  # optional
        timeout=10.0,
    ),
)
```

---

## 7. Multi-agent topology patterns

### Sequential pipeline (Orchestrator delegates via sub_agents)
```python
orchestrator = Agent(
    name="orchestrator",
    model="gemini-2.5-flash",
    instruction="Run triage then investigation then report.",
    sub_agents=[triage_agent, investigation_agent, report_agent],
)
```

### Graph-based pipeline (Workflow with explicit edges)
```python
@node(rerun_on_resume=True)
async def run_triage(ctx: Context, flag_id: str) -> dict:
    result = await ctx.run_agent(triage_agent, flag_id=flag_id)
    return result

@node(rerun_on_resume=True)
async def run_investigation(ctx: Context, triage_result: dict) -> dict:
    result = await ctx.run_agent(investigation_agent, triage=triage_result)
    return result

pipeline = Workflow(
    name="sentinel_pipeline",
    edges=[
        ("START", run_triage),
        (run_triage, run_investigation),
        (run_investigation, "END"),
    ],
)
```

---

## 8. Context object (inside @node / callbacks)

```python
ctx.session          # current Session object
ctx.session.state    # dict — read/write persistent state within the session
ctx.user_content     # the Content that triggered this invocation
ctx.invocation_id    # unique ID for this run
await ctx.run_agent(agent, **kwargs)  # programmatically call a sub-agent
```

---

## 9. Gemini configuration

```python
import os
# Read from environment — never hardcode
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
# GOOGLE_API_KEY must be set in env; the ADK reads it automatically via google-genai.
```

Supported model strings (as of 2026-06):
- `"gemini-2.5-flash"` — fast, good for triage/investigation
- `"gemini-2.5-pro"` — higher quality, slower
