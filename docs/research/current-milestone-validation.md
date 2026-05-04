# Current Milestone Validation

Date: 2026-05-04

## Lifecycle

StormLead now uses the audited lifecycle below for production workflow routing:

1. `form-receiver` inserts a new lead and records `start -> captured` with `event_type=lead.captured`.
2. `enrich-worker` handles `lead.captured`, makes a real HTTP fetch attempt against `LeadRow.page_url`, persists deterministic evidence in `lead_state_transitions.payload_json`, updates deterministic enrichment fields, records `captured -> enriched`, and emits `lead.enriched`.
3. `agent-runtime` handles `lead.enriched`, routes model calls through LiteLLM, persists qualification fields, records `enriched -> qualified` or `enriched -> rejected`, and emits `lead.qualified` or `lead.rejected`.
4. `ping-post` handles `lead.qualified`, runs buyer ping/post, records `qualified -> auctioned`, records `auctioned -> sold` or `auctioned -> unsold`, and emits `lead.unsold` on unsold outcomes.
5. `agent-runtime` handles `lead.unsold` and `lead.rejected`, records `unsold/rejected -> nurtured`, and marks the lead nurtured.
6. Buyer review actions record audited timeline events. Only approved outcomes write wallet adjustment ledger events.

All transition rows use deterministic idempotency keys so Hatchet retries do not duplicate audit rows.

Delivery rows also carry `post_results.delivery_idempotency_key` so a retried auction cannot double-write the same buyer delivery for the same lead and bid.

## V1 Technical Controls

The local V1 paid-pilot readiness slice adds these source-of-truth controls:

1. Buyer review rows store operator review state before any wallet adjustment is issued.
2. `GET /v1/buyers/{buyer_id}/daily-report` reports daily delivery, buyer reviews, wallet state, and refill recommendation from real DB rows.
3. `GET /v1/admin/launch-readiness` is scoped by `market_state`, `market_zip`, `service`, and `campaign_budget_cents`.
4. Caddy and dev compose are local-first: ports bind to `127.0.0.1`, unimplemented public routes fail closed, and only implemented form/admin surfaces are proxied.

See `docs/research/v1-paid-pilot-runbook.md` for the operating procedure.

## Replay / Recovery

Replay is dry-run by default:

```powershell
DATABASE_URL="$env:DATABASE_URL_HOST" uv run python scripts/replay_lead.py --lead-id <uuid>
```

Replay from an explicit checkpoint:

```powershell
DATABASE_URL="$env:DATABASE_URL_HOST" uv run python scripts/replay_lead.py --lead-id <uuid> --from-state qualified
```

Execute replay:

```powershell
DATABASE_URL="$env:DATABASE_URL_HOST" uv run python scripts/replay_lead.py --lead-id <uuid> --from-state unsold --execute
```

Just recipes are available when `just` is installed:

```powershell
just replay-lead <uuid>
just replay-lead-from <uuid> qualified
just replay-lead-execute <uuid> unsold
```

Replay refuses terminal states (`sold`, `nurtured`) unless an operator chooses an earlier checkpoint.

## LiteLLM Runtime

All runtime model calls go through the LiteLLM OpenAI-compatible endpoint:

```text
${LITELLM_PROXY_URL}/v1/chat/completions
```

`agent-runtime` no longer imports direct provider SDKs. The LiteLLM static test rejects imports of `anthropic`, `claude_agent_sdk`, and `openai` in `agent_runtime` source.

## Observability / SLO Signals

Structured metrics are emitted through `stormlead_core.emit_metric` and can be searched in service logs by `metric.emitted`:

- `funnel.enriched`
- `funnel.qualified`
- `funnel.unsold`
- `funnel.sold`
- `funnel.nurtured`
- `qualification.latency_ms`
- `auction.win_rate`
- `unsold.recovery`
- `llm.cost_per_lead`

Each metric includes `correlation_id`; lead-scoped metrics include `lead_id`.

## Visual Admin Workflow

The admin UI now exposes the audited workflow without adding a separate frontend:

1. `GET /v1/admin/workflow-kpis` computes workflow KPI cards from `lead_state_transitions`, `ping_attempts`, and `post_results`.
2. `GET /v1/admin/workflow-runs/recent` groups recent audited lead runs by lead/workflow run.
3. `GET /v1/admin/leads/{lead_id}/timeline` renders redacted timeline events from append-only transition rows.
4. `POST /v1/admin/leads/{lead_id}/review` records `hold`, `review`, or `approve` operator actions as admin audit events.
5. Cowork/Playwright runs are headed/visible by default and write `testing/runs/<run_id>/evidence.json` with workflow metadata, subject IDs, assertions, observations, and artifact paths.

Payload summaries are shortened at the helper/API/UI boundary. Raw payloads and query-string URLs are not rendered in the timeline.

Hatchet remains the workflow engine for this milestone. n8n is deferred to non-critical operator automations; Temporal is deferred until workflow scale or replay complexity justifies a migration.

## Validation Snapshot

Passed in this workspace:

```powershell
uv sync --all-packages
docker compose --env-file .env.example -f infra/compose/dev/docker-compose.yml config --quiet
$env:DATABASE_URL="postgresql+psycopg://stormlead:change-me-in-openbao@localhost:5433/stormlead"
uv run python scripts/init_db.py
Push-Location libs/stormlead_db; uv run alembic upgrade head; Pop-Location
uv run ruff check services libs scripts/smoke_e2e.py scripts/replay_lead.py
uv run ruff format --check services libs scripts/smoke_e2e.py scripts/replay_lead.py
uv run pytest -q services libs
uv run mypy services libs
uv run python scripts/smoke_e2e.py
npm run test:playwright -- --project=chromium --reporter=line
npm run cowork:admin:record
```

Playwright note: browser proof is visible by default. `playwright.config.ts` sets `headless: false`, npm scripts add `--headed --workers=1`, and `npm run test:playwright:ui` / `npm run test:playwright:debug` are available for UI Mode or Inspector review.

Latest results:

```
docker compose --env-file .env.example -f infra/compose/dev/docker-compose.yml config --quiet: passed
scripts/init_db.py + alembic upgrade head: passed through 0006_v1_paid_pilot_controls
uv run ruff check services libs scripts/smoke_e2e.py scripts/replay_lead.py: passed
uv run ruff format --check services libs scripts/smoke_e2e.py scripts/replay_lead.py: passed
uv run pytest -q services libs: 67 passed, 50 warnings
uv run mypy services libs: success, 51 source files
npm run test:playwright -- --project=chromium --reporter=line: 1 passed, headed
npm run cowork:admin:record: passed and wrote evidence.json
```

Smoke note: `uv run python scripts/smoke_e2e.py` currently reaches `form-receiver` but returns `503 event emission failed; will retry` because the running local Hatchet engine rejects the configured dev token with `StatusCode.UNAUTHENTICATED: invalid auth token`. Static code, DB migration, API readiness, and headed browser admin evidence pass; full ingest-to-auction smoke remains blocked on valid local Hatchet auth and live worker registration.

Mypy note: the project configuration type-checks source files while ignoring untyped Hatchet decorator/worker entrypoint modules and existing service tests. Runtime workflow functions and shared libraries remain checked.

`just` wrappers are still not validated on this machine if the `just` binary is absent. Use the fallback commands above or install `just` with `winget install Casey.Just`.
