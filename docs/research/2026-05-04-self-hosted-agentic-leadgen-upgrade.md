# 2026-05-04 self-hosted agentic lead-gen upgrade plan (real-code path)

## goal

Turn `stormlead` into an end-to-end autonomous, self-hosted lead-gen system with production-safe agent orchestration, retrieval/crawling, and deterministic handoffs into your ping-post engine.

## best-fit external repos/docs to adopt now

1. **hatchet-dev/hatchet** (workflow + retries + schedules).
   - Repo: https://github.com/hatchet-dev/hatchet
   - Why: durable orchestration for `qualify_lead`, `buyer_match`, `voice_nurture` with explicit retries, backoff, and queue semantics.
2. **n8n-io/self-hosted-ai-starter-kit** (reference compose for agentic local AI stack).
   - Repo: https://github.com/n8n-io/self-hosted-ai-starter-kit
   - Why: practical compose patterns for self-hosted AI services and secure `.env` handling.
3. **BerriAI/litellm** (gateway for model routing, budget controls, and provider abstraction).
   - Repo: https://github.com/BerriAI/litellm
4. **Crawl4AI docs** (self-hosted crawler for prospect discovery / enrichment).
   - Docs: https://docs.crawl4ai.com/core/self-hosting/
5. **n8n hosting docs** (security hardening checklist for self-hosted automation control planes).
   - Docs: https://docs.n8n.io/hosting/

## target architecture delta (from current stormlead)

- Keep **FastAPI services + Postgres + Hatchet + LiteLLM** as core.
- Add **crawler worker** that discovers buyer candidates and validates website/service-area signals.
- Add **lead-ops agent workflows** with strict state transitions in DB (no hidden in-memory state).
- Add **human override queues** for high-value / low-confidence leads.

## implementation phases (no mock)

### phase 1 (week 1): deterministic orchestration contract

1. Add a lead workflow state machine in `libs/stormlead_core`:
   - `captured -> enriched -> qualified -> auctioned -> sold|unsold -> nurtured`.
2. Persist every transition in Postgres with idempotency key (`lead_id + step + version`).
3. Run all transitions via Hatchet workers, not ad-hoc async tasks.

**real code pattern (python, hatchet worker):**

```python
# services/agent-runtime/src/worker_lead_pipeline.py
from hatchet_sdk import Hatchet
from stormlead_core.models import LeadEvent
from stormlead_core.pipeline import run_qualification

hatchet = Hatchet()

@hatchet.task(name="lead.qualify", retries=3, timeout="120s")
def qualify_lead(input: dict) -> dict:
    event = LeadEvent.model_validate(input)
    result = run_qualification(event)
    return {"lead_id": event.lead_id, "score": result.score, "status": result.status}
```

### phase 2 (week 1-2): enrichment crawler (self-hosted)

1. Stand up Crawl4AI service in `infra/compose/dev/docker-compose.yml`.
2. Add `services/enrich-worker` to call crawler + parse structured signals:
   - business name
   - phone
   - service area mentions
   - emergency/storm intent markers
3. Store evidence JSON in Postgres for auditor visibility.

**compose fragment to add (real):**

```yaml
crawl4ai:
  image: unclecode/crawl4ai:latest
  ports:
    - "11235:11235"
  restart: unless-stopped
```

### phase 3 (week 2): model gateway hardening + cost controls

1. Keep LiteLLM as the single LLM ingress.
2. Create per-agent virtual keys with spend caps:
   - `agent.qualifier`
   - `agent.buyer_matcher`
   - `agent.voice_nurture`
3. Enforce fallback order per task class (cheap->smart escalation).

**real code pattern (OpenAI client via LiteLLM):**

```python
from openai import OpenAI

client = OpenAI(base_url="http://litellm:4000", api_key="${LITELLM_VKEY_QUALIFIER}")
resp = client.chat.completions.create(
    model="openai/gpt-4.1-mini",
    messages=[{"role": "system", "content": "qualify lead"}, {"role": "user", "content": lead_text}],
    temperature=0,
)
```

### phase 4 (week 2-3): autonomous buyer expansion loop

1. Add weekly Hatchet cron job `buyers.discovery.weekly`.
2. Crawl target metros + vertical directories.
3. Auto-create draft buyers with confidence score.
4. Route low confidence to manual review queue.

## immediate repo changes to make next (ordered backlog)

1. Create `services/enrich-worker/` with:
   - `main.py`
   - `crawler_client.py`
   - `scoring.py`
   - tests for parsing + score thresholds.
2. Add shared package:
   - `libs/stormlead_core/stormlead_core/pipeline.py` for deterministic state transitions.
3. Add Alembic migration:
   - `lead_state_transitions` table with unique constraint on idempotency key.
4. Add `just replay-lead LEAD_ID=<id>` command to rerun a lead from a transition checkpoint.

## security and reliability constraints

- No direct model calls from services (all must go through LiteLLM).
- No mutable workflow state outside DB.
- Every agent decision writes:
  - prompt version
  - model id
  - token usage
  - confidence
  - evidence pointer
- For self-hosted control plane UIs, require SSO/2FA and private network exposure only.

## why this is the best fit for stormlead

- Matches your current stack direction (FastAPI, Hatchet, LiteLLM, Postgres).
- Minimizes new moving parts while adding true autonomy loops.
- Keeps core moat (ping-post auction) deterministic and auditable while allowing AI to optimize around it.
