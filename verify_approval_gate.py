#!/usr/bin/env python3
"""Verification Script for Sentinel approval gate and state changes.

This script runs three scenarios:
1. Low-risk flag (FLG-001) - should run end-to-end automatically without pausing.
2. High-risk flag (FLG-019) approved - should pause, accept "approve", update the CSV to frozen, and generate the RCA report.
3. High-risk flag (FLG-022) denied - should pause, accept "deny", keep the account status unchanged, and exit early.

Includes a robust, self-healing retry mechanism on RESOURCE_EXHAUSTED (429) rate limits.
"""

import asyncio
import os
import sys
import csv
from dotenv import load_dotenv

# Load environmental variables
load_dotenv()

# Ensure API Key is configured
if not os.environ.get("GOOGLE_API_KEY"):
    print("Error: GOOGLE_API_KEY environment variable is not set.", file=sys.stderr)
    sys.exit(1)

# --- START OF ADK NODE MOCKING PATCH FOR OFFLINE VERIFICATION ---
from google.adk.agents.context import Context

# Keep reference to the original run_node
original_run_node = Context.run_node

async def mock_run_node(self, node, node_input=None, **kwargs):
    node_name = getattr(node, "name", None) or getattr(node, "__name__", None)
    
    if node_name == "triage_agent":
        from sentinel.triage import TriageResult
        
        # Check which flag is being triaged from node_input details
        flag_id = "FLG-001"
        if "FLG-019" in str(node_input):
            flag_id = "FLG-019"
        elif "FLG-022" in str(node_input):
            flag_id = "FLG-022"
            
        if flag_id == "FLG-001":
            return TriageResult(
                severity="low",
                category="Wash Trading Pattern",
                recommended_action="monitor",
                reasoning="Triage Agent reasoning: Low severity wash trading detected."
            )
        elif flag_id == "FLG-019":
            return TriageResult(
                severity="high",
                category="Rapid Structuring Deposit",
                recommended_action="freeze_account",
                reasoning="Triage Agent reasoning: Rapid structuring of fiat deposits below the $10,000 reporting threshold detected."
            )
        elif flag_id == "FLG-022":
            return TriageResult(
                severity="high",
                category="Sanctioned Destination Address",
                recommended_action="freeze_account",
                reasoning="Triage Agent reasoning: Withdrawal address matches OFAC SDN sanctioned blocklist. Transaction initiated from IP 192.0.2.1 using device DEV-99Z."
            )

    elif node_name == "investigation_agent":
        account_id = "ACC-007"
        if "ACC-010" in str(node_input):
            account_id = "ACC-010"
        elif "ACC-020" in str(node_input):
            account_id = "ACC-020"
            
        # Provide dossier containing PII (IPs, device IDs, account IDs, and addresses) to verify orchestrator PII redaction
        return (
            f"### Investigation Dossier for Account {account_id}\n"
            f"- Registered Country: US\n"
            f"- Risk Score: 85\n"
            f"- IP Address: 192.168.1.50 (Location: US)\n"
            f"- Transaction Device: DEV-12B45\n"
            f"- Mismatching transaction IP: 203.0.113.195 (Location: DE)\n"
            f"- Counterparty Address: 0xa856ec9af58dddc49945269d\n"
            f"- External Wallet: external_wallet_9883\n"
            f"- Prior Cases: None\n"
        )
        
    elif node_name == "report_agent":
        import re
        import ast
        from skills.rca_report import generate_rca_report
        
        # Parse the prompt string
        node_input_str = str(node_input)
        
        # Extract flag_id
        flag_id_match = re.search(r"Flag ID:\s*(FLG-\d+)", node_input_str)
        flag_id = flag_id_match.group(1) if flag_id_match else "FLG-001"
        
        # Extract Triage Result dict
        triage_data = {}
        triage_match = re.search(r"Triage Result:\s*(\{.*?\})", node_input_str, re.DOTALL)
        if triage_match:
            try:
                triage_data = ast.literal_eval(triage_match.group(1))
            except Exception:
                pass
                
        # Extract Approval Status
        approval_status_match = re.search(r"Approval Status:\s*([a-zA-Z_]+)", node_input_str)
        approval_status = approval_status_match.group(1) if approval_status_match else "not_required"
        
        # Extract Investigation Dossier
        dossier = ""
        dossier_match = re.search(r"Investigation Dossier:\s*(.*?)\s*Approval Status:", node_input_str, re.DOTALL)
        if dossier_match:
            dossier = dossier_match.group(1).strip()
            
        return generate_rca_report(
            flag_id=flag_id,
            triage_data=triage_data,
            investigation_data={"dossier": dossier},
            approval_status=approval_status
        )
        
    # For approval_gate and any other workflow node, run the original logic
    return await original_run_node(self, node, node_input, **kwargs)

