# Architecture Design Note

This document details the architectural decisions, pipeline design, cost accounting framework, and scoping decisions behind the Growtrics Agentic Content Generation Service.

---

## 1. Pipeline and Multi-Agent Design

The service implements a clean, decoupled 3-stage multi-agent pipeline to generate and verify educational items:

```
[Start Job]
   │
   ▼
[Generator Agent] (Uses gpt-4o-mini to draft the MCQ under strict schema)
   │
   ▼
[Validator Agent (Quality Gate)]
   ├── 1. Pydantic Parsing check (validates JSON structure)
   ├── 2. Programmatic Rule check (exact 4 choices A-D, uniqueness, key mapping)
   └── 3. LLM-as-Judge Audit (checks factuality, clarity, and difficulty scores)
   │
   ├───► [Passes All Gates] ──► [Save item as VALIDATED]
   │
   └───► [Fails Any Gate]
            │
            ▼
     [Attempts < Max (2)]?
            │
            ├──► Yes ──► [Repair Agent] (Fixes MCQ with Judge feedback) ──► Re-run Validation
            │
            └──► No ──► [Save item as REQUIRES_REVIEW] (HITL fallback)
```

### Decoupled Components and Roles:
- **Generator Agent**: Focuses strictly on creating creative and pedagogy-aligned questions based on the target subject and difficulty. Enforces output syntax via Pydantic model serialization.
- **Validator Agent**: Acting as a quality firewall. First running fast, zero-cost rules (schema validity, uniqueness of choices) before delegating to the more expensive LLM-as-Judge for semantic grading (evaluating truthfulness, explanation correctness, and grade appropriateness).
- **Repair Agent**: Acts only when validation fails. It receives the failed draft plus the precise auditor feedback. Rather than starting from scratch, it performs targeted repairs to save token consumption.

---

## 2. Quality Gate Specifications

The firewall gate enforces validation rules at three distinct layers:

1. **Layer 1: Structural Format (Pydantic)**: Checks that the JSON contains `question`, `choices`, `correct_answer`, and `explanation` fields.
2. **Layer 2: Rule Safety (Programmatic)**: Zero-cost checks:
   - Choices dictionary has exactly 4 items.
   - Keys are exactly A, B, C, D.
   - All choices have unique values (no duplicates).
   - Marked `correct_answer` is present in choices keys.
   - All string fields are populated (no empty values).
3. **Layer 3: Cognitive Quality (LLM-as-Judge)**: Evaluates the item using a structured grading rubric:
   - `difficulty_alignment` (Score $\ge 0.8$)
   - `factuality_score` (Score $\ge 0.8$)
   - `clarity_score` (Score $\ge 0.8$)
   - `explanation_alignment` (True)
   - `schema_valid` (True)

### Failure Recovery & Bounded Repairs:
- If any layer fails, the item moves to the `REPAIRING` state and the Repair Agent is invoked.
- We set `MAX_REPAIR_ATTEMPTS = 2`.
- If an item fails validation after 2 repairs, it transitions to a **`REQUIRES_REVIEW`** state rather than being discarded or entering an infinite loop. This preserves operator visibility and supports human-in-the-loop audit gates.

---

## 3. Telemetry and Cost Model

### Cost Tracker
We capture token metrics on every single LLM execution:
- Cost calculation: `Total Cost = (Input Tokens * Input Rate) + (Output Tokens * Output Rate)`.
- Pricing constants for default model (`gpt-4o-mini`):
  - Input: \$0.15 / 1M tokens
  - Output: \$0.60 / 1M tokens

### Projections at Scale (Default Model: `gpt-4o-mini`)
Estimated costs are illustrative and assume approximately 1,000 input tokens and 300 output tokens per generated item, including validation. Actual production costs depend on prompt size, repair frequency, and provider pricing:

| Items / Day | Estimated Daily Cost (Illustrative) |
|---|---|
| 1,000 | ~\$0.33 |
| 10,000 | ~\$3.30 |
| 100,000 | ~\$33.00 |

### Telemetry Latency Tracking
The telemetry engine captures P50 and P95 latency values from job event logs, enabling operators to identify bottlenecks during execution.

---

## 4. Scoping Decisions: What We Cut and Why

We deliberately prioritized core backend reliability, clean architecture, and durability over surface-level features:

| Feature | Reason for Cutting / Prototype Trade-off |
|---|---|
| **LangGraph Orchestration** | We intentionally implemented a custom orchestrator and state machine because the pipeline is linear and deterministic. Moving to LangGraph would add external dependencies and complexity. If branching logic increases, the decoupled providers/repositories allow migrating the orchestrator to LangGraph with minimal effort. |
| **Distributed Queues (Redis/Celery)** | Excluded to keep the prototype self-contained. SQLite + `asyncio.Queue` provides durable state-tracking and in-memory scheduling, showing robust job workers without external operational dependencies. |
| **Relational Database Server (PostgreSQL)** | Replaced with SQLite (`aiosqlite`). The Repository pattern abstracts database actions, allowing migration to PostgreSQL without editing application logic. |
| **Semantic Cache** | nice-to-have optimization. In production, prompt hashing and semantic caching (using Redis or GPTCache) would be added to reduce repeated generation costs. |
| **Job Cancellation Endpoints** | Excluded because it is not required for the challenge scope and adds unnecessary state-machine complexity for a prototype. |
| **Kubernetes (K8s)** | Overkill for a local prototype. Production execution maps perfectly to stateless serverless containers like Google Cloud Run or AWS Fargate. |
