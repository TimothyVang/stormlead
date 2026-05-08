# Browser Workflow Evidence Summary

This tracked summary records what the StormLead browser workflow proves without storing generated videos, traces, or timestamped screenshots in git.

## Current Workflow

- Target: `GET /admin` from the `ping-post` FastAPI app.
- Data mode: real API and database calls; no Playwright route mocks.
- Visibility mode: headed browser execution; StormLead does not use headless browser runs for operator evidence.
- Browser action: creates a buyer, activates/funds it, adds a deposit, then verifies KPI cards and the buyer roster.
- Admin workflow visibility: the dashboard includes real workflow KPI cards, recent audited workflow runs, lead timeline inspection, persisted review actions, and V1 buyer-review events when the smoke path is run.
- Cowork pattern: Request -> Analysis -> Plan -> Review/Approve -> Execute -> Verify.
- Evidence output: local ignored files under `testing/runs/`, `testing/playwright-artifacts/`, `testing/screenshots/`, `testing/videos/`, and `testing/logs/`; each Cowork run includes `evidence.json`.

## Verification Commands

- `npm run check:build-status` writes a timeout-resume status report under `testing/runs/free-build-current/` and reports the next safe command.
- `npm run validate:local`
- `npm run mcp:stormlead:check`
- `npm run mcp:stormlead:smoke`
- `npm run smoke`
- `npm run simulate:v1`
- `npm run test:playwright -- --project=api --reporter=line`
- `npm run test:playwright -- --project=chromium`
- `npm run test:chrome-observer`
- `npm run learn:loop:api`
- `uv run ruff check services libs scripts/smoke_e2e.py scripts/replay_lead.py`
- `uv run pytest -q services libs`
- `uv run python scripts/smoke_e2e.py`
- `npm run test:playwright -- --project=chromium --reporter=line`
- `npm run test:playwright:ui` for visible time-travel/debug review when needed
- `npm run cowork:admin:record`

## Resume After Timeout

Run `npm run check:build-status` first. If it reports `blocked`, follow `next_command`. If it reports `resume_needed`, continue from `resume_phase`. If it reports `ready`, the next evidence step is `npm run learn:loop:api` or a PR/review handoff.

## Latest Verification Snapshot

2026-05-08 local Windows/OpenCode verification passed with local-only synthetic data:

- `npm ci --ignore-scripts`: 289 packages installed, 0 vulnerabilities.
- `uv sync --all-packages`: Python workspace dependencies resolved and synced.
- `npm run validate:compose`: dev and full Docker Compose configs valid.
- `npm run mcp:stormlead:smoke`: StormLead Local Ops MCP smoke passed with 14 tools.
- `npm run lint:python`: Ruff passed.
- `npm run typecheck:python`: mypy passed for 74 source files.
- `npm run test:python`: 104 passed, 2 skipped.
- `npm run check:build-status`: status `ready`, no blockers or warnings; current state written to `testing/runs/free-build-current/state.json`.
- Local service probe: ping-post health/ready, form-receiver health, and LiteLLM readiness all passed.
- `scripts/smoke_e2e.py` via StormLead Local Ops MCP: PASS in 1285ms; verified synthetic form webhook, call tracking webhook, buyer ping/post, return review, buyer daily report, admin timeline, and scoped launch readiness.
- `scripts/simulate_v1_leads.py` via StormLead Local Ops MCP: PASS; covered qualified sold, returned approved, unsold, rejected, duplicate capture, suppressed opt-out, and nurture scenarios; evidence manifest `testing/runs/20260508T210842Z-c15611fd/v1-simulation-evidence.json`.
- `npm run test:playwright -- --project=chromium --reporter=line`: 32 passed; generated headed browser evidence under `testing/runs/2026-05-08T21-09-13-058Z-paid-pilot-admin-review/`, `testing/runs/2026-05-08T21-09-46-932Z-role-experience-agentic-workflow/`, and `testing/runs/2026-05-08T21-10-14-084Z-operator-review/`.

Follow-up cleanup and evidence from the same session:

- `pyproject.toml` moved pytest cache output to ignored `testing/.pytest_cache`, which removes the local `.pytest_cache` access-denied warning.
- `stormlead_core.models` now uses timezone-aware UTC defaults for lead and buyer timestamps.
- `ping_post.api` no longer emits the Hatchet `debug` or string-duration deprecation warnings during test imports.
- `npm run test:python`: 104 passed, 2 skipped, with no warnings in the test output.
- `npm run learn:loop:api`: passed; wrote `testing/runs/2026-05-08T21-15-38-295Z-self-learning-loop/self-learning-summary.json`, ran Playwright API proof with 26 passed, captured Chrome observer evidence, and reported Lighthouse navigation performance `0.89` with accessibility, best-practices, and SEO at `1.0`.
- `scripts/seed_dev.py` now gives fixed local smoke buyers enough monthly budget for repeated synthetic runs; after reseeding, `scripts/smoke_e2e.py` via StormLead Local Ops MCP passed again in 1962ms with buyer-a ping/post, return review, buyer daily report, admin timeline, and scoped launch readiness.

## Sharing Evidence

Generated videos and traces are ignored by git. To share evidence, prefer a short written summary here, a small curated screenshot, or external artifact storage. Use Git LFS if browser videos must be versioned.
