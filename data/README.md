# Sentinel Synthetic Data

This directory stores the synthetic data schemas and tables representing the transaction, account, and incident state of the crypto exchange.

## Schema Specifications

The database contains the following tables (expected as CSV or JSON, with ~30–50 rows per table to support testing):

### 1. `accounts`
* `account_id` (primary key): Unique identifier for the account.
* `created_at`: Isoformat timestamp of account creation.
* `kyc_level`: KYC verification level (e.g., `0`, `1`, `2`).
* `country`: 2-letter country code of the customer.
* `risk_score`: Float between `0.0` (safe) and `1.0` (extremely risky).
* `status`: Current status, restricted to: `active`, `under_review`, `frozen`.

### 2. `transactions`
* `tx_id` (primary key): Unique identifier for the transaction.
* `account_id` (foreign key): Reference to `accounts.account_id`.
* `timestamp`: Isoformat timestamp of the transaction.
* `type`: Type of transaction, restricted to: `deposit`, `withdrawal`, `trade`.
* `amount`: Numeric value of the transaction.
* `currency`: Crypto/Fiat ticker (e.g., `BTC`, `ETH`, `USD`).
* `counterparty_address`: Recipient/sender blockchain address or external account.
* `channel`: Transaction channel (e.g., `api`, `web`, `mobile`).
* `ip_country`: 2-letter country code from which the transaction was initiated.
* `device_id`: Identifier for the client device.

### 3. `flags`
* `flag_id` (primary key): Unique identifier for the risk flag.
* `account_id` (foreign key): Reference to `accounts.account_id`.
* `tx_id` (foreign key, optional): Reference to `transactions.tx_id`.
* `rule_id` (foreign key): Reference to `rules.rule_id`.
* `severity`: Level of flag severity, restricted to: `low`, `med`, `high`.
* `created_at`: Isoformat timestamp when the flag was triggered.
* `reason`: Descriptive explanation of the rule trigger.

### 4. `cases`
* `case_id` (primary key): Unique identifier for historical cases.
* `account_id` (foreign key): Reference to `accounts.account_id`.
* `opened_at`: Isoformat timestamp when the case was opened.
* `category`: Categorization (e.g., `Structuring`, `IP_Mismatch`, `Account_Takeover`).
* `resolution`: Resolution details (e.g., `cleared`, `terminated`, `monitored`).
* `rca_summary`: Detailed root cause analysis summary.

### 5. `rules`
* `rule_id` (primary key): Unique identifier for the triage rule.
* `name`: Descriptive name of the rule.
* `description`: What the rule triggers on.
* `severity_default`: Default severity classification (`low`, `med`, `high`).
* `recommended_action`: Default recommended action (`monitor`, `request_kyc`, `escalate`, `freeze_account`).

---

## Consistency Rules
* All `flags.account_id` and `flags.tx_id` must match real, existing rows in `accounts` and `transactions`.
* High-severity flags should cluster on a small subset of accounts designated as "risky" to simulate real incident triage.
* Historical `cases` should exist for some of the flagged accounts to allow contextual lookup during investigations.
