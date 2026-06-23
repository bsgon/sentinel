"""Investigation Agent for Sentinel.

Implementation:
- Connects to the local Sentinel MCP Server using stdio transport parameters.
- Uses `sys.executable` and `-m mcp_server.server` to execute the server subprocess in the current virtual environment context.
- Invokes MCP database tools to build a comprehensive user context dossier.

Design Rationale:
- Tool Access Control: Only the InvestigationAgent has access to the database via MCP tools.
  Keeping data retrieval isolated to a single agent prevents other agents from
  unnecessarily invoking tools, reduces token overhead, and avoids prompt pollution.
- Neutral Data Gathering: The InvestigationAgent compiles facts neutrally. It does
  not make policy decisions or recommend actions, keeping the context compilation phase
  free of decision-making bias.

Behavior:
- Accepts account details request prompt.
- Queries get_account, get_recent_transactions, get_flags, and get_prior_cases.
- Compiles the retrieved facts into a markdown formatted dossier and returns it.
"""

import os
import sys
from google.adk import Agent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioConnectionParams
from mcp import StdioServerParameters

# Read configuration from the environment
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Define the MCP Server parameters to spawn the FastMCP server as a stdio subprocess.
# Using sys.executable ensures it runs using the same virtual environment Python interpreter.
mcp_tools = MCPToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_server.server"],
        ),
        timeout=10.0,
    )
)

# Define the Investigation Agent using the ADK Agent class
investigation_agent = Agent(
    name="investigation_agent",
    model=MODEL_NAME,
    description="Assembles a comprehensive context dossier on the flagged account using MCP tools.",
    instruction=(
        "You are an Investigation Agent. Your job is to gather all necessary context regarding "
        "a flagged account. You must call the available MCP tools to query the database: "
        "1. get_account (query account details like country, risk score, KYC level, status) "
        "2. get_recent_transactions (query recent transactions for activity check) "
        "3. get_flags (query all triggered risk flags on this account) "
        "4. get_prior_cases (query past support or investigation cases for this account) "
        "Query these tools using the provided account_id, and compile all returned facts "
        "into a single, clean, cohesive, and detailed markdown dossier. "
        "Do not make decisions, resolve flags, or recommend actions; only gather and present the factual data."
    ),
    tools=[mcp_tools],
)

