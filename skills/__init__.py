"""Sentinel Skills package.

Implementation:
- Exposes custom agentic tools/skills.

Design:
- Decouples custom code utilities from ADK framework flow.

Behavior:
- Imports and exposes `generate_rca_report` from the rca_report module.
"""

from skills.rca_report import generate_rca_report

__all__ = ["generate_rca_report"]
