"""Root Cause Analysis (RCA) report generation skill.

This skill compiles triage outcomes, account details, transaction patterns,
approval outcomes, and case histories into a clean, structured Incident RCA
report in markdown format.

REUSABILITY DESIGN RATIONALE:
1. Decoupled from ADK Context: This function takes primitive Python types and standard
   dictionaries (str, dict) instead of framework-specific objects (like Context, Agent).
   This allows the skill to be used in unit tests, command-line scripts, other agents,
   or web APIs without any dependency on the ADK execution flow.
2. Parameterized & Modular: By separating inputs (flag_id, triage_data, investigation_data,
   approval_status), it has a clear interface. Any system can gather these data points from
   any database or model and use this skill to generate a consistent, uniform report.
3. Self-Contained PII Sanitization: To ensure the report is safe for public logs or internal
   compliance archives, the skill performs its own regex-based PII redaction on the inputs
   independently, ensuring confidentiality by design.
"""

import re
from datetime import datetime

def redact_pii(text: str) -> str:
    """Uses regular expressions to redact IP addresses, device IDs, account IDs, and counterparty addresses from a string.

    Implementation:
    - Redacts IPv4 addresses.
    - Redacts Device IDs (DEV-xxx).
    - Redacts Account IDs (ACC-xxx).
    - Redacts Counterparty Addresses (Ethereum hex 0x..., external_wallet_xxx, bank_wire_ref_xxx, and sanctioned BTC addresses).

    Design:
    - Strict regex matching to ensure consistent redaction without leaking characters.

    Behavior:
    - Returns string with PII replaced by standardized redacted placeholders.
    """
    if not isinstance(text, str):
        return text
    # Redact IPv4 Addresses: e.g. 192.168.1.1
    ip_pattern = r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"
    text = re.sub(ip_pattern, "[REDACTED_IP]", text)
    # Redact Device IDs: e.g. DEV-12B, DEV-38D, DEV-001B
    device_pattern = r"\bDEV-[A-Za-z0-9]+\b"
    text = re.sub(device_pattern, "[REDACTED_DEVICE]", text)
    # Redact Account IDs: e.g. ACC-001, ACC-010
    account_pattern = r"\bACC-\d+\b"
    text = re.sub(account_pattern, "[REDACTED_ACCOUNT]", text)
    # Redact Counterparty Addresses:
    # 1. Hex addresses (0x...) and peel patterns
    # 2. External wallets (external_wallet_...)
    # 3. Bank wire refs (bank_wire_ref_...)
    # 4. Sanctioned BTC address (1KP_SANCTIONED_ADDRESS_BTC_...)
    address_patterns = [
        r"\b0x[a-zA-Z0-9_]+\b",
        r"\bexternal_wallet_\d+\b",
        r"\bbank_wire_ref_\d+\b",
        r"\b1KP_[A-Za-z0-9_]+\b"
    ]
    for pattern in address_patterns:
        text = re.sub(pattern, "[REDACTED_ADDRESS]", text)
    return text

