# SPEC.md — Sentinel
> Grounding spec for the build agent. Read this before every task. Follow ADK/MCP API patterns from `/reference` (the course codelabs) — do not invent framework APIs.

## Summary
Sentinel is a multi-agent Trust & Safety incident-triage assistant for a crypto exchange. Given a flagged account event (synthetic), an `OrchestratorAgent` runs a **triage → investigation → human approval → RCA report** pipeline. The `TriageAgent` classifies the flag under a constrained action policy; the `InvestigationAgent` pulls account/transaction/case context through an MCP server; any high-risk action (e.g. `freeze_account`) pauses for explicit human approval before any state change; and a reusable RCA report skill drafts a structured incident report.

## Track
Agents for Business.

## Pipeline
```
Flag (synthetic) ─► OrchestratorAgent
   1) TriageAgent        → {severity, category, recommended_action}   [constrained policy]
   2) InvestigationAgent → dossier   [via MCP server: account, txns, prior cases]
   3) ApprovalGate       → if high-risk: PAUSE → human approve/deny   [human-in-the-loop]
   4) ReportAgent        → RCA report   [reusable skill]
   └─► decision trail (logged, PII-redacted)
```

## Agents (one responsibility each)
- **OrchestratorAgent** — entrypoint; takes a `flag_id`; coordinates the pipeline; routes the approval gate; logs the decision trail.
- **TriageAgent** — classifies the flag using `rules` as a constrained policy; may only choose from the allowed action list.
- **InvestigationAgent** — calls the MCP tools to assemble a context dossier (account, recent transactions, prior cases). Does not decide; only gathers context.
- **ApprovalGate** — for high-risk actions, pauses and requires explicit human confirmation before any state change.
- **ReportAgent** — invokes the RCA skill and returns the structured report.

## Constrained action policy
Allowed actions: `monitor`, `request_kyc`, `escalate`, `freeze_account`.
High-risk (require human approval before execution): `freeze_account`, and any future state-changing action.

## Synthetic data schema (in `/data`; ~30–50 rows per table)
- **accounts** — `account_id, created_at, kyc_level, country, risk_score, status` (active/under_review/frozen)
- **transactions** — `tx_id, account_id, timestamp, type` (deposit/withdrawal/trade)`, amount, currency, counterparty_address, channel, ip_country, device_id`
- **flags** — `flag_id, account_id, tx_id, rule_id, severity` (low/med/high)`, created_at, reason`
- **cases** — `case_id, account_id, opened_at, category, resolution, rca_summary`
- **rules** — `rule_id, name, description, severity_default, recommended_action`

Consistency: flags reference real `tx_id`/`account_id`; high-severity flags cluster on a few risky accounts; some accounts have prior `cases`.

## Concepts demonstrated (map)
| Concept | Where |
|---|---|
| Multi-agent system (ADK) | Code (the 4 agents + orchestration) |
| MCP Server | Code (`/mcp_server`, read-only tools) |
| Security features | Code + Video (constrained policy, PII redaction, human-in-the-loop) |
| Agent skill (RCA generator) | Code (`/skills`) |

## Hard constraints (non-negotiable)
- **Synthetic data only.** Never use or fabricate real user data.
- **No secrets in code.** All keys via environment variables; `.env` git-ignored; keep `.env.example`.
- **Comments** on every module, agent, and tool (implementation, design, behavior).
- Follow ADK/MCP patterns from `/reference`; if unsure of an API, read the reference rather than guessing.
- Keep agent boundaries meaningful — do not split into agents for appearance; each must have a real reason to exist.

## Stack
ADK (`google-adk`) + Gemini, plus an MCP server. Pin exact package versions from the `/reference` codelabs.
