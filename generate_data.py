"""Synthetic Data Generator for Sentinel.

This script generates a reproducible, internally consistent Trust & Safety dataset
representing accounts, transactions, rules, flags, and prior cases for a crypto exchange.
It outputs CSV files into the /data directory following the schemas in SPEC.md.

Design & Consistency Rules:
1. Chronological order: Account Creation (2024-2025) -> Prior Cases (2025-early 2026)
   -> Transactions (April-June 2026) -> Risk Flags (triggered on transactions or accounts in 2026).
2. Clustering: A few designated risky accounts have high risk_scores, receive multiple high-severity
   flags, and are associated with suspicious transaction patterns and prior cases.
3. Reference Integrity: Every flag and case points to a valid account_id. Transaction flags point to a
   valid tx_id belonging to that account.
4. Reproducibility: A fixed random seed (42) ensures identical output on every run.
"""

import os
import random
import csv
from datetime import datetime, timedelta

# Set random seed for reproducibility
random.seed(42)

# Define file paths
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.csv")
TRANSACTIONS_FILE = os.path.join(DATA_DIR, "transactions.csv")
FLAGS_FILE = os.path.join(DATA_DIR, "flags.csv")
CASES_FILE = os.path.join(DATA_DIR, "cases.csv")
RULES_FILE = os.path.join(DATA_DIR, "rules.csv")

# Constants for Generation
NUM_ACCOUNTS = 40
NUM_TRANSACTIONS = 300
NUM_FLAGS = 25
NUM_CASES = 15
NUM_RULES = 8

