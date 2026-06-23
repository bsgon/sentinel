"""Sentinel Trust & Safety incident-triage agents package.

Implementation:
- Exposes orchestrator, triage, investigation, approval gate, and report agents/workflows.
- Wires components together using ADK.

Design Rationale:
- A clean multi-agent system where each agent is constrained to a single clear responsibility.
- Decouples classification, context gathering, approval, and report formatting.

Behavioral Interface:
- orchestrator_agent: Main entrypoint workflow coordinating execution.
- triage_agent: Constrained risk categorizer.
- investigation_agent: Dossier compiler calling MCP database tools.
- approval_gate: HITL verification node for high-risk actions.
- report_agent: RCA report generator skill invoker.
"""

from sentinel.orchestrator import orchestrator_agent
from sentinel.triage import triage_agent
from sentinel.investigation import investigation_agent
from sentinel.approval import approval_gate
from sentinel.report import report_agent

__all__ = [
    "orchestrator_agent",
    "triage_agent",
    "investigation_agent",
    "approval_gate",
    "report_agent",
]
