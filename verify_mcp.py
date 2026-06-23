#!/usr/bin/env python3
"""Verification Script for Sentinel MCP Server.

This script imports and executes the four MCP server tools:
- get_account
- get_recent_transactions
- get_flags
- get_prior_cases
against the synthetic data. It prints the outputs in formatted JSON.
"""

import asyncio
import json
import sys
from mcp_server.server import (
    get_account,
    get_recent_transactions,
    get_flags,
    get_prior_cases,
)

async def test_account(account_id: str):
    print(f"\n==================================================")
    print(f"Testing tools for Account ID: {account_id}")
    print(f"==================================================")

    # 1. Test get_account
    account_result = await get_account(account_id)
    print("\n--- [Tool] get_account ---")
    print(json.dumps(account_result, indent=2))

    # 2. Test get_recent_transactions
    tx_result = await get_recent_transactions(account_id)
    print(f"\n--- [Tool] get_recent_transactions ({len(tx_result)} transactions found) ---")
    # Show first 3 for readability if there are many
    show_txs = tx_result[:3]
    print(json.dumps(show_txs, indent=2))
    if len(tx_result) > 3:
        print(f"... and {len(tx_result) - 3} more transactions.")

    # 3. Test get_flags
    flags_result = await get_flags(account_id)
    print(f"\n--- [Tool] get_flags ({len(flags_result)} flags found) ---")
    print(json.dumps(flags_result, indent=2))

    # 4. Test get_prior_cases
    cases_result = await get_prior_cases(account_id)
    print(f"\n--- [Tool] get_prior_cases ({len(cases_result)} cases found) ---")
    print(json.dumps(cases_result, indent=2))

async def main():
    # Test valid account ACC-010 (Clustered with Structuring flag, cases)
    await test_account("ACC-010")

    # Test valid account ACC-020 (Clustered with Sanctioned match, IP mismatch)
    await test_account("ACC-020")

    # Test non-existent account ACC-999 (Checks error handling and empty states)
    await test_account("ACC-999")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Verification failed with error: {e}", file=sys.stderr)
        sys.exit(1)
