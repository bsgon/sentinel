# Sentinel: A Human-in-the-Loop Trust & Safety Triage Team

### A multi-agent pipeline that triages crypto-exchange risk flags at machine speed — but stops and asks a human before it ever freezes an account.

**Track: Agents for Business**

---

## The problem

Every cryptocurrency exchange runs a Trust & Safety (T&S) function whose job is to catch bad activity — money laundering, sanctioned-address withdrawals, structuring, wash trading — without punishing legitimate customers. Automated rules generate a relentless stream of flags, and a human analyst has to triage each one: figure out how serious it is, pull the account's history, decide what to do, and document the decision for compliance.

This creates a painful trade-off with real money on both sides:

- **Do it manually** and you are slow and expensive. Analysts spend most of their time gathering context — opening dashboards, reading transaction logs, checking prior cases — before they can even begin to decide. Backlogs grow, and genuinely dangerous activity sits in a queue.
- **Fully automate it** and you are reckless. Freezing a customer's account is a near-irreversible action: it severs someone from their money, destroys trust, and can carry regulatory consequences if done wrongly. A confidently-wrong model that freezes accounts on its own is a liability, not a product.

The right answer is neither extreme. T&S needs **speed on the investigation and reasoning**, but **human judgment on the irreversible decision**. That is exactly the shape of problem that a well-designed multi-agent system fits.

## Why agents — and why *multiple* of them

A single large prompt could classify a flag. But a believable T&S system has to do four genuinely different jobs — classify under policy, gather evidence from systems of record, decide whether a human must intervene, and produce an auditable report — and those jobs have *different trust requirements*. Collapsing them into one model means one component holds every capability at once: it can read data, make policy decisions, and (if wired to act) change state. That is the worst possible security posture.

Sentinel instead mirrors a real triage standard operating procedure as a pipeline of **single-responsibility agents**, each holding only the capability its job demands:

- The agent that **decides** has no access to data or tools.
- The agent that **reads data** makes no decisions.
- The agent that could trigger an **irreversible action** cannot perform it — it must route through a human.

The multi-agent split is not decoration to look sophisticated; each boundary is a deliberate confinement that makes the system safer and easier to reason about. That is the "meaningful use of agents" the problem actually calls for.

## Solution overview

Sentinel takes a single `flag_id` (a synthetic flagged account event) and runs it through a **triage → investigation → human approval → RCA report** pipeline:

1. **Orchestrator Agent** — the control plane. It validates input, coordinates the other agents, enforces PII redaction, executes any approved state change itself, and logs the full decision trail. It deliberately does *no* reasoning about the flag.
2. **Triage Agent** — a constrained classifier. Given the flag and the exchange's rule policy, it outputs a `severity`, a `category`, and a `recommended_action`. Its output schema permits only four actions — `monitor`, `request_kyc`, `escalate`, `freeze_account` — so it cannot invent an action outside policy. It has no tools.
3. **Investigation Agent** — the only agent with data access, and only through a **read-only MCP server**. It assembles a neutral evidence dossier: account profile, recent transactions, all triggered flags, and prior cases. It makes no decisions.
4. **Approval Gate** — the human-in-the-loop control. If the recommended action is high-risk (`freeze_account`), the pipeline **pauses** and surfaces the proposed action, the reasoning, and the dossier, then waits for an explicit `approve`/`deny`. Low-risk actions proceed automatically.
5. **Report Agent** — invokes a reusable **RCA report skill** to produce a structured incident report (Summary, Timeline, Signals/Evidence, Decision & Rationale, Action Taken, Follow-ups).

Crucially, **no language model ever writes state**. When an account is frozen, it is the Orchestrator — ordinary, auditable code — that performs the change, and only after a human has approved it.

## Architecture

```
Flag (synthetic) ──► Orchestrator Agent
   1) Triage Agent        → {severity, category, recommended_action}   [constrained policy]
   2) Investigation Agent → evidence dossier   [via read-only MCP server]
   3) Approval Gate       → if high-risk: PAUSE → human approve/deny   [human-in-the-loop]
   4) Report Agent        → RCA report   [reusable skill]
        └─► PII-redacted decision trail (logged)
```

The repository README contains two Mermaid diagrams — a runtime *flow* view and a *component* view that makes the trust boundary explicit (which component may touch data, tools, state, or the human). The investigation tooling is served by a local **FastMCP** server over stdio that exposes exactly four read-only functions (`get_account`, `get_recent_transactions`, `get_flags`, `get_prior_cases`) over a synthetic CSV dataset. Because those tools cannot mutate anything, the entire investigation phase is side-effect free by construction.

