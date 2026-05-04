# Self-hosted agentic lead-gen automation plan (real-code implementation path)

Date: 2026-05-04

## Objective

Turn `stormlead` into a fully automated, self-hosted lead-gen system with AI agents that:

1. Ingests leads from forms/webhooks.
2. Scores and deduplicates leads.
3. Routes leads through a resilient ping-post auction.
4. Triggers follow-up actions (email/SMS/voice) with guardrails.
5. Continuously improves buyer routing based on outcomes.

This plan focuses on production-grade open-source components with active GitHub repos and official documentation.

---

## Recommended OSS stack upgrades (verified)

### 1) Orchestration + human-in-the-loop workflows
- **n8n** (self-hosted) for deterministic orchestration, retries, approvals, and integrations.
- GitHub: https://github.com/n8n-io/n8n
- Docs: https://docs.n8n.io/hosting/

Why here: your current stack already has service boundaries and event-like flow (`lead.captured`), so n8n can orchestrate cross-service automation without replacing your core auction logic.

### 2) Stateful AI-agent runtime for qualification and recovery flows
- **LangGraph** for durable/stateful multi-step agent execution.
- GitHub: https://github.com/langchain-ai/langgraph
- Docs: https://langchain-ai.github.io/langgraph/

Why here: your `services/agent-runtime/` already contains domain agent modules (`qualify.py`, `execution.py`, `worker.py`), which maps directly to graph-based agent state machines.

### 3) Multi-agent teamwork option for specialized roles
- **AutoGen** for agent-to-agent collaboration (e.g., verifier agent + routing agent + outreach strategist).
- GitHub: https://github.com/microsoft/autogen
- Docs: https://microsoft.github.io/autogen/stable/

Why here: use selectively for complex tasks (e.g., dispute triage), while keeping deterministic steps in n8n.

### 4) Vector memory for retrieval-based lead context
- **Qdrant** as self-hosted vector database.
- GitHub: https://github.com/qdrant/qdrant
- Docs: https://qdrant.tech/documentation/

Why here: store normalized buyer outcomes and call transcripts to improve qualification prompts and routing decisions.

---

## Real-code integration plan in this repo

## Phase 1 — deterministic automation backbone (1-2 weeks)

### 1. Emit canonical lead events from form-receiver
Add a typed event publisher call after successful write in `services/form-receiver/src/form_receiver/api.py`.

```python
from stormlead_core.events import EventBus

bus = EventBus()

await bus.publish(
    topic="lead.captured",
    payload={
        "lead_id": str(lead.id),
        "phone": lead.phone,
        "zip": lead.zip,
        "captured_at": lead.created_at.isoformat(),
    },
)
```

### 2. Add idempotent delivery keys for buyer postbacks
In `services/ping-post/src/ping_post/auction.py`, include an idempotency header per `(lead_id,buyer_id)`.

```python
import hashlib

idempotency_key = hashlib.sha256(f"{lead.id}:{buyer.id}".encode()).hexdigest()
headers["Idempotency-Key"] = idempotency_key
```

### 3. Build n8n workflow for lead lifecycle
Create self-hosted n8n workflow:
- Trigger: webhook/event `lead.captured`.
- Call `agent-runtime` qualify endpoint.
- If `quality_score >= threshold`: call `ping-post`.
- On failure/timeouts: enqueue retry path and operator alert.

Use queue mode for worker scaling in n8n per hosting docs.

---

## Phase 2 — AI agent hardening (2-4 weeks)

### 4. Convert qualify flow into LangGraph state machine
In `services/agent-runtime/src/agent_runtime/qualify.py`, model explicit states:
- `collect_signals`
- `fraud_check`
- `score`
- `decision`
- `human_review`

Minimal skeleton:

```python
from langgraph.graph import StateGraph, END

class QualifyState(dict):
    pass

def collect_signals(state: QualifyState) -> QualifyState:
    # call phone/address validators
    return state

def fraud_check(state: QualifyState) -> QualifyState:
    # risk heuristics
    return state

def score(state: QualifyState) -> QualifyState:
    # compute quality_score
    return state

def route(state: QualifyState) -> str:
    return "human_review" if state.get("needs_review") else "done"

graph = StateGraph(QualifyState)
graph.add_node("collect_signals", collect_signals)
graph.add_node("fraud_check", fraud_check)
graph.add_node("score", score)
graph.add_node("human_review", lambda s: s)
graph.add_edge("collect_signals", "fraud_check")
graph.add_edge("fraud_check", "score")
graph.add_conditional_edges("score", route, {"human_review": "human_review", "done": END})
app = graph.compile()
```

### 5. Persist retrieval memory in Qdrant
Store embeddings for:
- buyer rejection reasons
- dispute outcomes
- call outcome summaries

Then retrieve similar prior outcomes during lead scoring for contextual calibration.

---

## Phase 3 — closed-loop optimization (4-8 weeks)

### 6. Buyer performance feedback loop
Extend scoring inputs with:
- win-rate by buyer/geo/service line
- dispute-rate
- payment latency

Add periodic retraining/retuning workflow in n8n:
- nightly aggregate SQL
- update buyer routing weights
- canary deploy weights

### 7. Human approval gates for high-risk actions
Require human approval for:
- low-confidence review leads
- large outbound spend actions
- routing exceptions

Implement as n8n wait/approval nodes + audit log entry in Postgres.

---

## Concrete repo changes to schedule next (no mocks)

1. `services/form-receiver/src/form_receiver/api.py`
   - publish `lead.captured` with strict schema validation.
2. `services/agent-runtime/src/agent_runtime/api.py` (add if missing)
   - `POST /qualify` endpoint returning structured score + reasons.
3. `services/ping-post/src/ping_post/auction.py`
   - idempotency key + retry-safe delivery records.
4. `libs/stormlead_db/src/stormlead_db/tables.py`
   - add `lead_events`, `buyer_scorecards`, `delivery_attempts` tables.
5. `infra/compose/dev/docker-compose.yml`
   - add n8n + qdrant services and internal networking.

---

## GitHub repos to study before coding each phase

- n8n core: https://github.com/n8n-io/n8n
- n8n self-hosted AI starter kit: https://github.com/n8n-io/self-hosted-ai-starter-kit
- LangGraph: https://github.com/langchain-ai/langgraph
- AutoGen: https://github.com/microsoft/autogen
- Qdrant: https://github.com/qdrant/qdrant

---

## Acceptance criteria for “automated self-hosted lead gen”

1. 95%+ of captured leads process end-to-end without human intervention.
2. All buyer postbacks are idempotent and retry-safe.
3. Every AI decision includes rationale + trace id.
4. Human approvals are auditable with immutable logs.
5. Routing weights update from real buyer outcomes at least daily.

If these are met, your system is not just “AI-assisted”; it is truly agentic, automated, and operationally self-hosted.
