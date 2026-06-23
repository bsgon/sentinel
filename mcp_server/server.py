"""Sentinel MCP Server implementation.

Implementation:
- Wires an MCP server using the FastMCP framework.
- Queries and parses CSV files from the local data directory.

Design:
- Exposes clean, read-only tools to fetch account details, transaction history, flags, and prior support/investigation cases.
- Follows FastMCP tool decoration patterns.

Behavior:
- Serves transaction, case, account, and flag information to connected MCP clients over stdio transport.
"""

import csv
import os
from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server for Sentinel
mcp_server = FastMCP("Sentinel")

# Define file paths to synthetic CSV files
DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.csv")
TRANSACTIONS_FILE = os.path.join(DATA_DIR, "transactions.csv")
FLAGS_FILE = os.path.join(DATA_DIR, "flags.csv")
CASES_FILE = os.path.join(DATA_DIR, "cases.csv")

def _read_csv(file_path: str) -> list[dict]:
    """Helper method to read a CSV file and return a list of dictionaries.

    If the file does not exist, an empty list is returned.
    """
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)

@mcp_server.tool()
async def get_account(account_id: str) -> dict:
    """Fetches details for a specific user account.

    Implementation:
    - Scans accounts.csv for a matching account_id.
    - Deserializes and cleans fields.

    Design:
    - Read-only data-querying tool.

    Behavior:
    - Returns account metadata dictionary or error dictionary if not found.
    """
    rows = _read_csv(ACCOUNTS_FILE)
    for row in rows:
        if row["account_id"] == account_id:
            return {
                "account_id": row["account_id"],
                "created_at": row["created_at"],
                "kyc_level": int(row["kyc_level"]) if row["kyc_level"] else None,
                "country": row["country"],
                "risk_score": float(row["risk_score"]) if row["risk_score"] else 0.0,
                "status": row["status"]
            }
    return {"error": f"Account {account_id} not found"}

@mcp_server.tool()
async def get_recent_transactions(account_id: str) -> list[dict]:
    """Fetches recent transaction history for a specific account.

    Implementation:
    - Filters transactions.csv by matching account_id.
    - Sorts records by timestamp in descending order (most recent first).

    Design:
    - Read-only transaction list retrieval.

    Behavior:
    - Returns list of matching transaction records.
    """
    rows = _read_csv(TRANSACTIONS_FILE)
    txs = []
    for row in rows:
        if row["account_id"] == account_id:
            txs.append({
                "tx_id": row["tx_id"],
                "account_id": row["account_id"],
                "timestamp": row["timestamp"],
                "type": row["type"],
                "amount": float(row["amount"]) if row["amount"] else 0.0,
                "currency": row["currency"],
                "counterparty_address": row["counterparty_address"],
                "channel": row["channel"],
                "ip_country": row["ip_country"],
                "device_id": row["device_id"]
            })
    # Sort by timestamp descending
    txs.sort(key=lambda x: x["timestamp"], reverse=True)
    return txs

@mcp_server.tool()
async def get_flags(account_id: str) -> list[dict]:
    """Fetches risk flags triggered for a specific account.

    Implementation:
    - Scans flags.csv matching account_id.
    - Sorts results by created_at descending.

    Design:
    - Read-only flags list retrieval.

    Behavior:
    - Returns list of triggered flags for the account.
    """
    rows = _read_csv(FLAGS_FILE)
    flags = []
    for row in rows:
        if row["account_id"] == account_id:
            flags.append({
                "flag_id": row["flag_id"],
                "account_id": row["account_id"],
                "tx_id": row["tx_id"] if row["tx_id"] else None,
                "rule_id": row["rule_id"],
                "severity": row["severity"],
                "created_at": row["created_at"],
                "reason": row["reason"]
            })
    # Sort by created_at descending
    flags.sort(key=lambda x: x["created_at"], reverse=True)
    return flags

@mcp_server.tool()
async def get_prior_cases(account_id: str) -> list[dict]:
    """Fetches historical support or investigation cases for a specific account.

    Implementation:
    - Reads cases.csv and filters by account_id.
    - Sorts matching rows by opened_at timestamp descending.

    Design:
    - Read-only historical context retrieval.

    Behavior:
    - Returns list of historical cases.
    """
    rows = _read_csv(CASES_FILE)
    cases = []
    for row in rows:
        if row["account_id"] == account_id:
            cases.append({
                "case_id": row["case_id"],
                "account_id": row["account_id"],
                "opened_at": row["opened_at"],
                "category": row["category"],
                "resolution": row["resolution"],
                "rca_summary": row["rca_summary"]
            })
    # Sort by opened_at descending
    cases.sort(key=lambda x: x["opened_at"], reverse=True)
    return cases

if __name__ == "__main__":
    mcp_server.run(transport="stdio")


