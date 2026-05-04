# Browser Workflow Evidence Summary

This tracked summary records what the StormLead browser workflow proves without storing generated videos, traces, or timestamped screenshots in git.

## Current Workflow

- Target: `GET /admin` from the `ping-post` FastAPI app.
- Data mode: real API and database calls; no Playwright route mocks.
- Browser action: creates a buyer, activates/funds it, adds a deposit, then verifies KPI cards and the buyer roster.
- Admin workflow visibility: the dashboard includes real workflow KPI cards, recent audited workflow runs, lead timeline inspection, and persisted review actions.
- Cowork pattern: Request -> Analysis -> Plan -> Review/Approve -> Execute -> Verify.
- Evidence output: local ignored files under `testing/runs/`, `testing/playwright-artifacts/`, `testing/screenshots/`, `testing/videos/`, and `testing/logs/`; each Cowork run includes `evidence.json`.

## Verification Commands

- `uv run ruff check services libs`
- `uv run pytest -q services libs`
- `npm run test:playwright -- --project=chromium --reporter=line`
- `npm run cowork:admin:record`

## Sharing Evidence

Generated videos and traces are ignored by git. To share evidence, prefer a short written summary here, a small curated screenshot, or external artifact storage. Use Git LFS if browser videos must be versioned.
