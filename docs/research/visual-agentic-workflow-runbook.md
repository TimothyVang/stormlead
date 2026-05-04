# Visual Agentic Workflow Runbook

Date: 2026-05-04

## Operator Surface

Open the local admin UI:

```powershell
$env:STORMLEAD_ADMIN_URL="http://127.0.0.1:8003"
npm run cowork:admin
```

The `/admin` page now shows:

- Buyer onboarding and wallet controls from the paid-pilot workflow.
- Agentic workflow KPI cards backed by Postgres audit tables.
- Recent lead workflow runs grouped from `lead_state_transitions`.
- A lead timeline viewer with shortened transition payload summaries.
- Review action buttons for `hold` and `approve`, persisted as admin audit events.

## Timeline Contract

Timeline data comes from real append-only rows in `lead_state_transitions`; the UI does not synthesize fake workflow steps.

API endpoints:

- `GET /v1/admin/workflow-kpis`
- `GET /v1/admin/workflow-runs/recent?limit=20`
- `GET /v1/admin/leads/{lead_id}/timeline`
- `POST /v1/admin/leads/{lead_id}/review`

Payload summaries are shortened before API/UI rendering. Raw payloads and query-string URLs are not rendered.

## Review Actions

Review actions are persisted with `task_name=admin.review_action` and `status=reviewed`.

- `hold` sets `LeadRow.hold_for_review=true`.
- `review` also sets `LeadRow.hold_for_review=true`.
- `approve` clears `LeadRow.hold_for_review`.

These actions are audit events, not fake lifecycle transitions. The latest real pipeline state remains visible in the timeline.

## KPI Interpretation

Workflow KPIs are computed from existing source-of-truth tables at request time:

- `lead_state_transitions` for lifecycle counts, qualification acceptance, enrichment, auction, sold, unsold, nurture, and transition status counts.
- `ping_attempts` for buyer acceptance rate.
- `post_results` for delivered lead and buyer review rates.

If a denominator does not exist yet, the API responds with `value=null` and a `reason` instead of manufacturing a rate.

## Evidence Artifacts

Cowork/Playwright runs write ignored evidence under `testing/runs/<run_id>/`:

- `plan.md`
- `evidence.json`
- `logs/cowork-log.md`
- `logs/assertions.json`
- `reviews/review.md`
- `screenshots/`

`evidence.json` records the workflow name, run ID, status, generated artifact paths, assertions, observations, and subject IDs such as `buyer_id` or `lead_id` when available.

Playwright operator/debug references:

- Visible execution: StormLead overrides Playwright's default headless mode. `npm run test:playwright` runs headed with one worker, while `npm run cowork:admin` launches a visible browser that stays open for review. https://playwright.dev/docs/running-tests
- UI Mode and Inspector: use `npm run test:playwright:ui` for timeline/DOM snapshot/network inspection, or `npm run test:playwright:debug` for step-by-step Inspector execution. https://playwright.dev/docs/test-ui-mode and https://playwright.dev/docs/debug
- Trace Viewer: open a trace with `npx playwright show-trace path/to/trace.zip`; use the action, console, and network panels to verify what the browser really did. https://playwright.dev/docs/trace-viewer
- HTML/JSON reports: the local config writes reports under `testing/playwright-report/` and `testing/logs/playwright-results.json`; open the HTML report with `npm run show:playwright-report`. https://playwright.dev/docs/test-reporters
- Locators: keep workflows resilient by using user-facing role, label, and text locators before CSS/XPath. https://playwright.dev/docs/locators
- Network observation: use response waits/events to prove real API calls happened. Do not use `page.route`/`context.route` to fake production API responses for milestone proof. https://playwright.dev/docs/network

StormLead-specific rule: Playwright artifacts are visible evidence, not source of truth. The source of truth remains Postgres audit tables and admin API responses; generated traces, videos, screenshots, and reports stay ignored unless explicitly curated for a tracked review.

## Workflow Engine Decision

Keep Hatchet for this milestone.

Reason:

- Current services already emit Hatchet events and write idempotent Postgres audit rows.
- The required visibility gap was timeline/KPI/review evidence, not workflow orchestration capability.
- Adding n8n would duplicate orchestration without strengthening the source-of-truth audit trail.
- Temporal remains a future option if workflows need stronger cross-language determinism or high-scale replay semantics, but it would require a larger migration than this milestone needs.

Decision path:

- Use Hatchet plus `lead_state_transitions` now.
- Revisit Temporal only after sustained workflow volume or replay complexity makes Hatchet the bottleneck.
- Revisit n8n only for operator-authored non-critical automations outside the paid lead lifecycle.

## Validation

Minimum validation after touching this surface:

```powershell
$env:DATABASE_URL="postgresql+psycopg://stormlead:change-me-in-openbao@localhost:5433/stormlead"
uv run python scripts/init_db.py
Push-Location libs/stormlead_db; uv run alembic upgrade head; Pop-Location
uv run ruff check services libs scripts/replay_lead.py
uv run ruff format --check services libs scripts/replay_lead.py
uv run pytest -q services libs
uv run mypy services libs
npm run test:playwright -- --project=chromium --reporter=line
npm run cowork:admin:record
```

If `just` is unavailable, use the direct commands above.