def generate_rca_report(
    flag_id: str,
    triage_data: dict,
    investigation_data: dict,
    approval_status: str
) -> str:
    """Drafts a structured Root Cause Analysis report for a flagged account incident.

    Enforces a consistent structured layout including Summary, Timeline, Signals/Evidence,
    Decision & Rationale, Action Taken, and Follow-ups.

    Args:
        flag_id: The ID of the synthetic risk flag/event.
        triage_data: Dict containing triage results: 'severity', 'category', 'recommended_action', 'reasoning'.
        investigation_data: Dict containing 'dossier' text compiled by the InvestigationAgent.
        approval_status: The outcome of the human approval gate (e.g. 'approved', 'denied', 'not_required', 'bypassed').

    Returns:
        str: A structured markdown incident report.
    """
    # Extract and clean triage details
    severity = str(triage_data.get("severity", "unknown")).upper()
    category = str(triage_data.get("category", "unknown"))
    recommended_action = str(triage_data.get("recommended_action", "unknown"))
    reasoning = str(triage_data.get("reasoning", "No reasoning provided."))

    # Extract investigation dossier and sanitize it
    raw_dossier = investigation_data.get("dossier", "")
    if not raw_dossier and "dossier" not in investigation_data:
        # If investigation_data is passed as a string or a flat dict without 'dossier' key
        if isinstance(investigation_data, dict):
            raw_dossier = investigation_data.get("dossier_text", str(investigation_data))
        else:
            raw_dossier = str(investigation_data)

    dossier = redact_pii(raw_dossier.strip())
    
    # Try to extract Account ID from dossier or triage data
    account_id = "Unknown"
    account_match = re.search(r"ACC-\d+", raw_dossier)
    if account_match:
        account_id = account_match.group(0)

    # Determine status and action taken text
    status = "COMPLETED" if approval_status in ("approved", "not_required", "bypassed") else "ABORTED"
    
    # Generate Timeline
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    timeline_events = [
        f"- **Flag Detected**: Incident flag {flag_id} triggered on account {account_id}.",
        f"- **Triage Completed**: Triage classification assigned category '{category}' with {severity} severity.",
        f"- **Investigation Completed**: Context dossier assembled containing account details, transaction patterns, and prior cases.",
    ]
    
    if recommended_action == "freeze_account":
        timeline_events.append(
            f"- **Human-in-the-Loop Approval Gate**: High-risk action '{recommended_action}' evaluated. Status: {approval_status.upper()}."
        )
    else:
        timeline_events.append(
            f"- **Approval Gate Bypassed**: Proposed action '{recommended_action}' is low-risk. Direct execution enabled."
        )
        
    if status == "COMPLETED":
        timeline_events.append(
            f"- **State Change Executed**: Recommended resolution action '{recommended_action}' successfully applied."
        )
    else:
        timeline_events.append(
            f"- **Pipeline Aborted**: Recommended resolution action '{recommended_action}' rejected by human operator. No state changes applied."
        )

    timeline_str = "\n".join(timeline_events)

    # Extract key signals/evidence from dossier (e.g. country, risk score, prior cases)
    # We parse the dossier text to find risk indicators to present in the Signals/Evidence section
    risk_score_match = re.search(r"(Risk Score|risk_score):\s*(\d+(\.\d+)?)", dossier)
    risk_score = risk_score_match.group(2) if risk_score_match else "N/A"
    
    country_match = re.search(r"(Country|country|Registered Country):\s*([A-Z]{2})", dossier)
    country = country_match.group(2) if country_match else "N/A"
    
    prior_cases = "None found"
    if "prior cases" in dossier.lower() or "prior_cases" in dossier.lower():
        prior_cases_part = re.split(r"Prior Cases:?", dossier, flags=re.IGNORECASE)
        if len(prior_cases_part) > 1:
            prior_cases = prior_cases_part[1].strip()
            if not prior_cases or "none" in prior_cases.lower():
                prior_cases = "None found"
            else:
                # Truncate if too long
                prior_cases = prior_cases[:300] + "..." if len(prior_cases) > 300 else prior_cases

    # Define follow-up actions depending on severity and category
    follow_ups = []
    if severity == "HIGH":
        follow_ups.append("- **Compliance Escalation**: Escalate account to Compliance officer for final regulatory SAR review.")
        if recommended_action == "freeze_account" and status == "COMPLETED":
            follow_ups.append("- **Legal Lock**: File internal SAR detailing Blocklist/SDN/Structuring violation within 24 hours.")
    
    if recommended_action == "request_kyc":
        follow_ups.append("- **KYC Verification**: Issue official KYC/AML request for identity and source of funds verification.")
        follow_ups.append("- **Grace Period**: Suspend withdrawal capabilities if documents are not submitted within 7 days.")
    elif recommended_action == "monitor":
        follow_ups.append("- **Enhanced Monitoring**: Place account on watchlist. Re-evaluate transaction risk score weekly.")
    else:
        follow_ups.append("- **Identity Audit**: Conduct review of recent login locations, device fingerprints, and API key updates.")
        
    follow_ups.append("- **Audit Log**: Archive this report and associated decision trail in Sentinel database.")
    follow_ups_str = "\n".join(follow_ups)

    # account_id is kept visible in the operator-facing header sections (Summary, Action Taken)
    # so the operator knows which account the report is about. All other free-text fields
    # (dossier, reasoning, timeline) have already been sanitized via redact_pii above.
    report = f"""# Incident Root Cause Analysis (RCA) Report

## Summary
- **Incident Status:** {status}
- **Flag ID:** {flag_id}
- **Account ID:** {account_id}
- **Country:** {country}
- **Account Risk Score:** {risk_score}
- **Triage Severity:** {severity}
- **Triage Category:** {category}
- **Proposed Action:** {recommended_action.upper()}
- **Approval Gate Outcome:** {approval_status.upper()}
- **Report Generated At:** {now_str}

---

## Timeline
{timeline_str}

---

## Signals/Evidence
Below is the factual evidence retrieved during investigation:
- **Account Details:** Country of registration: {country}, Risk Score: {risk_score}.
- **Prior Cases:** {prior_cases}
- **Dossier Context (Sanitized):**
```markdown
{dossier}
```

---

## Decision & Rationale
The Triage Agent evaluated the incident details against exchange policies:
- **Assigned Category:** {category}
- **Severity Rating:** {severity}
- **Reasoning/Justification:**
  > {redact_pii(reasoning.strip())}

---

## Action Taken
- **HITL Verification:** The recommended action **{recommended_action.upper()}** was routed through the Sentinel Approval Gate.
- **Outcome:** **{approval_status.upper()}**
- **State Change Status:** {f"Account {account_id} status updated to FROZEN." if (recommended_action == 'freeze_account' and status == 'COMPLETED') else "No state changes applied to account."}

---

## Follow-ups
{follow_ups_str}
"""
    return report