## Concepts demonstrated

Sentinel implements four of the course's key concepts, each mapped to a real need rather than bolted on:

- **Multi-agent system (ADK).** Built on Google's Agent Development Kit. The Orchestrator is an ADK `Workflow`; Triage, Investigation, and Report are ADK `Agent`s wired to Gemini; sub-agents run as node computations via the `Context` API.
- **MCP server.** A read-only FastMCP server provides the Investigation Agent's context tools, cleanly separating "how we fetch data" from "how we reason about it."
- **Security features (the centerpiece).** Three layers: a *constrained action policy* (the Triage Agent's Pydantic schema makes out-of-policy actions structurally impossible); a *human-in-the-loop approval gate* implemented as an ADK long-running interrupt; and *PII redaction* that scrubs IPs, device IDs, account IDs, and wallet addresses from every log and report before it is persisted.
- **Reusable agent skill.** The RCA report generator is a standalone Python function decoupled from the ADK framework — it takes plain dicts and strings, so it can be reused in tests, scripts, dashboards, or other agents without dragging the agent runtime along.

## Governance: mapping to the NIST AI RMF

Because Sentinel automates a high-stakes decision, it is designed to be *governable*, not just functional. Its oversight maps onto the four functions of the **NIST AI Risk Management Framework**:

- **Govern** — A constrained action policy and strict separation of duties define what each agent may do; only the Orchestrator changes state, and only after human approval.
- **Map** — The Triage Agent classifies each flag's severity and category against a rule policy that encodes the exchange's risk appetite, establishing risk context before any action is weighed.
- **Measure** — The Investigation Agent assembles a measurable evidence dossier via read-only tools, and every run emits a PII-redacted decision trail and a structured RCA report for traceability.
- **Manage** — Risk-proportionate response: high-risk actions pause for a human, low-risk proceed automatically; least privilege and data minimization bound the residual risk.

Read together, **Govern** and **Manage** are where the human-oversight argument lives: policy defines what the system may *propose*, and the approval gate defines what a human must *authorize*. **Map** and **Measure** ensure the human at the gate is handed a classified risk and a complete evidence dossier — never asked to approve blind. This is the difference between an agent that merely *acts* and one that is *accountable*.

## Build journey & key tradeoffs

The system was built incrementally with an AI coding assistant, grounded in a written spec and a set of standing rules (read the spec before each task; never invent ADK/MCP APIs; all secrets via environment variables; everything synthetic; comment implementation, design, and behavior). The build order deliberately prioritized a working happy path — synthetic data, MCP server, then the three core agents end to end — before layering on the differentiators: the approval gate, the RCA skill, and a security/quality pass.

The most interesting tradeoff was in the approval gate. ADK commits a node's state only when the node *completes*, but the gate pauses *inside* a node to wait for the human. The pragmatic choice was to keep the orchestrator as a single node and accept that triage and investigation re-run once on resume, rather than prematurely splitting the pipeline into four persistent nodes. This is documented openly as a known limitation with its proper production fix, which we considered more honest than hiding it.

A second deliberate choice was to keep *all* data synthetic and *all* state changes in plain code. The repository is public, so there can be no real customer data and no secrets; and keeping freezes out of the LLM's hands means the security story does not depend on the model behaving — it depends on the architecture.

## Limitations & next steps

- **Resume replay.** As above, a high-risk flag re-runs triage and investigation once after the human resumes the gate. The fix is to split the orchestrator into discrete, sequential ADK nodes so each step's result is persisted before the next begins.
- **Synthetic, single-exchange scope.** The rules, schema, and data model one exchange's policies. Real deployment would integrate live systems of record behind the same MCP interface — notably without changing the agent layer, which is the point of the boundary.
- **Deterministic classifier.** Triage relies on a tight prompt plus a strict schema. A production version would add evaluation sets and regression tests over labeled flags to measure classification quality over time.
- **Single human gate.** Today any high-risk action needs one approval. A richer model would support role-based, multi-party approval for the most severe actions.

Sentinel is intentionally small, but complete: a portfolio-ready demonstration that agentic automation and human accountability are not in tension. The agents do the tireless work — classify, investigate, document — and a human keeps the one decision that must never be automated. That is what Trust & Safety actually needs.