# Helper to generate random isoformat timestamps in a range
def random_date(start_dt: datetime, end_dt: datetime) -> str:
    delta = end_dt - start_dt
    random_seconds = random.randint(0, int(delta.total_seconds()))
    dt = start_dt + timedelta(seconds=random_seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def generate_dataset():
    print("Generating synthetic crypto-exchange Trust & Safety dataset...")

    # ==========================================
    # 1. Generate Rules
    # ==========================================
    # We define exactly 8 distinct rules following common Trust & Safety scenarios.
    rules = [
        {
            "rule_id": "RUL-001",
            "name": "Rapid Structuring Deposit",
            "description": "Multiple cash-in/deposits just below standard $10,000 reporting thresholds within 24 hours.",
            "severity_default": "high",
            "recommended_action": "freeze_account"
        },
        {
            "rule_id": "RUL-002",
            "name": "IP Country Mismatch",
            "description": "User transaction IP country differs from their registered KYC country.",
            "severity_default": "med",
            "recommended_action": "request_kyc"
        },
        {
            "rule_id": "RUL-003",
            "name": "Sanctioned Destination Address",
            "description": "Withdrawal counterparty blockchain address is associated with high-risk/sanctioned entities.",
            "severity_default": "high",
            "recommended_action": "freeze_account"
        },
        {
            "rule_id": "RUL-004",
            "name": "High Value Transaction Spikes",
            "description": "A single transaction amount significantly exceeds the historic average for the account.",
            "severity_default": "med",
            "recommended_action": "escalate"
        },
        {
            "rule_id": "RUL-005",
            "name": "Wash Trading Pattern",
            "description": "High-frequency self-matching trade behavior to artificially inflate token volumes.",
            "severity_default": "low",
            "recommended_action": "monitor"
        },
        {
            "rule_id": "RUL-006",
            "name": "Velocity Trade Spike",
            "description": "Sub-second execution of multiple trade transactions suggestive of unauthorized API exploitation.",
            "severity_default": "low",
            "recommended_action": "monitor"
        },
        {
            "rule_id": "RUL-007",
            "name": "Dormant Account Awakening",
            "description": "High-value trade or withdrawal on an account inactive for more than 180 days.",
            "severity_default": "med",
            "recommended_action": "request_kyc"
        },
        {
            "rule_id": "RUL-008",
            "name": "Unusual Micro-Withdrawal Peeling",
            "description": "Repetitive minor withdrawals to nested external addresses within a short timeframe.",
            "severity_default": "med",
            "recommended_action": "escalate"
        }
    ]

    # Write rules.csv
    with open(RULES_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["rule_id", "name", "description", "severity_default", "recommended_action"])
        writer.writeheader()
        writer.writerows(rules)

    # ==========================================
    # 2. Generate Accounts
    # ==========================================
    # Designate 4 risky accounts to cluster high risk scores and severe flags on.
    risky_accounts_indices = {10, 20, 30, 38}  # e.g., ACC-010, ACC-020, ACC-030, ACC-038
    countries = ["US", "GB", "DE", "CA", "BR", "JP", "AU", "SG", "FR", "NL"]
    kyc_levels = [0, 1, 2]

    accounts = []
    account_ids = []
    
    start_account_date = datetime(2024, 1, 1)
    end_account_date = datetime(2025, 6, 30)

    for i in range(1, NUM_ACCOUNTS + 1):
        acc_id = f"ACC-{i:03d}"
        account_ids.append(acc_id)
        
        is_risky = i in risky_accounts_indices
        created_at = random_date(start_account_date, end_account_date)
        
        # Risky accounts have poor KYC, high risk score, and status likely under review or frozen.
        if is_risky:
            kyc_level = random.choice([0, 1])
            country = random.choice(countries)
            risk_score = round(random.uniform(0.75, 0.99), 2)
            status = random.choice(["under_review", "frozen", "active"])
        else:
            kyc_level = random.choices([1, 2], weights=[40, 60])[0]
            country = random.choice(countries)
            risk_score = round(random.uniform(0.01, 0.30), 2)
            status = random.choices(["active", "under_review"], weights=[95, 5])[0]

        accounts.append({
            "account_id": acc_id,
            "created_at": created_at,
            "kyc_level": kyc_level,
            "country": country,
            "risk_score": risk_score,
            "status": status
        })

    # Write accounts.csv
    with open(ACCOUNTS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["account_id", "created_at", "kyc_level", "country", "risk_score", "status"])
        writer.writeheader()
        writer.writerows(accounts)

    # ==========================================
    # 3. Generate Transactions
    # ==========================================
    # We will generate exactly 300 transactions from April 1, 2026 to June 20, 2026.
    start_tx_date = datetime(2026, 4, 1)
    end_tx_date = datetime(2026, 6, 20)

    transactions = []
    tx_ids = []
    
    # Track transactions by account for easy reference later
    txs_by_account = {acc_id: [] for acc_id in account_ids}

    # High-risk accounts will have specific transaction sequences
    # Standard accounts will get standard transaction streams
    currs = ["BTC", "ETH", "USDT", "USD", "EUR"]
    channels = ["web", "mobile", "api"]

    # Pre-populate specific suspicious transactions for risky accounts to enable rule matching:
    # 1. ACC-010: Structuring pattern (Depositing multiple amounts just below $10,000)
    # 2. ACC-020: Sanctioned destination address and high-risk country IP mismatch
    # 3. ACC-030: Awakening of a dormant account + huge volume spikes
    # 4. ACC-038: Micro-withdrawal peeling to random external addresses
    
    suspicious_txs = []
    
    # ACC-010 Structuring
    t_acc_10 = datetime(2026, 5, 12, 10, 0, 0)
    for k in range(5):
        t_acc_10 += timedelta(minutes=random.randint(15, 60))
        suspicious_txs.append({
            "account_id": "ACC-010",
            "timestamp": t_acc_10.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type": "deposit",
            "amount": round(random.uniform(9500, 9950), 2),
            "currency": "USD",
            "counterparty_address": f"bank_wire_ref_{random.randint(100,999)}",
            "channel": "web",
            "ip_country": "US",
            "device_id": "DEV-10A"
        })

    # ACC-020 IP Mismatch and Sanctions
    suspicious_txs.append({
        "account_id": "ACC-020",
        "timestamp": "2026-06-15T14:22:11Z",
        "type": "withdrawal",
        "amount": 2.5,
        "currency": "BTC",
        "counterparty_address": "1KP_SANCTIONED_ADDRESS_BTC_0982",
        "channel": "api",
        "ip_country": "KP",  # Sanctioned IP Country mismatch
        "device_id": "DEV-20B"
    })
    
    # ACC-030 Dormant account spike
    suspicious_txs.append({
        "account_id": "ACC-030",
        "timestamp": "2026-04-20T08:15:30Z",
        "type": "withdrawal",
        "amount": 150000.0,
        "currency": "USDT",
        "counterparty_address": "0x534a9f...b2e3",
        "channel": "mobile",
        "ip_country": "GB",
        "device_id": "DEV-30C"
    })

    # ACC-038 Peeling chain
    t_acc_38 = datetime(2026, 6, 18, 20, 0, 0)
    for k in range(6):
        t_acc_38 += timedelta(minutes=random.randint(2, 10))
        suspicious_txs.append({
            "account_id": "ACC-038",
            "timestamp": t_acc_38.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "type": "withdrawal",
            "amount": round(random.uniform(5, 50), 2),
            "currency": "USDT",
            "counterparty_address": f"0xpeel_{random.randint(10000, 99999)}_addr",
            "channel": "api",
            "ip_country": "BR",
            "device_id": "DEV-38D"
        })

    # Insert suspicious transactions first, then fill out the rest up to 300
    tx_counter = 1
    for stx in suspicious_txs:
        tx_id = f"TX-{tx_counter:04d}"
        tx_ids.append(tx_id)
        stx_full = {"tx_id": tx_id, **stx}
        transactions.append(stx_full)
        txs_by_account[stx["account_id"]].append(stx_full)
        tx_counter += 1

    # Distribute the remaining transactions among all accounts
    remaining_count = NUM_TRANSACTIONS - len(transactions)
    for _ in range(remaining_count):
        acc_id = random.choice(account_ids)
        # Select base account info to maintain consistency
        acc_info = next(a for a in accounts if a["account_id"] == acc_id)
        
        tx_type = random.choices(["deposit", "withdrawal", "trade"], weights=[30, 30, 40])[0]
        amount = round(random.uniform(10.0, 5000.0), 2)
        if tx_type == "trade":
            amount = round(random.uniform(50.0, 15000.0), 2)
            
        currency = random.choice(currs)
        
        # Address generation
        if tx_type == "trade":
            counterparty = "internal_exchange"
        elif tx_type == "deposit":
            counterparty = f"external_wallet_{random.randint(1000,9999)}"
        else:
            counterparty = f"0x{random.randbytes(12).hex()}"
            
        channel = random.choice(channels)
        
        # IP country matches account country 95% of the time, except for occasional travel or proxy
        ip_country = acc_info["country"]
        if random.random() < 0.05:
            ip_country = random.choice([c for c in countries if c != acc_info["country"]])
            
        device_id = f"DEV-{acc_id[-3:]}{random.choice(['A', 'B'])}"
        timestamp = random_date(start_tx_date, end_tx_date)

        tx_id = f"TX-{tx_counter:04d}"
        tx_ids.append(tx_id)
        
        tx_record = {
            "tx_id": tx_id,
            "account_id": acc_id,
            "timestamp": timestamp,
            "type": tx_type,
            "amount": amount,
            "currency": currency,
            "counterparty_address": counterparty,
            "channel": channel,
            "ip_country": ip_country,
            "device_id": device_id
        }
        transactions.append(tx_record)
        txs_by_account[acc_id].append(tx_record)
        tx_counter += 1

    # Sort transactions chronologically to keep file clean and logical
    transactions.sort(key=lambda x: x["timestamp"])
    
    # Rewrite tx_id to ensure order
    for idx, tx in enumerate(transactions):
        tx["tx_id"] = f"TX-{(idx + 1):04d}"

    # Re-map our cached txs_by_account with correct sorted tx_ids
    txs_by_account = {acc_id: [] for acc_id in account_ids}
    for tx in transactions:
        txs_by_account[tx["account_id"]].append(tx)

    # Write transactions.csv
    with open(TRANSACTIONS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "tx_id", "account_id", "timestamp", "type", "amount", "currency",
            "counterparty_address", "channel", "ip_country", "device_id"
        ])
        writer.writeheader()
        writer.writerows(transactions)

    # ==========================================
    # 4. Generate Prior Cases
    # ==========================================
    # We generate exactly 15 prior cases.
    # To represent realistic scenarios, prior cases should exist for some of the flagged accounts
    # as well as general accounts. Let's make sure the 4 risky accounts have prior history.
    case_accounts = ["ACC-010", "ACC-020", "ACC-030", "ACC-038", "ACC-010"] # risky accounts history
    # Add other random accounts to complete the 15 cases
    while len(case_accounts) < NUM_CASES:
        rand_acc = random.choice(account_ids)
        case_accounts.append(rand_acc)

    categories = ["Structuring", "IP_Mismatch", "Account_Takeover", "Sanction_Match", "Suspicious_Activity"]
    resolutions = ["cleared", "terminated", "monitored"]
    
    cases = []
    start_case_date = datetime(2025, 7, 1)
    end_case_date = datetime(2026, 3, 31)

    for i in range(1, NUM_CASES + 1):
        case_id = f"CAS-{i:03d}"
        acc_id = case_accounts[i-1]
        opened_at = random_date(start_case_date, end_case_date)
        category = random.choice(categories)
        resolution = random.choice(resolutions)
        
        # Write specific summaries for a premium feel
        rca_summaries = {
            "Structuring": "Investigation showed deposit velocity spikes just below local regulatory declaration limit. Repetitive transfers cleared after manual user tax verification.",
            "IP_Mismatch": "Session IP shifted to VPN endpoint during travel. Account verified via SMS OTP challenge and security team clearance.",
            "Account_Takeover": "Sudden device shift followed by withdrawal attempt. Session terminated, password reset required, and trade restriction lifted after KYC selfie verify.",
            "Sanction_Match": "User name or wallet address flagged on OFAC low-confidence keyword match. Confirmed false positive; account status restored.",
            "Suspicious_Activity": "Automated alert triggered on repetitive high volume trades. Reviewed trade execution logs, concluded standard API usage, status kept active."
        }
        rca_summary = rca_summaries[category]

        cases.append({
            "case_id": case_id,
            "account_id": acc_id,
            "opened_at": opened_at,
            "category": category,
            "resolution": resolution,
            "rca_summary": rca_summary
        })

    # Sort cases chronologically
    cases.sort(key=lambda x: x["opened_at"])
    
    # Re-key case_id to maintain order
    for idx, case in enumerate(cases):
        case["case_id"] = f"CAS-{(idx + 1):03d}"

    # Write cases.csv
    with open(CASES_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["case_id", "account_id", "opened_at", "category", "resolution", "rca_summary"])
        writer.writeheader()
        writer.writerows(cases)

    # ==========================================
    # 5. Generate Flags
    # ==========================================
    # We must generate exactly 25 flags.
    # Flags must reference real tx_id/account_id.
    # High-severity flags must cluster on the risky accounts.
    # Low/Med flags can be scattered.
    flags = []
    
    # 1. First, create specific high-severity flags clustering on the risky accounts
    # ACC-010: RUL-001 (Structuring)
    acc10_txs = txs_by_account["ACC-010"]
    if acc10_txs:
        # Reference the last transaction in the structuring sequence
        ref_tx = acc10_txs[-1]
        flags.append({
            "account_id": "ACC-010",
            "tx_id": ref_tx["tx_id"],
            "rule_id": "RUL-001",
            "severity": "high",
            "created_at": ref_tx["timestamp"],
            "reason": "Triggered on multiple fiat deposits of $9k+ within a 6-hour window."
        })
        
    # ACC-020: RUL-003 (Sanctioned destination address) and RUL-002 (IP country mismatch)
    acc20_txs = [t for t in txs_by_account["ACC-020"] if t["ip_country"] == "KP"]
    if acc20_txs:
        ref_tx = acc20_txs[0]
        flags.append({
            "account_id": "ACC-020",
            "tx_id": ref_tx["tx_id"],
            "rule_id": "RUL-003",
            "severity": "high",
            "created_at": ref_tx["timestamp"],
            "reason": "Withdrawal address matched OFAC SDN sanctioned blocklist."
        })
        flags.append({
            "account_id": "ACC-020",
            "tx_id": ref_tx["tx_id"],
            "rule_id": "RUL-002",
            "severity": "med",
            "created_at": ref_tx["timestamp"],
            "reason": "Login session and transaction initiated from North Korea (KP), mismatching US KYC."
        })

    # ACC-030: RUL-007 (Dormant account awakening) and RUL-004 (High value transaction spike)
    acc30_txs = [t for t in txs_by_account["ACC-030"] if t["amount"] == 150000.0]
    if acc30_txs:
        ref_tx = acc30_txs[0]
        flags.append({
            "account_id": "ACC-030",
            "tx_id": ref_tx["tx_id"],
            "rule_id": "RUL-007",
            "severity": "high",
            "created_at": ref_tx["timestamp"],
            "reason": "Dormant account activated by a massive outbound transfer after 210 days of inactivity."
        })
        flags.append({
            "account_id": "ACC-030",
            "tx_id": ref_tx["tx_id"],
            "rule_id": "RUL-004",
            "severity": "high",
            "created_at": ref_tx["timestamp"],
            "reason": "Transaction size ($150,000) exceeds average historical tx sizes by 500x."
        })

    # ACC-038: RUL-008 (Peeling micro-withdrawals)
    acc38_txs = txs_by_account["ACC-038"]
    if acc38_txs:
        ref_tx = acc38_txs[-1]
        flags.append({
            "account_id": "ACC-038",
            "tx_id": ref_tx["tx_id"],
            "rule_id": "RUL-008",
            "severity": "high",
            "created_at": ref_tx["timestamp"],
            "reason": "Peeling chain activity: 6 rapid micro-withdrawals to unique external addresses in 30 minutes."
        })

    # 2. Fill in the remaining flags up to 25.
    # We want a distribution of low/med/high across other accounts.
    # Total flags must be exactly 25. We currently have 6. We need 19 more.
    # Let's generate a mix of Med and Low severity flags on non-risky accounts, and maybe one more high severity flag.
    non_risky_account_ids = [aid for aid in account_ids if aid not in ["ACC-010", "ACC-020", "ACC-030", "ACC-038"]]
    
    # We need exactly 19 more.
    flag_severity_options = ["low", "med", "high"]
    flag_severity_weights = [60, 35, 5]  # Keep high flags rare on standard accounts

    while len(flags) < NUM_FLAGS:
        acc_id = random.choice(non_risky_account_ids)
        acc_txs = txs_by_account[acc_id]
        
        # Ensure we have transactions to flag, otherwise pick another account
        if not acc_txs:
            continue
            
        ref_tx = random.choice(acc_txs)
        
        # Select a rule (not rule 1, 3, or 8, which are clustered on risky accounts)
        rule = random.choice([r for r in rules if r["rule_id"] not in ["RUL-001", "RUL-003", "RUL-008"]])
        severity = rule["severity_default"]
        
        # Skip if we already flagged this transaction to avoid duplicates
        if any(f["tx_id"] == ref_tx["tx_id"] and f["rule_id"] == rule["rule_id"] for f in flags):
            continue
            
        # Description reason
        reason_map = {
            "RUL-002": f"IP mismatch detected: Tx from {ref_tx['ip_country']} instead of registered account country.",
            "RUL-004": f"Transaction of {ref_tx['amount']} {ref_tx['currency']} exceeds standard risk thresholds.",
            "RUL-005": f"Wash trading patterns detected in trades matching internal exchange IDs.",
            "RUL-006": f"High rate of trade orders submitted via API from device {ref_tx['device_id']}.",
            "RUL-007": f"Account reactivation trade triggered after long periods of hibernation."
        }
        reason = reason_map.get(rule["rule_id"], "Automated risk score threshold breach.")

        flags.append({
            "account_id": acc_id,
            "tx_id": ref_tx["tx_id"],
            "rule_id": rule["rule_id"],
            "severity": severity,
            "created_at": ref_tx["timestamp"],
            "reason": reason
        })

    # Sort flags chronologically
    flags.sort(key=lambda x: x["created_at"])
    
    # Set unique sequential flag_id
    for idx, flag in enumerate(flags):
        flag["flag_id"] = f"FLG-{(idx + 1):03d}"

    # Write flags.csv
    with open(FLAGS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["flag_id", "account_id", "tx_id", "rule_id", "severity", "created_at", "reason"])
        writer.writeheader()
        writer.writerows(flags)

    # ==========================================
    # Verification & Summary Counts
    # ==========================================
    print("\nDataset Generation Complete! Summary Statistics:")
    print(f"  - Rules:        {len(rules)}")
    print(f"  - Accounts:     {len(accounts)}")
    print(f"  - Transactions: {len(transactions)}")
    print(f"  - Cases:        {len(cases)}")
    print(f"  - Flags:        {len(flags)}")
    
    # Let's count flag severities
    severities = {"low": 0, "med": 0, "high": 0}
    for f in flags:
        severities[f["severity"]] += 1
    print(f"  - Flags by Severity: Low={severities['low']}, Med={severities['med']}, High={severities['high']}")

    # Let's count high-severity flags clustering on risky accounts
    risky_flags = [f for f in flags if f["account_id"] in ["ACC-010", "ACC-020", "ACC-030", "ACC-038"]]
    risky_high_flags = [f for f in risky_flags if f["severity"] == "high"]
    print(f"  - High-Severity Flags on Risky Accounts (ACC-010/020/030/038): {len(risky_high_flags)} out of {severities['high']} total high flags.")
    
    print("\nFiles written successfully to data directory.")

if __name__ == "__main__":
    generate_dataset()
