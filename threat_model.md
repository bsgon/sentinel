# STRIDE Threat Model — Sentinel

This document presents a detailed security analysis of the **Sentinel** project using the **STRIDE** methodology (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege). The goal is to evaluate the incident-triage assistant architecture against common threats and propose mitigation recommendations for production environments.

---

## 📐 Architecture Overview & Trust Boundaries

Sentinel implements a multi-agent architecture based on the Google Agent Development Kit (`google-adk`) and the Model Context Protocol (MCP). Data flows cross the following trust boundaries:
1. **User Input / CLI**: Reception of synthetic risk flag identifiers.
2. **Agent Layer (Orchestrator and Specialists)**: Natural language processing and classification via the external Gemini API.
3. **Local MCP Server**: Local `stdio` subprocess exposing read-only data-querying tools.
4. **Storage (CSV Files)**: Local filesystem containing account, transaction, rule, and audit log data.
5. **Human-in-the-Loop (HITL) Approval Gate**: Interactive terminal prompt for operators to authorize high-risk actions.

---

## 📊 STRIDE Evaluation Matrix

The following table summarizes Sentinel's compliance status against each STRIDE pillar:

| Threat | Description | Current Status | Severity | Existing Mitigation | Gap / Remaining Risk |
|---|---|---|---|---|---|
| **S**poofing | Faking the identity of the orchestrator, MCP server, or human operator. | **Partially Secure** | 🔴 High | Local MCP communication via stdio subprocess; process boundary isolation. | Lack of authentication in CLI input and human approval gate (HITL) responses. |
| **T**ampering | Modifying database files, altering rules, or manipulating agent outputs. | **Partially Secure** | 🔴 High | Read-only MCP tools; state modifications executed by static code. | Local plaintext CSV files lack cryptographic integrity or granular OS-level access control. |
| **R**epudiation | An operator denying they authorized an action, or deleting audit trails. | **Vulnerable** | 🟡 Medium | Recording execution details in `data/decision_trail.log`. | Plain text log files without cryptographic signatures or write-once (WORM) constraints. |
| **I**nformation Disclosure | Exposing customer PII (IPs, device IDs, wallet addresses, bank refs) in logs. | **Secure** | 🟢 Low | `redact_pii` filter actively scrubbing logs and RCA reports. | Raw PII is sent to the Gemini API (requires corporate data protection agreements). |
| **D**enial of Service | Exhausting system resources or model API quota limits. | **Partially Secure** | 🟡 Medium | Automatic retry/backoff handler in the runner for 429 quota errors. | Synchronous execution; blocking terminal inputs; reading entire CSVs into memory. |
| **E**levation of Privilege | Executing restricted state changes without going through the approval gate. | **Partially Secure** | 🔴 High | Agent privilege separation: Triage has no tools; Investigation is read-only. | Hardcoded `bypass_gate=True` logic exists in the main orchestrator code. |

---

## 🔍 Detailed Pillar Analysis

### 1. Spoofing (Identity Spoofing)
* **Threat**: A malicious process or user could send fake instructions to the MCP server or forge operator approval responses.
* **Evaluation**:
  * The communication channel between the Sentinel orchestrator and the local MCP server uses the FastMCP framework over standard input/output (`stdio`) managed by the active Python subprocess (`sys.executable`). This provides process-level isolation, preventing external network entities from querying database tools.
  * However, in the interactive CLI (`run.py`), any keyboard input is accepted as the operator's decision (`approve`/`deny`). There is no session token verification, digital signature, or Role-Based Access Control (RBAC).

> [!IMPORTANT]
> **Mitigation Recommendation**: Transition the approval gate from the console CLI to a secure API endpoints protected by JWT authentication and digital signatures for high-risk actions.

---

