#!/usr/bin/env python3
"""Sentinel Entrypoint Runner CLI.

Implementation:
- Loads the local environment configuration from .env using python-dotenv.
- Verifies necessary API key configurations.
- Sanity checks component imports.
- Performs command-line argument parsing and input validation.
- Orchestrates and executes the ADK multi-agent pipeline interactively, handling Human-in-the-Loop prompts from stdout/stdin.

Design Rationale:
- Decouples pipeline invocation from tests.
- Implements two layers of validation: CLI-level format and database checks, and workflow-level node validation.
- Self-contained CLI loop handles RequestInput events interactively, allowing operators to approve or deny high-risk actions dynamically.

Runtime Behavior:
- Invoked with no arguments: checks environment and prints "Sentinel up".
- Invoked with flag ID argument (e.g. `python run.py FLG-019`): validates format and existence, triggers pipeline, prompts for approval if required, and prints the resulting Incident RCA Report.
- Exits with code 1 and writes errors to stderr on validation failures or configuration issues.
"""

import os
import sys
import re
import csv
import asyncio
from dotenv import load_dotenv

def _flag_exists(flag_id: str) -> bool:
    """Checks the synthetic CSV database to verify if a flag ID exists.

    Implementation:
    - Resolves data directory path.
    - Scans flags.csv matching the input flag_id.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    flags_file = os.path.abspath(os.path.join(current_dir, "data", "flags.csv"))
    if not os.path.exists(flags_file):
        return False
    with open(flags_file, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["flag_id"] == flag_id:
                return True
    return False

async def run_pipeline(flag_id: str):
    """Executes the ADK OrchestratorAgent pipeline interactively for the given flag ID.

    Implementation:
    - Wires up the ADK Runner with InMemorySessionService.
    - Listens to run_async event stream.
    - Intercepts RequestInput pause events, prompting the operator on stdout and submitting response via input().
    - Retries automatically on 429 Resource Exhausted API quota limits.

    Behavior:
    - Interactive loop that executes the multi-agent pipeline and outputs the final redacted RCA report.
    """
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    import google.genai.types as types
    from google.genai.errors import ClientError
    from sentinel.orchestrator import orchestrator_agent

    session_service = InMemorySessionService()
    runner = Runner(
        app_name="sentinel",
        agent=orchestrator_agent,
        session_service=session_service,
    )
    session = await session_service.create_session(
        app_name="sentinel",
        user_id="operator-1",
    )

    user_message = types.Content(
        role="user",
        parts=[types.Part.from_text(text=flag_id)]
    )

    current_message = user_message
    max_retries = 10

    while True:
        paused = False
        interrupt_id = None
        attempt = 0

        # Run stream loop with retry on 429
        while attempt < max_retries:
            try:
                async for event in runner.run_async(
                    user_id=session.user_id,
                    session_id=session.id,
                    new_message=current_message,
                ):
                    if event.long_running_tool_ids:
                        paused = True
                        interrupt_id = list(event.long_running_tool_ids)[0]
                        if event.content and event.content.parts:
                            msg_text = event.content.parts[0].function_call.args.get("message", "Approve? ")
                            print(msg_text, end="")
                        break
                # Successful run, break out of retry loop
                break
            except (ClientError, Exception) as ce:
                err_msg = str(ce)
                # Check for 429 / RESOURCE_EXHAUSTED or 503 / UNAVAILABLE / transient server errors
                is_quota = "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg
                is_transient = "UNAVAILABLE" in err_msg or "503" in err_msg or "INTERNAL" in err_msg or "500" in err_msg
                
                if is_quota or is_transient:
                    attempt += 1
                    if is_quota:
                        delay = 60
                        # Check for recommended retry delay in error string
                        match = re.search(r"Please retry in (\d+\.?\d*)s", err_msg)
                        if match:
                            delay = int(float(match.group(1))) + 2
                        print(f"\n[Rate Limit] Gemini 429 Resource Exhausted. Retrying attempt {attempt}/{max_retries} in {delay}s...", file=sys.stderr)
                    else:
                        delay = 5 * attempt # Incremental backoff: 5s, 10s, 15s...
                        print(f"\n[API Error] Gemini 503/500 Service Unavailable. Retrying attempt {attempt}/{max_retries} in {delay}s...", file=sys.stderr)
                    await asyncio.sleep(delay)
                else:
                    raise ce
        else:
            print("\nError: Execution failed after maximum quota retries.", file=sys.stderr)
            sys.exit(1)

        if not paused:
            # Pipeline finished successfully
            break

        # Read input from standard input for the approval gate prompt
        try:
            user_input = sys.stdin.readline().strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExecution cancelled by operator.")
            sys.exit(1)

        resume_part = types.Part(
            function_response=types.FunctionResponse(
                id=interrupt_id,
                name="adk_request_input",
                response={"result": user_input}
            )
        )
        current_message = types.Content(role="user", parts=[resume_part])

    # Fetch and display the final incident report from session output
    session = await session_service.get_session(
        app_name="sentinel",
        user_id="operator-1",
        session_id=session.id
    )
    final_output = None
    for e in reversed(session.events):
        if e.output:
            final_output = e.output
            break

    if final_output:
        rca_report = final_output.get("rca_report")
        if rca_report:
            print("\n" + "="*80)
            print("FINAL ROOT CAUSE ANALYSIS (RCA) REPORT")
            print("="*80)
            print(rca_report)
            print("="*80 + "\n")
        else:
            print(f"\n[System] Pipeline completed with status: {final_output.get('status')}")
            print(f"[System] Approval Outcome: {final_output.get('approval_status')}\n")

def main():
    # 1. Load environment variables from local .env file
    load_dotenv()

    # 2. Check for required Google Gemini API Configuration
    api_key = os.environ.get("GOOGLE_API_KEY")
    model_name = os.environ.get("GEMINI_MODEL")

    if not api_key:
        print("Error: GOOGLE_API_KEY environment variable is not set.", file=sys.stderr)
        print("Please create a .env file based on .env.example and add your API key.", file=sys.stderr)
        sys.exit(1)

    if not model_name:
        print("Warning: GEMINI_MODEL not specified in environment. Defaulting to 'gemini-2.5-flash'.", file=sys.stderr)
        model_name = "gemini-2.5-flash"
        os.environ["GEMINI_MODEL"] = model_name

    # 3. Import Sentinel agents and workflows to verify import sanity
    try:
        import sentinel
        from sentinel import orchestrator_agent
        from mcp_server.server import mcp_server
        from skills import generate_rca_report
        
        # Verify and retrieve agent names
        agent_names = [triage_agent.name for triage_agent in [sentinel.triage_agent, sentinel.investigation_agent, sentinel.report_agent]]
        
    except Exception as e:
        print(f"Error initializing Sentinel components: {e}", file=sys.stderr)
        sys.exit(1)

    # 4. Check if a Command Line Argument is provided
    if len(sys.argv) > 1:
        flag_id = sys.argv[1].strip()
        
        # Input Validation: Format check
        if not re.match(r"^FLG-\d{3}$", flag_id):
            print(f"Error: Invalid Flag ID format '{flag_id}'. Format must be 'FLG-XXX' where XXX is a 3-digit number.", file=sys.stderr)
            sys.exit(1)
            
        # Input Validation: Database existence check
        if not _flag_exists(flag_id):
            print(f"Error: Flag ID '{flag_id}' does not exist in the database.", file=sys.stderr)
            sys.exit(1)
            
        # Execute the pipeline
        asyncio.run(run_pipeline(flag_id))
    else:
        # Default behavior: Print startup confirmation
        print("Sentinel up")

if __name__ == "__main__":
    main()
