# Current Milestone Validation

Date: 2026-05-04

## Lifecycle

StormLead now uses the audited lifecycle below for production workflow routing:

1. `form-receiver` inserts a new lead and records `start -> captured` with `event_type=lead.captured`.
2. `enrich-worker` handles `lead.captured`, makes a real HTTP fetch attempt against `LeadRow.page_url`, persists deterministic evidence in `lead_state_transitions.payload_json`, updates deterministic enrichment fields, records `captured -> enriched`, and emits `lead.enriched`.
3. `agent-runtime` handles `lead.enriched`, routes model calls through LiteLLM, persists qualification fields, records `enriched -> qualified` or `enriched -> rejected`, and emits `lead.qualified` or `lead.rejected`.
4. `ping-post` handles `lead.qualified`, runs buyer ping/post, records `qualified -> auctioned`, records `auctioned -> sold` or `auctioned -> unsold`, and emits `lead.unsold` on unsold outcomes.
5. `agent-runtime` handles `lead.unsold` and `lead.rejected`, records `unsold/rejected -> nurtured`, and marks the lead nurtured.

All transition rows use deterministic idempotency keys so Hatchet retries do not duplicate audit rows.

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

## LiteLLM Policy

All runtime model calls go through the LiteLLM OpenAI-compatible endpoint:

```text
${LITELLM_PROXY_URL}/v1/chat/completions
```

`agent-runtime` no longer imports direct provider SDKs. `services/agent-runtime/tests/test_litellm_policy.py` statically rejects imports of `anthropic`, `claude_agent_sdk`, and `openai` in `agent_runtime` source.

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

## Validation Snapshot

Passed in this workspace:

```powershell
uv sync --all-packages
uv run ruff check services libs scripts/replay_lead.py
uv run ruff format --check services libs scripts/replay_lead.py
uv run pytest -q services libs
uv run mypy services libs
```

Latest results:

```
60 passed, 48 warnings
Success: no issues found in 50 source files
```

Mypy note: the project configuration type-checks source files while ignoring untyped Hatchet decorator/worker entrypoint modules and existing service tests. Runtime workflow functions and shared libraries remain checked.

`just` wrappers are still not validated on this machine if the `just` binary is absent. Use the fallback commands above or install `just` with `winget install Casey.Just`.