### 2. Tampering (Data Manipulation)
* **Threat**: Direct manipulation of synthetic database CSV files or default risk rules that influence LLM decisions.
* **Evaluation**:
  * **Strength**: The database tools exposed via the MCP server (`get_account`, `get_recent_transactions`, `get_flags`, `get_prior_cases`) are strictly **read-only**. The `InvestigationAgent` has no write permissions, reducing prompt-injection write vectors. Account status updates are hardcoded in static Python code rather than delegated to LLM decision boundaries.
  * **Vulnerability**: The CSV database files under `data/` are stored in plaintext. An attacker with access to the host machine could manually alter account risk scores, transaction histories, or the rules policy file (`rules.csv`).

> [!TIP]
> **Mitigation Recommendation**: Replace the CSV database files with a relational database management system (RDBMS) utilizing strict credential access and OS-level file system permissions.

---

### 3. Repudiation
* **Threat**: A human operator approving a false freeze action and later denying it, claiming system malfunction.
* **Evaluation**:
  * The orchestrator logs all events, triage details, dossier contexts, and final outcomes to `data/decision_trail.log`.
  * However, because the log is a local plain text file, it lacks tamper-proof protections. Anyone with write access can edit or delete log lines. Furthermore, the system only logs the generic `operator-1` identity without capturing cryptographic signatures.

> [!WARNING]
> **Mitigation Recommendation**: Stream sanitized logs to a central, write-once-read-many (WORM) log aggregator (e.g., AWS CloudWatch, Splunk, or SIEM) with cryptographic hash chaining.

---

### 4. Information Disclosure (Data Leakage)
* **Threat**: Leaking customer Personally Identifiable Information (PII) to compliance archives or unauthorized personnel.
* **Evaluation**:
  * **Strength**: Sentinel actively runs a multi-pass regex filter (`redact_pii`) on both local log dumps and generated RCA reports. It successfully sanitizes IP addresses, device IDs (`DEV-xxx`), account IDs (`ACC-xxx`), and wallet/bank wire identifiers.
  * **Vulnerability**: Raw PII is still sent to external Google Gemini API endpoints during runtime execution. While transit is encrypted, enterprise usage requires data protection agreements to ensure zero data retention policies.

---

### 5. Denial of Service
* **Threat**: Flooding the system with fake alerts to exhaust API limits or CPU resources.
* **Evaluation**:
  * The runner handles Gemini 429 quota exhaustion (`RESOURCE_EXHAUSTED`) with automatic retry logic.
  * However, reading entire CSV tables into memory for every MCP query does not scale. Also, the interactive CLI blocks process threads while waiting for human input, rendering the pipeline unable to handle concurrent alerts.

> [!TIP]
> **Mitigation Recommendation**: Implement caching for database reads and migrate the pipeline execution to an asynchronous message queue (e.g., Celery, RabbitMQ) to decouple automated triage from the operator response interface.

---

### 6. Elevation of Privilege
* **Threat**: Bypassing the human operator gate to execute account freezes.
* **Evaluation**:
  * The agents adhere to the principle of least privilege (Triage has no database tools; Investigation is read-only).
  * However, the main orchestrator node in `sentinel/orchestrator.py` checks `ctx.state.get("bypass_gate")` to decide whether to skip the approval gate. While designed for test automation, hardcoding bypass logic in the main control flow poses a critical elevation of privilege vulnerability.

> [!CAUTION]
> **Mitigation Recommendation**: Completely remove the `bypass_gate` state checks from the main orchestrator code. Use isolated test mocks rather than building logical backdoors into production code files.

---

## 🏁 Conclusion & Final Verdict

Sentinel **implements outstanding security design patterns** for multi-agent applications, such as separation of agent tool privileges, interactive approval gates (HITL), and active PII sanitization in compliance logs.

However, to be deemed production-ready, it **does not fully pass the STRIDE assessment** due to local infrastructure constraints (plaintext CSV databases, unsigned logs, and lack of operator authentication). Adopting the recommended database, logging, and API-based authorization patterns will mitigate these security gaps.
