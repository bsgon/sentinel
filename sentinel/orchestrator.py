"""Orchestrator Agent for Sentinel.

This agent acts as the main entrypoint and coordinator of the incident-triage pipeline.
It takes a `flag_id`, routes execution through the Triage and Investigation agents,
checks the decision against the Approval Gate for high-risk actions, logs the decision
trail (with PII redacted), and invokes the Report Agent to draft the final RCA report.

Architectural Rationale for Separation:
1. Separation of Control vs Content: The OrchestratorAgent is a state machine / control flow coordinator.
   It does not contain direct LLM reasoning about flags or databases, separating execution flow from logic.
2. Single Responsibility: It manages logging, PII redaction, and coordinates the sequential execution
   and conditional branching (ApprovalGate) across specialized agents.
"""

import csv
import logging
import os
import re
from google.adk import Context, Workflow
from google.adk.workflow import node

# Import sub-agents and gate nodes
from sentinel.triage import triage_agent
from sentinel.investigation import investigation_agent
from sentinel.report import report_agent
from sentinel.approval import approval_gate

# Set up logging
logger = logging.getLogger("sentinel.orchestrator")
logging.basicConfig(level=logging.INFO)

# Helper: Redact PII (IP addresses, Device IDs, Account IDs, and Counterparty Addresses) from logs and outputs
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

