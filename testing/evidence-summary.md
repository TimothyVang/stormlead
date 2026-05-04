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

- `uv run ruff check services libs scripts/smoke_e2e.py scripts/replay_lead.py`
- `uv run pytest -q services libs`
- `uv run python scripts/smoke_e2e.py`
- `npm run test:playwright -- --project=chromium --reporter=line`
- `npm run test:playwright:ui` for visible time-travel/debug review when needed
- `npm run cowork:admin:record`

## Sharing Evidence

Generated videos and traces are ignored by git. To share evidence, prefer a short written summary here, a small curated screenshot, or external artifact storage. Use Git LFS if browser videos must be versioned.
