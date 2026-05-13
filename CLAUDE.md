# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Python-first monorepo for a self-hosted B2B lead-gen business: detect storm events, capture homeowner leads, qualify with LLM agents, run a ping-post auction to a buyer roster, and dial unsold leads via voice AI.

Dev runs on Windows + WSL2 with Docker Compose. Prod targets Hetzner + Docker Compose under systemd.

## Commands

### Windows-native quickstart (primary on this machine)

The Windows path is PowerShell-driven via `scripts/bootstrap.ps1`. Prefer these over the WSL2 `just` path on Windows hosts.

```powershell
npm run setup:local      # one-shot bootstrap: deps, .env, compose up, migrate, seed, verify
npm run start:local      # restart the local pipeline stack (no install/migrate/verify)
npm run verify:local     # readiness doctor + synthetic smoke (use as the local readiness gate)
npm run doctor           # readiness status + next safe command, no smoke
npm run reset:demo       # re-seed fixed local demo buyers/leads
```

### Python (via uv workspace)

```bash
uv run pytest -x -q services libs          # run all tests
uv run pytest -x -q services/ping-post    # run one service's tests
uv run ruff check services libs scripts/smoke_e2e.py scripts/replay_lead.py scripts/simulate_v1_leads.py
uv run ruff format services libs           # format
uv run mypy services libs                  # type check
```

### Dev stack (via just)

```bash
just up           # lean stack: local APIs + required workflow infra
just up-pipeline  # add workflow workers + LiteLLM before smoke/simulation
just up-full      # every optional service, including observability and UIs
just down         # tear down
just nuke         # down -v (destroys volumes — dev only)
just logs ping-post  # tail one service
just migrate      # sqlalchemy create_all + alembic upgrade head (uses DATABASE_URL_HOST)
just seed         # seed dev data
just smoke        # e2e: ingest → auction → delivery → return review
just test         # pytest -x -q
just lint         # ruff + mypy
just fmt          # ruff format + fix
just psql         # psql into the local db
```

### npm scripts (validation and browser proof)

```bash
npm run validate:compose       # check docker-compose config parses
npm run validate:codex         # validate opencode.json + .codex/config.toml + MCP profiles
npm run lint:python            # ruff check
npm run typecheck:python       # mypy
npm run test:python            # pytest
npm run smoke                  # scripts/smoke_e2e.py
npm run simulate:v1            # scripts/simulate_v1_leads.py
npm run validate:local         # single pre-commit gate: compose + lint + typecheck + tests

# Playwright (headed, one worker)
npm run test:playwright -- --project=chromium --reporter=line
npm run test:playwright:ui     # Playwright UI Mode (time-travel inspection)
npm run test:playwright:debug  # Playwright Inspector with step controls

# Cowork demo (visible browser)
npm run cowork:admin           # stays open
npm run cowork:admin:record    # capture mode

# Evidence cleanup
npm run evidence:clean         # preview
npm run evidence:clean:apply   # remove ignored generated artifacts

# Codex CLI (repo-local install via npm)
npm run codex                  # interactive
npm run codex:readonly         # inspect only
npm run codex:exec -- "prompt" # non-interactive
npm run codex:review           # review uncommitted changes
npm run codex:app              # Codex Desktop / in-app browser

# StormLead MCP
npm run mcp:stormlead:check    # syntax check MCP server
npm run mcp:stormlead:smoke    # smoke MCP tools
```

### Lead replay

```bash
just replay-lead <LEAD_ID>
just replay-lead-from <LEAD_ID> <FROM_STATE>
just replay-lead-execute <LEAD_ID> <FROM_STATE>  # actually executes
```

### Migrations

```bash
just migrate-rev "description"   # autogenerate alembic revision
```

## Architecture

### Service layout

```
services/
  ping-post/        FastAPI auction engine — fans out parallel pings, picks buyer winner, posts, debits wallets, admin UI
  storm-watcher/    Tropycal/NWS/FEMA pollers, Hatchet cron
  enrich-worker/    Deterministic lead enrichment, emits lead.enriched event
  agent-runtime/    LiteLLM-routed qualify/nurture workers
  form-receiver/    Formbricks webhook ingestion, emits lead.captured event
  voice-bridge/     Local-safe follow-up preview contracts; no live carrier calls

libs/
  stormlead_core/   Shared Pydantic models, CEL evaluator wrapper
  stormlead_db/     SQLAlchemy models + Alembic migrations (Postgres schema)

apps/
  landing/          Local landing page + synthetic lead submit gate (port 8005)
  buyer-portal/     Buyer wallet, delivery report, return review UI (port 8004)
```

### Data flow

Webhook/storm poll → Hatchet workflow → enrich-worker → agent-runtime → ping-post auction → buyer delivery / nurture / return-review

### Key infrastructure components

