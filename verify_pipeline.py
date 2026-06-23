#!/usr/bin/env python3
"""Verification Script for Sentinel multi-agent pipeline.

This script executes the pipeline end-to-end using a sample flag ID,
bypassing the approval gate via session state configuration.
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# Load environmental variables
load_dotenv()

# Ensure API Key is configured
if not os.environ.get("GOOGLE_API_KEY"):
    print("Error: GOOGLE_API_KEY environment variable is not set.", file=sys.stderr)
    sys.exit(1)

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
import google.genai.types as types

# Import Sentinel agents
from sentinel.orchestrator import orchestrator_agent

async def main():
    print("=== Sentinel Multi-Agent Pipeline Verification ===")
    
    # Initialize the session service and runner
    session_service = InMemorySessionService()
    runner = Runner(
        app_name="sentinel",
        agent=orchestrator_agent,
        session_service=session_service,
    )

    # Create a session with bypass_gate=True in the state
    session = await session_service.create_session(
        app_name="sentinel",
        user_id="operator-1",
        state={"bypass_gate": True},
    )

    # Use FLG-019 (Structuring flag on ACC-010) as test input
    sample_flag = "FLG-019"
    print(f"Triggering pipeline for flag: {sample_flag}\n")

    # Run the workflow asynchronously
    user_message = types.Content(
        role="user", 
        parts=[types.Part.from_text(text=sample_flag)]
    )

    final_event = None
    async for event in runner.run_async(
        user_id=session.user_id,
        session_id=session.id,
        new_message=user_message,
    ):
        if event.is_final_response():
            final_event = event

    print("\n=================== Execution Finished ===================")
    if final_event and final_event.content and final_event.content.parts:
        print("\nFinal Pipeline Output:")
        print(final_event.content.parts[0].text)
    else:
        print("\nPipeline completed successfully. Check the logs above.")

if __name__ == "__main__":
    asyncio.run(main())
