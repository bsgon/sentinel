"""Triage Agent for Sentinel.

Implementation:
- Formulates a classification request prompt combining incident flag details and formatted rule policy text.
- Leverages Gemini and strict Pydantic output schema constraints to parse classifications.

Design Rationale:
- Confinement & Security: TriageAgent has NO access to external tools or databases.
  This prevents it from making state-changing calls or reading unauthorized data.
  It acts as a pure decision function (pure classifier) operating on inputs.
- Fast & Constrained policy enforcement: By restricting outputs to a strict Pydantic
  schema and specific allowed actions ('monitor', 'request_kyc', 'escalate', 'freeze_account'),
  we guarantee policy compliance and facilitate deterministic downstream routing.

Behavior:
- Accepts incident flag details and rules policy as input.
- Outputs a TriageResult object containing the severity, category, recommended action, and detailed reasoning.
"""

import os
from typing import Literal
from pydantic import BaseModel, Field
from google.adk import Agent

# Read configuration from the environment
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

class TriageResult(BaseModel):
    """Pydantic schema to enforce structured and validated output from the TriageAgent."""
    severity: Literal["low", "med", "high"] = Field(
        description="The severity classification of the risk flag (low, med, high)."
    )
    category: str = Field(
        description="The category of the violation rule (e.g., Wash Trading, Structuring, IP Mismatch, Sanctions, etc.)."
    )
    recommended_action: Literal["monitor", "request_kyc", "escalate", "freeze_account"] = Field(
        description="The recommended resolution action. Must strictly be one of the allowed actions."
    )
    reasoning: str = Field(
        description="A detailed explanation and justification of the triage classification and the recommended action."
    )

# Define the Triage Agent using the ADK Agent class
triage_agent = Agent(
    name="triage_agent",
    model=MODEL_NAME,
    description="Classifies Trust & Safety flags using predefined rules and policies.",
    instruction=(
        "You are a Trust & Safety Triage Agent for a crypto exchange. "
        "Your task is to classify incoming flags based on the rules provided in the prompt. "
        "You must determine the severity (low, med, or high), the category (e.g., IP Mismatch, Wash Trading), "
        "and a recommended action. "
        "The allowed actions are strictly constrained to: 'monitor', 'request_kyc', 'escalate', "
        "and 'freeze_account'. You must not choose or propose any other actions. "
        "You must also provide a detailed explanation of your reasoning for this triage decision in the reasoning field."
    ),
    output_schema=TriageResult,
)