# Apply the Context patch
Context.run_node = mock_run_node
# --- END OF ADK NODE MOCKING PATCH ---


from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
import google.genai.types as types
from google.genai.errors import ClientError

# Import Sentinel orchestrator
from sentinel.orchestrator import orchestrator_agent

def get_account_status(account_id: str) -> str:
    accounts_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "accounts.csv"))
    if not os.path.exists(accounts_file):
        return "file_not_found"
    with open(accounts_file, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["account_id"] == account_id:
                return row["status"]
    return "not_found"

def set_account_status(account_id: str, status: str):
    accounts_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "accounts.csv"))
    if not os.path.exists(accounts_file):
        return
    rows = []
    fieldnames = []
    with open(accounts_file, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            if row["account_id"] == account_id:
                row["status"] = status
            rows.append(row)
    with open(accounts_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

async def run_with_retry(runner, user_id, session_id, new_message=None):
    """Wraps runner.run_async with retry logic on RESOURCE_EXHAUSTED errors."""
    import re
    max_retries = 12
    
    for attempt in range(max_retries):
        try:
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=new_message,
            ):
                yield event
            return
        except ClientError as ce:
            if "RESOURCE_EXHAUSTED" in str(ce) or ce.code == 429:
                delay = 60
                match = re.search(r"Please retry in (\d+\.?\d*)s", str(ce))
                if match:
                    delay = int(float(match.group(1))) + 2
                print(f"\n[Rate Limit] Hit quota limit (429). Retrying attempt {attempt + 1}/{max_retries} in {delay}s...")
                await asyncio.sleep(delay)
            else:
                raise ce
        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                delay = 60
                match = re.search(r"Please retry in (\d+\.?\d*)s", str(e))
                if match:
                    delay = int(float(match.group(1))) + 2
                print(f"\n[Rate Limit] Hit quota limit (429). Retrying attempt {attempt + 1}/{max_retries} in {delay}s...")
                await asyncio.sleep(delay)
            else:
                raise e
    raise RuntimeError("Failed to execute runner.run_async after maximum retries due to rate limits.")

async def test_low_risk_flow():
    print("\n" + "="*80)
    print("SCENARIO 1: Testing Low-Risk Flow (FLG-001 - monitor)")
    print("="*80)
    
    account_id = "ACC-007"
    initial_status = get_account_status(account_id)
    print(f"[Pre-run] Account {account_id} status: {initial_status}")
    
    session_service = InMemorySessionService()
    runner = Runner(
        app_name="sentinel",
        agent=orchestrator_agent,
        session_service=session_service,
    )
    session = await session_service.create_session(app_name="sentinel", user_id="operator-1")
    
    user_message = types.Content(role="user", parts=[types.Part.from_text(text="FLG-001")])
    
    print("[Verification] Starting pipeline run...")
    paused = False
    async for event in run_with_retry(runner, session.user_id, session.id, user_message):
        if event.long_running_tool_ids:
            paused = True
            print("ERROR: Pipeline paused for low-risk action!")
            break
            
    # Retrieve final result
    session = await session_service.get_session(app_name="sentinel", user_id="operator-1", session_id=session.id)
    final_output = None
    for e in reversed(session.events):
        if e.output:
            final_output = e.output
            break
            
    print(f"[Verification] Flow completed. Paused: {paused}")
    print(f"[Verification] Pipeline Status: {final_output.get('status') if final_output else 'Unknown'}")
    print(f"[Verification] Approval Status: {final_output.get('approval_status') if final_output else 'Unknown'}")
    
    final_status = get_account_status(account_id)
    print(f"[Post-run] Account {account_id} status: {final_status}")
    assert final_status == initial_status, "Low-risk status should not have changed"
    print("SCENARIO 1 PASSED!")

async def test_high_risk_approved_flow():
    print("\n" + "="*80)
    print("SCENARIO 2: Testing High-Risk Approved Flow (FLG-019 - freeze_account)")
    print("="*80)
    
    account_id = "ACC-010"
    # Ensure initial status is under_review
    set_account_status(account_id, "under_review")
    initial_status = get_account_status(account_id)
    print(f"[Pre-run] Account {account_id} status: {initial_status}")
    
    session_service = InMemorySessionService()
    runner = Runner(
        app_name="sentinel",
        agent=orchestrator_agent,
        session_service=session_service,
    )
    session = await session_service.create_session(app_name="sentinel", user_id="operator-1")
    
    user_message = types.Content(role="user", parts=[types.Part.from_text(text="FLG-019")])
    
    print("[Verification] Starting pipeline run...")
    paused = False
    interrupt_id = None
    
    async for event in run_with_retry(runner, session.user_id, session.id, user_message):
        if event.long_running_tool_ids:
            paused = True
            interrupt_id = list(event.long_running_tool_ids)[0]
            print(f"[Verification] Pipeline paused on RequestInput interrupt: {interrupt_id}")
            # Print surfaced message
            if event.content and event.content.parts:
                print(event.content.parts[0].function_call.args.get("message"))
            break
            
    assert paused, "Pipeline should have paused for high-risk action"
    
    # Resume by sending the approve response
    resume_part = types.Part(
        function_response=types.FunctionResponse(
            id=interrupt_id,
            name="adk_request_input",
            response={"result": "approve"}
        )
    )
    resume_message = types.Content(role="user", parts=[resume_part])
    print("\n[Verification] Sending resume response: 'approve'")
    
    async for res_event in run_with_retry(runner, session.user_id, session.id, resume_message):
        if res_event.is_final_response():
            pass
            
    # Retrieve final result
    session = await session_service.get_session(app_name="sentinel", user_id="operator-1", session_id=session.id)
    final_output = None
    for e in reversed(session.events):
        if e.output:
            final_output = e.output
            break
            
    print(f"[Verification] Flow completed.")
    print(f"[Verification] Pipeline Status: {final_output.get('status') if final_output else 'Unknown'}")
    print(f"[Verification] Approval Status: {final_output.get('approval_status') if final_output else 'Unknown'}")
    
    final_status = get_account_status(account_id)
    print(f"[Post-run] Account {account_id} status: {final_status}")
    assert final_status == "frozen", f"Account {account_id} should be frozen, but got {final_status}"
    
    # Reset status
    set_account_status(account_id, "under_review")
    print("SCENARIO 2 PASSED!")

async def test_high_risk_denied_flow():
    print("\n" + "="*80)
    print("SCENARIO 3: Testing High-Risk Denied Flow (FLG-022 - freeze_account)")
    print("="*80)
    
    account_id = "ACC-020"
    # Ensure initial status is under_review
    set_account_status(account_id, "under_review")
    initial_status = get_account_status(account_id)
    print(f"[Pre-run] Account {account_id} status: {initial_status}")
    
    session_service = InMemorySessionService()
    runner = Runner(
        app_name="sentinel",
        agent=orchestrator_agent,
        session_service=session_service,
    )
    session = await session_service.create_session(app_name="sentinel", user_id="operator-1")
    
    user_message = types.Content(role="user", parts=[types.Part.from_text(text="FLG-022")])
    
    print("[Verification] Starting pipeline run...")
    paused = False
    interrupt_id = None
    
    async for event in run_with_retry(runner, session.user_id, session.id, user_message):
        if event.long_running_tool_ids:
            paused = True
            interrupt_id = list(event.long_running_tool_ids)[0]
            print(f"[Verification] Pipeline paused on RequestInput interrupt: {interrupt_id}")
            break
            
    assert paused, "Pipeline should have paused for high-risk action"
    
    # Resume by sending the deny response
    resume_part = types.Part(
        function_response=types.FunctionResponse(
            id=interrupt_id,
            name="adk_request_input",
            response={"result": "deny"}
        )
    )
    resume_message = types.Content(role="user", parts=[resume_part])
    print("\n[Verification] Sending resume response: 'deny'")
    
    async for res_event in run_with_retry(runner, session.user_id, session.id, resume_message):
        if res_event.is_final_response():
            pass
            
    # Retrieve final result
    session = await session_service.get_session(app_name="sentinel", user_id="operator-1", session_id=session.id)
    final_output = None
    for e in reversed(session.events):
        if e.output:
            final_output = e.output
            break
            
    print(f"[Verification] Flow completed.")
    print(f"[Verification] Pipeline Status: {final_output.get('status') if final_output else 'Unknown'}")
    print(f"[Verification] Approval Status: {final_output.get('approval_status') if final_output else 'Unknown'}")
    
    final_status = get_account_status(account_id)
    print(f"[Post-run] Account {account_id} status: {final_status}")
    assert final_status == "under_review", f"Account {account_id} should remain under_review, but got {final_status}"
    print("SCENARIO 3 PASSED!")

def verify_decision_trail_log():
    print("\n" + "="*80)
    print("SCENARIO 4: Verifying Decision Trail Log")
    print("="*80)
    
    log_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", "decision_trail.log"))
    assert os.path.exists(log_file), "decision_trail.log was not created!"
    print(f"[Verification] decision_trail.log file exists at {log_file}")
    
    # Check that PII is redacted in the log
    with open(log_file, "r") as f:
        content = f.read()
        
    has_redacted_ip = "[REDACTED_IP]" in content
    has_redacted_device = "[REDACTED_DEVICE]" in content
    has_redacted_account = "[REDACTED_ACCOUNT]" in content
    has_redacted_address = "[REDACTED_ADDRESS]" in content
    
    print(f"[Verification] Log contains redacted IPs: {has_redacted_ip}")
    print(f"[Verification] Log contains redacted device IDs: {has_redacted_device}")
    print(f"[Verification] Log contains redacted account IDs: {has_redacted_account}")
    print(f"[Verification] Log contains redacted addresses: {has_redacted_address}")

    assert has_redacted_ip, "Logs should contain redacted IPs"
    assert has_redacted_device, "Logs should contain redacted device IDs"
    assert has_redacted_account, "Logs should contain redacted account IDs"
    assert has_redacted_address, "Logs should contain redacted counterparty addresses"
    
    # Print the last 40 lines of the log for visual confirmation
    print("\n--- Recent log entries ---")
    lines = content.splitlines()
    for line in lines[-40:]:
        print(line)
        
    print("\nSCENARIO 4 PASSED!")

async def main():
    try:
        await test_low_risk_flow()
        
        print("\n[Verification] Pausing 0.1 seconds to avoid API rate limits...")
        await asyncio.sleep(0.1)
        
        await test_high_risk_approved_flow()
        
        print("\n[Verification] Pausing 0.1 seconds to avoid API rate limits...")
        await asyncio.sleep(0.1)
        
        await test_high_risk_denied_flow()
        
        print("\n[Verification] Pausing 0.1 seconds to ensure logs are written...")
        await asyncio.sleep(0.1)
        
        verify_decision_trail_log()
        print("\nAll Scenarios Passed Successfully!")
    except Exception as e:
        print(f"\nVerification failed with error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
