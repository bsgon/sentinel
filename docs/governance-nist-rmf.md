# Governance: Sentinel and the NIST AI Risk Management Framework

*Paste-ready section for the Kaggle writeup (Track: Agents for Business). ~600 words.*

---

A Trust & Safety system that can freeze a customer's account is a high-stakes
automation: a wrong decision is slow to reverse, damages customer trust, and can
carry regulatory weight. Sentinel is therefore designed not just to *work*, but to
be *governable*. Its oversight design maps directly onto the four functions of the
**NIST AI Risk Management Framework (AI RMF 1.0)** — Govern, Map, Measure, and
Manage — turning "human oversight" from a slogan into a set of concrete, auditable
controls.

### Govern — policies, roles, and accountability

Governance in Sentinel is enforced in code, not left to convention. The
`TriageAgent` operates under a **constrained action policy**: its Pydantic output
schema (`TriageResult`) makes it structurally impossible to recommend anything
outside the allowed set — `monitor`, `request_kyc`, `escalate`, `freeze_account`.
The model cannot invent a novel action, however it is prompted. Accountability is
reinforced by **separation of duties**: each agent has a single responsibility, and
critically, *only the Orchestrator is permitted to change state*. The reasoning
agents (Triage, Investigation, Report) are deliberately denied write access, so no
LLM can act unilaterally on the production system.

### Map — establishing the risk context

Before any action is weighed, Sentinel establishes what kind of risk it is looking
at. The `TriageAgent` classifies each incoming flag's **severity** and **category**
against `rules.csv`, the policy table that encodes the exchange's risk appetite —
for example, a withdrawal to a sanctioned address maps to a high-severity freeze,
while a wash-trading pattern maps to low-severity monitoring. This mapping step
ensures that the *response* is always grounded in an explicit, organization-defined
notion of *risk*, rather than an ad-hoc model judgment.

### Measure — analyze, assess, and trace

Sentinel measures each incident through evidence and traceability. The
`InvestigationAgent` assembles a neutral **evidence dossier** — account profile,
recent transactions, all triggered flags, and prior cases — by calling the
**read-only MCP server**. Because the investigation tools cannot mutate data, the
measurement phase carries no risk of side effects. Every run then emits two durable
artifacts: a **PII-redacted decision trail** (`decision_trail.log`) capturing the
action, the decision, the rationale, and a timestamp; and a structured **RCA
report** documenting signals and reasoning. Together these make every automated
decision reconstructable after the fact — the foundation of any audit.

### Manage — prioritize and mitigate

Sentinel's response is **risk-proportionate**. Low-risk recommendations proceed
automatically, keeping analysts focused on what matters; but any high-risk action
(`freeze_account`) **pauses the pipeline and requires an explicit human
`approve`/`deny`** before the state change is committed. This human-in-the-loop gate
is the central mitigation: it bounds the blast radius of an automated error to
exactly the irreversible decisions, where human judgment is most valuable. Two
further controls limit residual risk — **least privilege** (the LLMs hold no write
capability; investigation tooling is read-only) and **data minimization** (regex-based
PII redaction scrubs IPs, device IDs, account IDs, and wallet addresses from logs
and reports before they are persisted).

### Why this matters

Read together, the **Govern** and **Manage** functions are where Sentinel's
human-oversight argument lives: a constrained policy defines *what the system is
allowed to propose*, and the approval gate defines *what a human must authorize
before it happens*. The **Map** and **Measure** functions ensure that the human at
the gate is not approving blind — they are handed a classified risk and a complete,
auditable evidence dossier. This is the difference between an agent that *acts* and
an agent that is *accountable*.
