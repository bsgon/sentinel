"""Approval Gate for Sentinel.

This module implements the Human-in-the-Loop (HITL) check for high-risk actions.
"""

from google.adk import Context
from google.adk.events import RequestInput
from google.adk.workflow import node

@node(rerun_on_resume=False)
async def approval_gate(
    ctx: Context,
    action: str,
    dossier: str,
    reasoning: str,
    account_id: str,
    flag_id: str,
):
    """Pauses the workflow and requests human confirmation for high-risk actions.

    Implementation:
    - Yields a RequestInput event with a detailed text prompt detailing the incident flag, account, proposed action, and compiled investigation dossier.
    - Captures the operator's response value when resumed.

    Design:
    - Rerun_on_resume is False to avoid double-pause loops upon resume.
    - Decoupled from the actual state change logic.

    Behavior:
    - Pauses execution and yields RequestInput. Resumes with operator input response.
    """
    message = (
        f"\n======================================================================\n"
        f"🚨 CRITICAL ACTION REQUIRED: Human-in-the-Loop Approval Gate Required 🚨\n"
        f"======================================================================\n"
        f"Risk Flag ID:    {flag_id}\n"
        f"Account ID:      {account_id}\n"
        f"Proposed Action: {action.upper()}\n"
        f"\n"
        f"--- TRIAGE REASONING ---\n"
        f"{reasoning.strip()}\n"
        f"\n"
        f"--- INVESTIGATION DOSSIER ---\n"
        f"{dossier.strip()}\n"
        f"======================================================================\n"
        f"Approve high-risk action '{action}'? (approve/deny): "
    )
    # Yield a RequestInput event to pause the workflow
    yield RequestInput(
        message=message,
        response_schema=str
    )