- **Postgres** (timescaledb-ha): PostGIS + TimescaleDB + pgvector. UTC only. Host port 5433, in-container port 5432.
- **Hatchet**: durable workflow orchestration on Postgres. No NATS — Hatchet handles the event bus.
- **LiteLLM proxy**: all runtime LLM calls go through `${LITELLM_PROXY_URL}/v1/chat/completions`. Direct Anthropic/OpenAI SDK imports are banned in runtime services.
- **Langfuse**: LLM observability at `http://localhost:3001`.
- **Hatchet UI**: `http://localhost:8080`.
- **ping-post admin**: `http://127.0.0.1:8003/admin` (Playwright baseURL).
- **landing**: `http://127.0.0.1:8005`.
- **buyer-portal**: `http://127.0.0.1:8004`.
- **voice-bridge**: `http://127.0.0.1:8006/readyz` with Docker Compose profile `voice`.

### Python package structure

Each service is a uv workspace member with its own `pyproject.toml`. Source layout: `services/<name>/src/<pkg_name>/`. Tests live at `services/<name>/tests/`. The root `pyproject.toml` manages all dev dependencies and tool config (ruff, mypy, pytest).

### Playwright / Cowork evidence

Tests live in `tests/playwright/`. Workflow definitions in `tests/playwright/workflows/`. All generated artifacts (screenshots, videos, traces, runs) go under `testing/` which is git-ignored. `testing/evidence-summary.md` is the only tracked evidence file. Do not use `page.route`/`context.route` to mock production API behavior in V1 proof runs.

### Codex and OpenCode

Both agents read `AGENTS.md` first. OpenCode uses `opencode.json`; Codex uses `.codex/config.toml`. Both load the same three MCP servers: `stormlead` (custom local ops), `docker` (Docker MCP Toolkit), `kubernetes` (Kubernetes MCP Toolkit). MCP profiles live in `.docker/` and must be imported once with `docker mcp profile import`.

## Critical Constraints

1. **LiteLLM**: pinned to a known-good image SHA (versions 1.82.7/1.82.8 had a supply-chain attack). Never `pip install litellm`. Only the cosign-verified Docker image.
2. **No direct provider SDKs** in runtime services. Use LiteLLM proxy exclusively.
3. **Postgres MCP**: use `crystaldba/postgres-mcp-pro` (not Anthropic's archived/vulnerable reference server). Pin a specific tag, not `:latest`.
4. **Hetzner region**: deploy to Ashburn (us-east) or Hillsboro (us-west) only. Falkenstein/Helsinki adds 150–200ms RTT and breaks the `<5s` auction budget.
5. **Local-only by default**: agents must not contact real homeowners, buyers, ad platforms, payment processors, or public webhooks. Use synthetic leads and local services unless the user explicitly approves a real external action.
6. **No NATS / SeaweedFS / OpenBao in V1**: cut after architecture review. Hatchet handles durable workflows; add these only when a concrete need surfaces.
7. **No Rust**: Python everywhere. Rewrite ping-post hot path in Go only if sustained >500 leads/sec load proves it necessary.
8. **jambonz**: NOT in dev Docker Compose (SIP/RTP doesn't work in WSL2). `voice-bridge` only runs a local preview profile in dev; future provider/call integration must point at a real Linux carrier bridge after explicit approval.

## Operating Mode (for agents)

- Default target is local simulation and technical proofing, not commercial paid launch.
- Do not commit, push, amend, or run destructive Git commands unless the user explicitly asks.
- Keep evidence under `testing/` paths (git-ignored); do not commit generated artifacts.
- MCP tools are local/dev by default — Docker/Kubernetes actions are inspect-first.
- StormLead Local Ops MCP command tools (`run_v1_simulation`, `run_local_smoke`) require `confirm_synthetic_local=true`.

## Documentation Map

- `docs/research/README.md` — current implementation guide, next build sequence, and 40% IRR operating model
- `docs/research/2026-05-architectural-fit.md` — why Postgres + Hatchet + FastAPI + US-region
- `docs/research/visual-agentic-workflow-runbook.md` — admin workflow timeline, review actions, KPI semantics
- `docs/research/v1-paid-pilot-runbook.md` — V1 technical controls and scoped readiness
- `docs/research/2026-05-end-to-end-automation-roadmap.md` — prioritized engineering plan to end-to-end automated operation; gap list with file:line citations and timeline
- `docs/research/2026-05-stack-improvements.md` — active technical risk register and implementation corrections
- `docs/research/ui-tars-agent-tars-runbook.md` — optional local UI-TARS/Agent TARS coworker workflow
- `testing/README.md` — Playwright/Cowork evidence rules, artifact hygiene
- `tools/TOOLS.md` — tool routing and MCP safety rules
- `tools/mcp/README.md` — StormLead Local Ops MCP tool reference
- `.codex/README.md` — Codex CLI scripts and project-scoped MCP setup
- `AGENTS.md` — repo-local agent operating guide
