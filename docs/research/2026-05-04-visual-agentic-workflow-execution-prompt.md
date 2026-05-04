# Visual Agentic Workflow Execution Prompt

Date: 2026-05-04

Use this prompt in a coding agent session to build StormLead's visual agentic workflow visibility milestone to completion.

## Copy/Paste Prompt

You are a senior staff engineer building the next StormLead milestone: **visual agentic workflow visibility for lead generation + lead sales**.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

Context:

StormLead is a real, self-hosted AI lead-gen platform. Current lifecycle is already implemented and committed:

`captured -> enriched -> qualified/rejected -> auctioned -> sold/unsold -> nurtured`

Current stack constraints:

- Python-first
- FastAPI
- Postgres
- Alembic
- Hatchet
- LiteLLM only for model calls
- Playwright for real browser workflows
- No mocked production behavior
- No fake KPI/buyer/lead data outside explicit dev/test seed paths
- No TODO stubs shipped as complete
- Every agent/workflow decision must be persisted for audit
- Every task must include runnable code, tests, and docs updates

Goal:

Build StormLead's **visual agentic workflow system** to 100% for the current milestone.

Definition of “visual agentic workflow”:

Operators must be able to see, inspect, and replay each lead's lifecycle across:

- browser actions
- backend workflow state
- agent decisions
- retries/failures
- business outcomes
- KPI/SLO impact

Do not claim 100% complete unless all implementation, docs, tests, and validation below are done.

Start by inspecting:

1. `git status --short --branch`
2. `git diff`
3. `docs/research/2026-05-04-build-execution-prompt.md`
4. `docs/research/current-milestone-validation.md`
5. existing admin UI in `services/ping-post/src/ping_post/api.py`
6. existing Playwright/Cowork files under `tests/playwright`
7. existing transition audit code in `libs/stormlead_db/src/stormlead_db/transitions.py`
8. existing observability code in `libs/stormlead_core/src/stormlead_core/observability.py`

Do not revert or overwrite user/other-agent changes.

Important product target:

Playwright is for browser-level execution and demo artifacts. It is not the whole workflow UI. Build the milestone as:

1. Playwright trace artifacts for UI actions.
2. Workflow/run timeline in StormLead admin UI.
3. Agent decision/audit timeline from Postgres transition rows.
4. KPI/SLO dashboard endpoints/cards for commercial visibility.
5. Optional orchestration adapter hooks for future n8n/Temporal, but do not migrate off Hatchet in this milestone unless necessary.

## Task 1: Lead Run Identity And Timeline Model

Goal:

Every lead run must have a consistent run/correlation identity across services, transitions, agent decisions, Playwright artifacts, and admin views.

Implement:

- Add or standardize `workflow_run_id` / `correlation_id` propagation across:
  - form capture
  - enrich-worker
  - agent-runtime qualification
  - ping-post auction
  - nurture
  - replay tooling
- Add DB-backed timeline query helpers that return ordered events for one lead:
  - transition audit rows
  - task name
  - from/to state
  - status
  - payload summary
  - created_at
  - workflow_run_id
- Do not duplicate source of truth if `lead_state_transitions` already contains enough data.

Checklist:

- [ ] Existing transition rows include enough timeline metadata.
- [ ] Missing run IDs are generated deterministically or safely at workflow boundaries.
- [ ] Timeline helper is tested.
- [ ] Replay uses the same identifiers where possible.

Deliverables:

- DB/helper updates
- Tests
- Docs

## Task 2: Admin Run Timeline UI

Goal:

Add a browser-visible operator page showing each lead's workflow timeline.

Implement:

- Add an admin UI page/section in the existing FastAPI admin UI:
  - list recent leads/runs
  - click a lead to view timeline
  - show states: captured, enriched, qualified/rejected, auctioned, sold/unsold, nurtured
  - show task status, timestamps, retry/idempotency metadata
  - show payload summaries without leaking raw PII unnecessarily
- Add API endpoint(s), for example:
  - `GET /admin/leads/{lead_id}/timeline`
  - or equivalent existing admin pattern
- Keep styling consistent with existing admin UI.
- Make it usable on desktop and mobile.

Checklist:

- [ ] Operator can open admin UI and inspect a lead timeline.
- [ ] Timeline is DB-backed, not hardcoded.
- [ ] Empty/error states are clear.
- [ ] PII is not overexposed.

Deliverables:

- FastAPI/admin UI changes
- Tests
- Docs/screenshots if Playwright can generate them

## Task 3: Playwright Evidence Linking

Goal:

Playwright browser actions should create trace/video/screenshot evidence and link that evidence to a lead run when applicable.

Implement:

- Extend existing Cowork/Playwright harness to record:
  - run ID
  - lead ID when known
  - artifact paths for trace/video/screenshot
  - workflow name
  - status
- Persist artifact metadata to a DB table or existing audit payload if sufficient.
- Keep generated artifacts ignored by git.
- Add admin timeline links to artifact metadata when present.
- Do not fake browser actions. Use the real app/admin UI/API/DB behavior.

Checklist:

- [ ] Playwright artifacts are generated in ignored `testing/` paths.
- [ ] Artifact metadata is queryable by lead/run.
- [ ] Admin timeline displays artifact links when present.
- [ ] Tests do not depend on local absolute paths.

Deliverables:

- Playwright harness update
- Artifact metadata persistence/query
- Admin UI link display
- Tests/docs

## Task 4: Agent Decision Trace Visibility

Goal:

Operators must see why the AI made a decision.

Implement:

- Ensure qualification/enrichment/nurture decisions persist structured reason data:
  - model route
  - score/confidence
  - reason codes
  - input feature summary
  - cost/latency metadata
  - LiteLLM trace correlation if available
- Add timeline rendering for decision payloads.
- Ensure all LLM calls still go through LiteLLM only.
- Add tests/static guard if needed.

Checklist:

- [ ] Direct provider SDK imports remain blocked.
- [ ] Decision payload is structured and redacted.
- [ ] Cost/latency/model metadata appears in timeline.
- [ ] Failed model calls are visible as failed/dead-letter events.

Deliverables:

- Agent runtime updates
- Timeline/API rendering
- Tests/docs

## Task 5: KPI/SLO Dashboard For Commercial Visibility

Goal:

Add an ops dashboard view that shows whether the automation is commercially working.

Implement:

- Add DB-backed KPI endpoint(s)/admin cards for:
  - lead throughput
  - enrichment success rate
  - qualification latency
  - qualification acceptance/rejection rate
  - auction win rate
  - buyer acceptance rate
  - sold/unsold rate
  - nurture recovery rate
  - estimated cost per lead
  - error/retry/dead-letter counts
- Prefer existing admin dashboard patterns.
- Do not use fake numbers. If no data exists, show zero/empty states clearly.

Checklist:

- [ ] KPIs are computed from real DB rows/events.
- [ ] Metrics match transition table/business tables.
- [ ] Low-data state is honest and readable.
- [ ] Tests cover KPI calculations.

Deliverables:

- Admin/API updates
- Tests
- Docs

## Task 6: Workflow Orchestration UI Decision And Adapter

Goal:

Prepare for visual orchestration without prematurely replacing Hatchet.

Implement:

- Create a short architecture doc deciding between n8n and Temporal for StormLead's next orchestration UI.
- Default recommendation should be pragmatic:
  - keep Hatchet for current durable execution
  - add n8n only for operator-friendly visual overlays/approvals if needed
  - consider Temporal only if Hatchet reliability/versioning becomes inadequate
- Add a small internal adapter/interface for emitting workflow events to external orchestration/observability sinks later, but keep current implementation backed by Hatchet/Postgres.
- Do not introduce n8n/Temporal containers unless the doc and implementation need them for this milestone.

Checklist:

- [ ] Decision doc exists.
- [ ] No unnecessary platform migration.
- [ ] Future n8n/Temporal integration path is clear.
- [ ] Current functionality remains self-hosted and working.

Deliverables:

- Docs
- Optional small adapter with tests

## Task 7: Human-In-The-Loop Review Hooks

Goal:

Low-confidence or risky leads should be reviewable visually.

Implement:

- Add review state/flag display in admin UI for:
  - low qualification confidence
  - enrichment failure
  - held for review
  - buyer dispute/return risk if existing data supports it
- Add operator action where feasible:
  - approve for auction
  - hold
  - mark reviewed
- Persist operator action as audit event/transition payload.
- Do not invent complex approval workflow if a minimal admin action is enough.

Checklist:

- [ ] Review-required leads are visible.
- [ ] Operator action is persisted.
- [ ] Audit trail shows who/what/when where available.
- [ ] Tests cover review action.

Deliverables:

- Admin/API updates
- Audit persistence
- Tests/docs

## Task 8: Docs And Runbook

Goal:

An operator should know how to use the visual workflow system.

Update docs:

- `docs/research/current-milestone-validation.md`
- add or update visual workflow docs/runbook
- update README if architecture changed

Document:

- how to open the admin timeline
- how to run Playwright/Cowork and view artifacts
- how to inspect a lead run
- how replay connects to timeline
- how to interpret KPIs
- how LiteLLM traces map to lead IDs
- known blockers or local setup caveats

Validation:

Run all required commands:

- `docker compose --env-file .env.example -f infra/compose/dev/docker-compose.yml config --quiet`
- `uv run ruff check services libs scripts/replay_lead.py`
- `uv run ruff format --check services libs scripts/replay_lead.py`
- `uv run pytest -q services libs`
- `uv run mypy services libs`
- Playwright/Cowork validation if frontend/admin UI changed:
  - `npm run test:playwright -- --project=chromium --reporter=line`
  - `npm run cowork:admin:record`
- If `just` is installed:
  - `just test`
  - `just smoke`
- If `just` is not installed:
  - document exact blocker and fallback commands run.

Global definition of done:

- [ ] Visual lead timeline works from admin UI.
- [ ] Timeline is backed by real DB audit data.
- [ ] Playwright artifacts are produced and linked to runs where applicable.
- [ ] Agent decision details are visible and redacted.
- [ ] Commercial KPI dashboard is real-data-backed.
- [ ] Replay/recovery links to timeline behavior.
- [ ] LiteLLM-only policy still enforced.
- [ ] No fake production behavior.
- [ ] Ruff passes.
- [ ] Format check passes.
- [ ] Pytest passes.
- [ ] Mypy passes.
- [ ] Compose config validates.
- [ ] Playwright/Cowork checks pass if touched.
- [ ] Docs are updated.
- [ ] Commit is created only after all feasible validation passes.
- [ ] Do not push unless explicitly asked.

Commit:

Only after the full definition of done passes, create one accurate commit, for example:

`feat(ops): add visual lead workflow timeline`

Final response format:

1. What changed
2. Proof/validation output
3. Remaining caveats, if any
4. Commit hash
5. Push status