# Helper: Fetch flag details from CSV
def _get_flag_details(flag_id: str) -> dict | None:
    """Fetches details of a specific flag by ID from the database.

    Implementation: Reads from synthetic flags.csv database.
    Design: Simple CSV parser.
    Behavior: Returns the matching flag row dictionary, or None if not found.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    flags_file = os.path.abspath(os.path.join(current_dir, "..", "data", "flags.csv"))
    if not os.path.exists(flags_file):
        return None
    with open(flags_file, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["flag_id"] == flag_id:
                return row
    return None

# Helper: Load rules from CSV
def _load_rules() -> list[dict]:
    """Loads exchange policy rules from the database.

    Implementation: Reads from rules.csv.
    Design: Separates rules configuration from agent instructions.
    Behavior: Returns a list of dictionaries detailing rule configurations.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    rules_file = os.path.abspath(os.path.join(current_dir, "..", "data", "rules.csv"))
    if not os.path.exists(rules_file):
        return []
    rules = []
    with open(rules_file, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rules.append(row)
    return rules

def _format_rules_policy(rules: list[dict]) -> str:
    """Formats rules into a policy instruction string for the triage agent.

    Implementation: Iterates rules and compiles a bulleted description.
    Design: Provides grounding instructions to constrain the triage agent.
    Behavior: Returns formatted string.
    """
    policy = []
    for rule in rules:
        policy.append(
            f"- Rule {rule['rule_id']} ({rule['name']}): {rule['description']}. "
            f"Default severity: {rule['severity_default']}. Recommended action: {rule['recommended_action']}."
        )
    return "\n".join(policy)

# Helper: Update account status in accounts database
def _update_account_status(account_id: str, new_status: str) -> None:
    """Updates the status of an account in the synthetic accounts CSV database.

    Implementation:
    - Reads accounts.csv.
    - Updates matching row status.
    - Overwrites accounts.csv with updated rows.

    Design:
    - Direct write state action executed on successful operator approval.

    Behavior:
    - Modifies the CSV status on disk and prints logs.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    accounts_file = os.path.abspath(os.path.join(current_dir, "..", "data", "accounts.csv"))
    if not os.path.exists(accounts_file):
        logger.warning(f"Accounts CSV file not found at {accounts_file}. Cannot update status.")
        return

    rows = []
    fieldnames = []
    with open(accounts_file, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row["account_id"] == account_id:
                msg = f"[Orchestrator] Executing state change: Updating account {account_id} status to '{new_status}'"
                logger.info(redact_pii(msg))
                print(redact_pii(msg))
                row["status"] = new_status
            rows.append(row)

    with open(accounts_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

# Helper: Log decision trail with PII redacted to standard logging and data/decision_trail.log
def _log_decision_trail(trail: dict) -> None:
    """Logs the pipeline decision trail with PII redacted to standard logging and appends to a log file.

    Implementation:
    - Redacts IPs, Device IDs, Account IDs, and Addresses using redact_pii.
    - Appends serialized redacted log to data/decision_trail.log.

    Design:
    - Compliance archiving by design.

    Behavior:
    - Writes to standard log and appends to disk.
    """
    import json
    from datetime import datetime

    trail_copy = dict(trail)
    trail_copy["timestamp"] = datetime.utcnow().isoformat() + "Z"

    # Serialize to string and redact PII
    trail_str = json.dumps(trail_copy, indent=2)
    redacted_trail = redact_pii(trail_str)

    # Log to logger and stdout
    logger.info(f"Decision Trail:\n{redacted_trail}")
    print(f"\n[Orchestrator] Pipeline Finished. Decision Trail Log:\n{redacted_trail}")

    # Append to decision_trail.log
    current_dir = os.path.dirname(os.path.abspath(__file__))
    log_file = os.path.abspath(os.path.join(current_dir, "..", "data", "decision_trail.log"))
    with open(log_file, mode="a", encoding="utf-8") as f:
        f.write(f"--- DECISION TRAIL AT {trail_copy['timestamp']} ---\n")
        f.write(redacted_trail)
        f.write("\n\n")

@node(rerun_on_resume=True)
async def orchestrator_workflow(ctx: Context, node_input: str) -> dict:
    """Orchestrates the triage, investigation, approval gate, and RCA report drafting.

    Implementation:
    - Node runs sequentially calling triage, investigation, conditional HITL approval gate, and reporting agents.
    - Bypasses approval gate during validation runs if ctx.state['bypass_gate'] is True.

    Design:
    - Structured workflow DAG using ADK framework.
    - Rerun_on_resume is True to re-evaluate the state upon approval gate completion.

    Behavior:
    - Validates flag format and existence, coordinates the sub-agents, redact PII in logs, and returns pipeline summary.
    """
    flag_id = str(node_input).strip()
    # Input Validation: Format check
    if not re.match(r"^FLG-\d{3}$", flag_id):
        raise ValueError(f"Invalid Flag ID format: '{flag_id}'. Expected format is 'FLG-XXX' where XXX is a 3-digit number.")

    logger.info(f"[Orchestrator] Starting Sentinel triage pipeline for Flag ID: {flag_id}")
    print(f"\n[Orchestrator] Starting Sentinel triage pipeline for Flag ID: {flag_id}")

    # Input Validation: Database existence check
    flag = _get_flag_details(flag_id)
    if not flag:
        raise ValueError(f"Flag ID '{flag_id}' not found in database.")

    # 2. Fetch Rules and format policy
    rules = _load_rules()
    rules_policy = _format_rules_policy(rules)

    import asyncio

    # NOTE: re-execution on resume — by design, rerun_on_resume=True causes the ADK to
    # re-run this node from the top after the approval gate resumes. Steps 1 & 2 therefore
    # execute twice for high-risk flags. This is an ADK architectural constraint: state
    # deltas written inside a paused node are not committed to the session service until
    # the node completes, so caching in ctx.state does not survive the pause.
    # The correct fix (P7 scope) is to split this into separate Workflow nodes
    # (run_triage → run_investigation → approval_gate → run_report) so each node completes
    # and commits before the next begins.
    account_id = flag["account_id"]

    # 3. Step 1: Run TriageAgent
    triage_prompt = f"""
    Please classify the following incident flag details:
    Flag ID: {flag['flag_id']}
    Account ID: {flag['account_id']}
    Transaction ID: {flag['tx_id']}
    Rule ID: {flag['rule_id']}
    Severity: {flag['severity']}
    Reason: {flag['reason']}

    Predefined Rules Policy:
    {rules_policy}
    """
    logger.info(f"[Orchestrator] [Step 1/4] Invoking TriageAgent for Flag ID: {flag_id}")
    print(f"[Orchestrator] [Step 1/4] Invoking TriageAgent...")
    triage_output = await ctx.run_node(triage_agent, node_input=triage_prompt)

    if hasattr(triage_output, "model_dump"):
        triage_data = triage_output.model_dump()
    elif isinstance(triage_output, dict):
        triage_data = triage_output
    else:
        triage_data = {
            "severity": getattr(triage_output, "severity", "low"),
            "category": getattr(triage_output, "category", "Unknown"),
            "recommended_action": getattr(triage_output, "recommended_action", "monitor"),
            "reasoning": getattr(triage_output, "reasoning", "No reasoning provided")
        }

    logger.info(redact_pii(f"[Orchestrator] Triage completed: {triage_data}"))
    print(redact_pii(f"[Orchestrator] Triage completed: {triage_data}"))
    await asyncio.sleep(5)

    # 4. Step 2: Run InvestigationAgent
    logger.info(f"[Orchestrator] [Step 2/4] Invoking InvestigationAgent for Account ID: {account_id}")
    print(f"[Orchestrator] [Step 2/4] Invoking InvestigationAgent...")
    investigation_prompt = f"Assemble an investigation dossier for account {account_id}."
    investigation_dossier = await ctx.run_node(investigation_agent, node_input=investigation_prompt)

    logger.info(f"[Orchestrator] Investigation completed. Dossier size: {len(investigation_dossier)} chars.")
    print(f"[Orchestrator] Investigation completed. Dossier size: {len(investigation_dossier)} chars.")
    dossier_preview = investigation_dossier[:250] + "..." if len(investigation_dossier) > 250 else investigation_dossier
    logger.info(redact_pii(f"[Orchestrator] Dossier preview:\n{dossier_preview}"))
    print(redact_pii(f"[Orchestrator] Dossier preview:\n{dossier_preview}"))
    await asyncio.sleep(5)

    # 5. Step 3: Conditional Approval Gate (Human-In-The-Loop)
    recommended_action = triage_data.get("recommended_action")
    approval_status = "not_required"
    HIGH_RISK_ACTIONS = {"freeze_account"}

    if recommended_action in HIGH_RISK_ACTIONS:
        # Check if we should bypass the gate (e.g. during verification run)
        bypass_gate = ctx.state.get("bypass_gate", False)
        if bypass_gate:
            logger.info(f"[Orchestrator] [Step 3/4] High-risk action '{recommended_action}' detected. Bypassing ApprovalGate for verification run.")
            print(f"[Orchestrator] [Step 3/4] High-risk action '{recommended_action}' detected. Bypassing ApprovalGate.")
            approval_status = "bypassed"
            # Perform state change automatically when bypassed during verification
            _update_account_status(account_id, "frozen")
        else:
            logger.info(f"[Orchestrator] [Step 3/4] High-risk action '{recommended_action}' detected. Pausing for ApprovalGate...")
            print(f"[Orchestrator] [Step 3/4] High-risk action '{recommended_action}' detected. Pausing for ApprovalGate...")
            
            # Set the required state variables for approval_gate parameter binding
            reasoning = triage_data.get("reasoning", flag.get("reason", "No reasoning provided"))
            ctx.state["action"] = recommended_action
            ctx.state["dossier"] = investigation_dossier
            ctx.state["reasoning"] = reasoning
            ctx.state["account_id"] = account_id
            ctx.state["flag_id"] = flag_id
            
            # Execute approval gate node
            approval_res = await ctx.run_node(approval_gate)
            
            # Extract decision. Since the response might be a dictionary on resume, handle both dict and string.
            if isinstance(approval_res, dict):
                decision = str(approval_res.get("result", approval_res)).strip().lower()
            else:
                decision = str(approval_res).strip().lower()

            logger.info(f"[Orchestrator] ApprovalGate decision parsed: '{decision}'")
            print(f"[Orchestrator] ApprovalGate decision parsed: '{decision}'")

            if decision == "approve":
                approval_status = "approved"
                msg_approved = f"[Orchestrator] Action APPROVED. Executing state change: freezing account {account_id}."
                logger.info(redact_pii(msg_approved))
                print(redact_pii(msg_approved))
                _update_account_status(account_id, "frozen")
            else:
                approval_status = "denied"
                msg_denied = f"[Orchestrator] Action DENIED. Aborting state change for account {account_id}."
                logger.warning(redact_pii(msg_denied))
                print(redact_pii(msg_denied))
    else:
        logger.info(f"[Orchestrator] [Step 3/4] Recommended action '{recommended_action}' is low-risk. Skipping ApprovalGate.")
        print(f"[Orchestrator] [Step 3/4] Recommended action '{recommended_action}' is low-risk. Skipping ApprovalGate.")
        approval_status = "not_required"

    # 6. Step 4: Conditionally Run ReportAgent (proceeds only on approve / low-risk)
    if approval_status == "denied":
        logger.warning("[Orchestrator] Pipeline aborted. Incident recommended action denied by human operator.")
        print("\n[Orchestrator] Pipeline aborted. Incident recommended action denied by human operator.")
        
        # Compile final denied output and log redacted decision trail
        final_output = {
            "status": "denied",
            "flag_id": flag_id,
            "account_id": account_id,
            "triage": triage_data,
            "approval_status": approval_status,
            "rca_report": None
        }
        _log_decision_trail(final_output)
        return final_output

    logger.info(f"[Orchestrator] [Step 4/4] Invoking ReportAgent to draft RCA report...")
    print(f"[Orchestrator] [Step 4/4] Invoking ReportAgent...")
    
    report_prompt = f"""
    Generate an RCA report for Flag ID: {flag_id}
    Triage Result: {triage_data}
    Investigation Dossier: {investigation_dossier}
    Approval Status: {approval_status}
    """
    rca_report = await ctx.run_node(report_agent, node_input=report_prompt)

    logger.info(f"[Orchestrator] Report generation completed.")
    print(f"[Orchestrator] Report generation completed.")

    # 7. Compile final response and log redacted decision trail
    final_output = {
        "status": "completed",
        "flag_id": flag_id,
        "account_id": account_id,
        "triage": triage_data,
        "approval_status": approval_status,
        "rca_report": rca_report
    }

    _log_decision_trail(final_output)
    return final_output

# Define the root OrchestratorAgent as an ADK Workflow
orchestrator_agent = Workflow(
    name="orchestrator_agent",
    edges=[("START", orchestrator_workflow)],
)


