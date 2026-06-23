"""Report Agent for Sentinel.

Implementation:
- Encapsulates the custom RCA report generation skill (`generate_rca_report` function tool).
- Wires the skill to the Agent instance tools list.

Design Rationale:
- Presentation & Formatting Decoupling: The ReportAgent is decoupled from triage decisions
  and direct database queries. Its sole concern is structuring and formatting the final RCA report.
- Skill integration: It encapsulates the RCA generation skill. This allows formatting guidelines or templates to change without impacting the core triage or investigation logic.

Behavior:
- Accepts compiled triage outcomes, dossier data, and approval gate status.
- Invokes the report skill and returns the final markdown RCA report text verbatim.
"""

import os
from google.adk import Agent
from skills.rca_report import generate_rca_report

# Read configuration from the environment
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Define the Report Agent using the ADK Agent class
report_agent = Agent(
    name="report_agent",
    model=MODEL_NAME,
    description="Generates the final Root Cause Analysis (RCA) report for incidents.",
    instruction=(
        "You are a Report Agent. Your task is to draft a structured Root Cause Analysis "
        "report for a flagged account incident. "
        "You must call the generate_rca_report tool to compile the final report. "
        "Provide: "
        "- flag_id: the ID of the flag "
        "- triage_data: a dictionary containing 'severity', 'category', 'recommended_action', and 'reasoning' "
        "- investigation_data: a dictionary containing a 'dossier' key with the investigation dossier text. "
        "- approval_status: the status of the human approval (e.g., 'approved', 'denied', 'not_required', 'bypassed') "
        "CRITICAL: You must return the EXACT output of the generate_rca_report tool verbatim in your final response. "
        "Do not summarize, do not prefix it with conversational text, and do not edit it. Simply output the raw report."
    ),
    tools=[generate_rca_report],
)


