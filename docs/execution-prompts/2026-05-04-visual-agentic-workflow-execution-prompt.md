# Visual Agentic Workflow Execution Prompt

Date: 2026-05-04

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to build StormLead's visual agentic workflow visibility milestone to completion.

This prompt is intentionally strict. Its purpose is to prevent partial delivery by forcing parallel discovery, vertical-slice implementation, real validation, and a measurable definition of done.

## Copy/Paste Prompt

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

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
- Playwright for real, visible browser workflows
- No mocked production behavior
- No fake KPI/buyer/lead data outside explicit dev/test seed paths
- No TODO stubs shipped as complete
- Every agent/workflow decision must be persisted for audit
- Every task must include runnable code, tests, and docs updates

Goal:

Build StormLead's **visual agentic workflow system** to 100% for the current milestone.

Non-negotiable outcome:

At the end of the session, a reviewer must be able to open StormLead admin, select a real lead, and answer these questions from the UI and linked evidence without reading logs manually:

- What happened to this lead?
- Which workflow/task performed each step?
- Why did the agent qualify/reject/nurture it?
- Did browser automation touch this lead/run, and where are the artifacts?
- Did the lead sell, fail, or enter nurture?
- What retries/failures happened?
- What was the commercial impact across the funnel?

Definition of “visual agentic workflow”:

Operators must be able to see, inspect, and replay each lead's lifecycle across:

- browser actions
- backend workflow state
- agent decisions
- retries/failures
- business outcomes
- KPI/SLO impact

Do not claim 100% complete unless all implementation, docs, tests, and validation below are done.

Execution mode:

- Finish this milestone in one continuous pass if technically possible.
- Do not stop after each task for approval.
- Use parallel subagents immediately after the initial repo inspection to compress discovery and reduce missed integration points.
- The main agent owns final architecture decisions, code integration, validation, docs, and final response.
- Subagents may research and propose implementation details, but the main agent must verify all findings against the codebase before editing.
- If a subagent reports uncertainty, inspect the relevant files directly before deciding.
- Only ask the user for clarification if there is a real product ambiguity or destructive action risk.
- Keep the implementation minimal: prefer existing `lead_state_transitions`, existing FastAPI admin UI, existing Playwright/Cowork harness, and existing metrics/logging before adding new tables, services, or dependencies.
- A milestone is not done when the UI looks good; it is done only when the UI is backed by real database state, validated by tests, and documented.

One-pass operating rule:

Work like a mission controller. Use subagents for discovery and risk reduction, then centralize implementation decisions in the main agent. Do not split into “research now, implement later” unless blocked by missing credentials, broken local tooling that has no fallback, or an explicit user stop.

If your agent platform has a Task/subagent tool, launch all six subagents in one parallel batch. If it does not, perform the six research workstreams yourself before editing and label the findings with the same section names.

Do not use subagents to make commits. Do not let subagents independently edit overlapping files. The main agent integrates all code changes.

No-premature-stop contract:

- Do not produce a final answer while any global definition-of-done item is unchecked.
- Do not end with “next steps” for work that is required by this prompt. Do the work instead.
- Do not say “mostly done,” “foundation complete,” or “ready for follow-up” unless the completion score is below 100 and the final response starts with `Not complete:`.
- If you discover missing work during final review, return to implementation mode immediately and fix it before responding.
- If a validation command fails, fix the failure and rerun it. Do not summarize the failure as a caveat unless it is an external/local tool blocker with no available fallback.
- If tests pass but docs are missing, keep working.
- If docs are done but Playwright/admin verification is missing, keep working.
- If implementation, docs, or required verification are incomplete, keep working until they are complete.

Hard completion gate algorithm:

```text
while true:
  inspect git status and current todo/checklist
  run or verify all focused tests for completed slices
  run the full validation suite
  calculate the 100-point completion score
  if score == 100 and validation passed and docs are updated:
      produce final response
      stop
  if there is a true external blocker:
      document exact blocker, fallback proof, incomplete score, and ask/stop only if user action is required
      stop
  otherwise:
      implement the missing/failing item
      rerun affected tests
      continue loop
```

True external blockers are limited to:

- required credentials are missing and no local/dev path exists
- required binary/service is unavailable and no equivalent fallback can validate the behavior
- Docker/OS failure prevents running the app and cannot be fixed from the repo
- user approval is required for a destructive action, paid dependency, schema rewrite that risks data loss, or product decision explicitly outside this prompt

Everything else is an implementation problem to fix, not a reason to stop.

Start by inspecting:

1. `git status --short --branch`
2. `git diff`
3. `docs/execution-prompts/2026-05-04-build-execution-prompt.md`
4. `docs/research/current-milestone-validation.md`
5. existing admin UI in `services/ping-post/src/ping_post/api.py`
6. existing Playwright/Cowork files under `tests/playwright`
7. existing transition audit code in `libs/stormlead_db/src/stormlead_db/transitions.py`
8. existing observability code in `libs/stormlead_core/src/stormlead_core/observability.py`

Do not revert or overwrite user/other-agent changes.

Quality bar:

- Build vertical, working slices instead of broad scaffolding.
- Prefer readable boring code over clever abstractions.
- Keep new names and new tables to the minimum needed.
- Write tests against behavior, not implementation details.
- Shorten payloads at API/UI boundaries by default; only show full fields where the existing admin UI already does and the operator needs it.
- Treat generated Playwright evidence as local artifacts, not source files.
- Keep production runtime independent from Playwright test-only code.
- Browser evidence must be visible/headed for operator review. Do not replace a visible browser workflow with headless-only proof.

## Parallel Subagent Protocol

After the initial inspection, launch these subagents concurrently. Ask each subagent to return concise findings with file paths, recommended edits, risks, and test targets. Do not let subagents commit.

Required subagent output contract:

Each subagent must return exactly these sections:

1. Existing facts: files/functions/endpoints/tables found, with paths.
2. Minimal implementation: smallest set of edits that satisfies this workstream.
3. Tests to add/update: exact test files and assertions.
4. Risks/blockers: only real blockers, not speculative concerns.
5. Do-not-do list: changes that would overbuild or violate constraints.

The main agent must paste or summarize each subagent's findings into its own working notes before implementation. If any required section is missing, continue by directly inspecting the relevant files and fill the gap yourself.

Subagent dependency map:

- Subagent B must inform Tasks 1, 3, 4, 5, and 7 because DB/audit shape is the backbone.
- Subagent A depends on B's timeline shape but can independently research HTML/API patterns.
- Subagent C depends on B only if DB artifact persistence is necessary; otherwise it can use ignored evidence manifests.
- Subagent D depends on B for payload shape and must preserve the LiteLLM rule.
- Subagent E depends on A for dashboard placement and B for transition/KPI queries.
- Subagent F depends on all findings for docs, but can research validation and orchestration independently.

Main-agent synthesis requirements:

Before editing code, write a concise internal synthesis with:

- chosen data source for timeline
- whether a migration is needed
- selected artifact metadata strategy
- selected admin UI route(s)
- selected KPI source queries
- selected review action persistence strategy
- docs to update
- tests to add

If the synthesis says a migration is needed, justify why existing transition payloads are insufficient.

Subagent A: Admin UI + Timeline

Prompt:

```text
Research the existing StormLead admin UI and API patterns. Focus on `services/ping-post/src/ping_post/api.py`, existing admin HTML/forms, existing KPI endpoints, and DB access patterns. Return a minimal implementation plan for a lead/run timeline UI and API that uses real `lead_state_transitions` data, avoids overexposed payloads, and fits the current visual style. Include exact files/functions likely needing edits and tests to add. Do not modify files.
```

Subagent B: DB Timeline + Audit Data

Prompt:

```text
Research transition audit and DB helpers. Focus on `libs/stormlead_db/src/stormlead_db/transitions.py`, `tables.py`, migrations, tests, and how services write `workflow_run_id`, `payload_json`, and statuses. Return a minimal design for lead timeline query helpers, run identity propagation, Playwright artifact metadata storage if needed, and tests. Prefer existing tables if sufficient; recommend a new table only if necessary. Do not modify files.
```

Subagent C: Playwright/Cowork Evidence

Prompt:

```text
Research existing Playwright/Cowork workflows under `tests/playwright`, scripts, testing artifact conventions, `.gitignore`, and admin demo scripts. Return a concrete plan to attach run IDs, lead IDs, and artifact paths to workflow evidence without mocking production behavior. Include exact files/functions likely needing edits and validation commands. Do not modify files.
```

Subagent D: Agent Decision + LiteLLM Traceability

Prompt:

```text
Research `services/agent-runtime`, `services/enrich-worker`, LiteLLM static tests, and decision payloads written to transition audit. Return a minimal implementation plan to expose shortened decision reasons, score/confidence, model route, cost, latency, and failure/dead-letter events in the admin timeline while preserving the LiteLLM-only rule. Include test targets. Do not modify files.
```

Subagent E: KPI/SLO + Review Actions

Prompt:

```text
Research current KPI endpoints/cards, buyer/auction tables, transition audit rows, and review-related lead fields (`hold_for_review`, quality scores, rejection/unsold states). Return a minimal real-data-backed KPI/SLO dashboard plan and a minimal human-in-the-loop review action plan. Include exact DB queries/endpoints/tests likely needed. Do not modify files.
```

Subagent F: Docs + Validation + Orchestration Decision

Prompt:

```text
Research docs and validation expectations. Focus on `docs/research/current-milestone-validation.md`, README, this prompt, compose files, and current validation commands. Return a doc update plan, n8n vs Temporal decision recommendation, and final validation checklist. Do not modify files.
```

Ready-to-copy parallel launch instruction:

If your coding environment supports launching multiple subagents/tasks in one tool call, launch all six subagents above together. If it requires separate calls, issue them back-to-back before reading any results. Use descriptions like:

```text
Admin timeline research
DB audit research
Playwright evidence research
Agent decision research
KPI review research
Docs validation research
```

Each subagent should be told: research only, do not edit, do not commit, return the required five-section output contract.

Merge protocol:

- Wait for all subagents before making substantial edits unless a finding is clearly independent and low-risk.
- Build one integrated implementation plan from the subagent reports.
- Prefer the smallest correct implementation that satisfies the global definition of done.
- Avoid adding new infrastructure if the existing FastAPI admin UI, Postgres audit table, Hatchet events, and Playwright artifacts can satisfy the milestone.
- If two subagents conflict, inspect the files directly and choose the simpler production-safe path.
- Track work with a todo list and keep one active implementation task at a time after the parallel research phase.
- Run focused tests after each major slice, then the full validation suite at the end.
- Do not start a second architecture path in parallel. Pick one implementation path and complete it end-to-end.
- If a planned table/migration is avoidable by using existing transition payloads, avoid the migration.
- If a planned UI framework dependency is avoidable by extending the existing admin HTML, avoid the dependency.
- If Playwright artifact persistence would require production DB writes from test code, prefer a test-only evidence manifest under ignored `testing/` and link it through admin only when metadata is explicitly available.

Suggested implementation order after subagents return:

1. DB/timeline query helpers and run identity propagation.
2. Admin timeline API and HTML rendering.
3. Playwright evidence metadata and admin links.
4. Agent decision payload improvements and LiteLLM trace fields.
5. KPI/SLO calculations and review actions.
6. Docs/runbook and orchestration decision.
7. Full validation, commit, final report.

Single-pass completion loop:

Repeat this loop until the global definition of done passes:

1. Implement the smallest next vertical slice.
2. Run the narrowest relevant tests.
3. Fix failures immediately.
4. Update docs for the slice.
5. Move to the next slice only when the current slice works.
6. After all slices, run the full validation suite.
7. If full validation fails, fix and rerun the failed command plus any affected earlier commands.
8. Commit only after the full suite passes or a local tool blocker is documented with fallback proof.

Hard stop conditions:

- Stop and ask before destructive git operations, schema rewrites that would drop data, replacing Hatchet with another orchestrator, introducing a new paid/cloud dependency, or exposing raw payloads in UI/artifacts.
- Do not stop for routine test failures, typing errors, formatting failures, missing helper functions, or local code integration issues; fix them.

Failure recovery playbook:

- If DB migrations fail: inspect migration order, model metadata, and Alembic heads; fix migration/code mismatch and rerun migration/config validation.
- If Playwright fails because services are down: run the documented stack/bootstrap fallback, verify `/readyz`, then rerun Playwright.
- If Playwright fails because selectors changed: update selectors to match the real UI, not fake the route or bypass the browser.
- If Playwright cannot open a visible browser because the host has no display, document the display blocker and do not count a headless run as milestone browser evidence.
- If mypy fails in changed code: fix types. If it fails in unrelated legacy code, first verify it is genuinely unrelated, then decide whether the calibrated mypy config should be adjusted or the legacy error should be fixed.
- If tests need data: use existing seed/smoke tooling or create test fixtures in tests only. Do not add fake production dashboard values.
- If `just` is missing: record the exact `Get-Command just` or shell error, run equivalent `uv`/`docker compose` commands, and document the fallback.
- If a subagent returns an overbuilt plan: use the facts, reject the overbuild, and proceed with the minimal path.

Anti-overbuild constraints:

- Do not add n8n or Temporal containers in this milestone unless existing requirements cannot be met with Hatchet/Postgres/admin UI.
- Do not add React or a new frontend build system for the admin timeline.
- Do not add a second observability stack if existing structured logs, DB audit rows, and current admin endpoints can expose the needed data.
- Do not add fake demo data to make dashboard cards look populated.
- Do not create multiple partial commits.

Preferred architecture for this milestone:

- Source of truth: Postgres tables, especially `lead_state_transitions` plus existing lead/buyer/auction tables.
- Workflow execution: keep Hatchet.
- Operator UI: extend current FastAPI admin HTML.
- Browser evidence: keep Playwright artifacts under ignored `testing/` paths, with metadata in an audit payload or a small manifest unless production needs DB persistence.
- Decision visibility: render redacted transition payload summaries.
- KPI visibility: compute from DB at request time unless an existing metrics table already exists.
- Future orchestration UI: document n8n/Temporal tradeoffs; do not add runtime dependency now.

Concrete file map:

Expect most implementation to land in these areas. Inspect first, then keep edits as small as possible.

```text
DB/timeline helpers:
  libs/stormlead_db/src/stormlead_db/transitions.py
  libs/stormlead_db/tests/test_lead_state_transitions.py

Core redaction / shared types if needed:
  libs/stormlead_core/src/stormlead_core/observability.py
  libs/stormlead_core/src/stormlead_core/pipeline.py
  libs/stormlead_core/tests/

Admin timeline + KPI UI/API:
  services/ping-post/src/ping_post/api.py
  services/ping-post/tests/

Agent decision payloads:
  services/agent-runtime/src/agent_runtime/qualify.py
  services/agent-runtime/src/agent_runtime/nurture.py
  services/agent-runtime/tests/

Enrichment evidence payloads:
  services/enrich-worker/src/enrich_worker/enrich.py
  services/enrich-worker/tests/

Auction outcome/KPI source data:
  services/ping-post/src/ping_post/auction.py
  services/ping-post/tests/test_auction.py

Playwright/Cowork evidence:
  tests/playwright/helpers/cowork.ts
  tests/playwright/workflows/*.workflow.ts
  scripts/live_admin_cowork.mjs
  testing/README.md

Docs/runbooks:
  docs/research/current-milestone-validation.md
  docs/research/visual-agentic-workflow-runbook.md (create if useful)
  README.md
```

Concrete API and helper targets:

Prefer these names unless existing naming patterns strongly suggest better local names.

```text
DB helpers:
  list_lead_timeline(session, lead_id) -> list[LeadTimelineEvent]
  summarize_transition_payload(payload_json) -> dict[str, Any]
  list_recent_lead_runs(session, limit=50) -> list[LeadRunSummary]

Admin JSON endpoints:
  GET /v1/admin/leads/{lead_id}/timeline
  GET /v1/admin/workflow-runs/recent
  GET /v1/admin/workflow-kpis
  POST /v1/admin/leads/{lead_id}/review

Admin HTML routes/sections:
  /admin timeline card or link from existing lead table
  /admin/leads/{lead_id}/timeline if existing routing style supports it

Playwright evidence manifest:
  testing/runs/<run_id>/evidence.json
```

If the current admin UI avoids separate HTML routes, embed the timeline in the existing `/admin` page with query parameters such as `?lead_id=<uuid>` and document that choice.

Suggested typed structures:

Use dataclasses or Pydantic models only if they fit the surrounding code. Otherwise return plain typed dicts from helpers.

```python
@dataclass(frozen=True)
class LeadTimelineEvent:
    lead_id: UUID
    workflow_run_id: str | None
    event_type: str
    task_name: str | None
    from_state: str
    to_state: str
    status: str
    created_at: datetime
    payload_summary: dict[str, Any]
    artifact_links: list[dict[str, str]]


@dataclass(frozen=True)
class LeadRunSummary:
    lead_id: UUID
    workflow_run_id: str | None
    current_state: str | None
    last_event_type: str | None
    last_event_at: datetime | None
    needs_review: bool
```

Example payload summary allowlist:

```text
Allowed keys:
  source
  score
  qualification_score
  lead_class
  rejection_reason
  reason
  reason_code
  confidence
  model
  model_used
  fallback_used
  duration_ms
  estimated_cost_usd
  estimated_input_tokens
  estimated_output_tokens
  fetched
  status_code
  requested_service
  eligible_buyers
  buyer_id
  bid_cents
  post_status_code
  artifact_path
  trace_path
  screenshot_path
  video_path

Always shorten/drop keys containing:
  phone
  email
  address
  webhook_secret
  api_key
  token
  authorization
  prompt
  raw_payload
```

Example evidence manifest schema:

```json
{
  "run_id": "uuid-or-readable-id",
  "lead_id": "uuid-or-null",
  "workflow_name": "paid-pilot-admin-review",
  "status": "passed",
  "created_at": "iso8601",
  "artifacts": [
    {"type": "trace", "path": "testing/playwright-artifacts/.../trace.zip"},
    {"type": "screenshot", "path": "testing/screenshots/.../admin.png"},
    {"type": "video", "path": "testing/videos/.../run.webm"}
  ]
}
```

Artifact paths should be relative to the repo root when possible. Do not store absolute local user paths in committed docs or production DB rows.

Example KPI response shape:

```json
{
  "window_hours": 24,
  "lead_throughput": {"value": 12, "reason": null},
  "enrichment_success_rate": {"value": 0.92, "reason": null},
  "qualification_acceptance_rate": {"value": 0.67, "reason": null},
  "auction_win_rate": {"value": 0.41, "reason": null},
  "buyer_acceptance_rate": {"value": 0.35, "reason": null},
  "nurture_recovery_rate": {"value": null, "reason": "no nurtured transitions in window"},
  "estimated_cost_per_lead": {"value": 0.18, "reason": null},
  "error_count": {"value": 0, "reason": null}
}
```

Implementation shortcuts that are acceptable:

- If there is no durable artifact table yet, write Playwright evidence metadata to ignored `testing/runs/<run_id>/evidence.json` and render links only when a transition payload or query parameter references that manifest.
- If a KPI cannot be calculated from persisted data, return `null` with a reason instead of adding a new persistence path just for one metric.
- If operator identity/auth does not exist yet, use `local-admin` and document it as a dev/admin limitation.
- If timeline HTML testing is easier through the FastAPI test client than Playwright, use the test client for unit coverage and Playwright for the existing Cowork smoke/demo path.

Payload summary rules:

- Never render full contact fields, webhook secrets, API keys, auth tokens, or full model prompts in timeline payload summaries.
- It is acceptable to show city/state/zip, score, class, model route, latency, cost estimate, reason code, task name, workflow run ID, and artifact relative path.
- If a payload contains unknown keys, summarize only allowlisted keys and include a `redacted_keys` count.

Security checks:

- Do not expose webhook secrets, buyer webhook URLs with embedded tokens, LiteLLM keys, Hatchet tokens, Langfuse secrets, or `.env` contents in timeline UI.
- Do not add screenshots/videos/traces to git.
- Do not make admin endpoints public-facing or unauthenticated beyond the current local/dev assumptions without documenting the risk.
- If a route returns JSON for timeline or KPIs, keep it deterministic and safe for browser rendering.

Timeline event contract:

Each timeline event returned by backend helpers should expose this shape or a clearly equivalent typed structure:

```json
{
  "lead_id": "uuid",
  "workflow_run_id": "string-or-null",
  "event_type": "lead.qualified",
  "task_name": "agent_runtime.qualify_lead",
  "from_state": "enriched",
  "to_state": "qualified",
  "status": "succeeded",
  "created_at": "iso8601",
  "payload_summary": {},
  "artifact_links": []
}
```

KPI contract:

KPI endpoints/cards should return real values using simple, explainable calculations:

- lead throughput: count of captured transitions in window
- enrichment success rate: enriched transitions / captured transitions
- qualification latency: average `qualification.latency_ms` if persisted, otherwise derive only if reliable timestamps exist
- qualification acceptance rate: qualified transitions / enriched transitions
- auction win rate: sold transitions / auctioned transitions
- buyer acceptance rate: accepted ping attempts / total ping attempts
- sold/unsold rate: sold and unsold transitions / auctioned transitions
- nurture recovery rate: nurtured transitions / unsold + rejected transitions
- estimated cost per lead: average persisted model cost from decision payloads
- errors/retries/dead letters: transition rows by status where available

If a metric cannot be computed honestly from current persisted data, show `null` plus `reason`, not a fake value.

Completion scorecard:

Use this scorecard before claiming completion. The milestone is not complete below 100/100 unless the user explicitly accepts a documented blocker.

```text
10 pts: parallel subagent research completed and reconciled
10 pts: run/correlation identity and DB timeline helper implemented + tested
15 pts: admin timeline UI/API implemented + tested + redacted
10 pts: Playwright/Cowork evidence metadata linked or explicitly supported with manifest strategy + tested
10 pts: agent decision trace fields visible + LiteLLM-only guard still passing
15 pts: KPI/SLO dashboard/cards are real-data-backed + tested
10 pts: human review hooks/actions persist audit trail + tested
10 pts: docs/runbook/orchestration decision updated
10 pts: full validation suite passes or exact local-tool blocker has fallback proof
```

Report the score in the final response. If the score is below 100, say what is missing and do not call the milestone done.

Review action contract:

Review actions should be intentionally small:

- mark reviewed
- hold for review
- approve for auction, only if the current state and existing business rules allow it

Every operator action must write an audit event with:

- lead ID
- action
- previous value/state
- new value/state
- operator identifier if available, otherwise `local-admin`
- timestamp
- reason/comment if supplied

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

Acceptance tests:

- Given a lead with multiple `lead_state_transitions`, timeline helper returns rows ordered by `created_at`.
- Timeline output includes `lead_id`, `from_state`, `to_state`, `event_type`, `task_name`, `status`, `workflow_run_id`, sanitized payload summary, and `created_at`.
- Timeline helper handles leads with no transitions without throwing.

## Task 2: Admin Run Timeline UI

Goal:

Add a browser-visible operator page showing each lead's workflow timeline.

Implement:

- Add an admin UI page/section in the existing FastAPI admin UI:
  - list recent leads/runs
  - click a lead to view timeline
  - show states: captured, enriched, qualified/rejected, auctioned, sold/unsold, nurtured
  - show task status, timestamps, retry/idempotency metadata
  - show payload summaries without exposing raw payloads unnecessarily
- Add API endpoint(s), for example:
  - `GET /admin/leads/{lead_id}/timeline`
  - or equivalent existing admin pattern
- Keep styling consistent with existing admin UI.
- Make it usable on desktop and mobile.

Checklist:

- [ ] Operator can open admin UI and inspect a lead timeline.
- [ ] Timeline is DB-backed, not hardcoded.
- [ ] Empty/error states are clear.
- [ ] Raw payloads are not overexposed.

Deliverables:

- FastAPI/admin UI changes
- Tests
- Docs/screenshots if Playwright can generate them

Acceptance tests:

- Admin timeline endpoint returns real DB-backed transition data for a known lead.
- Admin HTML includes timeline state labels and does not render raw phone/email/address from transition payloads.
- Empty timeline page renders a useful empty state.

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

Acceptance tests:

- Cowork/Playwright run writes an evidence manifest or metadata record containing workflow name, run ID, status, and artifact paths.
- Generated artifacts remain under ignored `testing/` paths.
- Admin timeline shows evidence links only when metadata exists; missing metadata does not break the page.

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

Acceptance tests:

- Qualification timeline payload includes model name, latency, cost estimate, score/confidence, and redacted reasoning summary.
- Failed/dead-letter model execution is visible as a timeline event or structured audit payload.
- Static LiteLLM test still rejects direct provider SDK imports.

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

Acceptance tests:

- KPI calculations return zero/empty values for an empty DB instead of fake numbers.
- KPI calculations match fixture rows for sold/unsold, buyer acceptance, auction win rate, and nurture recovery.
- Admin dashboard renders KPI cards from the real endpoint.

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

Acceptance tests:

- Decision doc explicitly says whether n8n or Temporal is added now or deferred.
- If an adapter is added, tests prove current behavior remains backed by Hatchet/Postgres without requiring n8n/Temporal.

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

Acceptance tests:

- Review-required leads are queryable from real lead fields.
- Operator action persists an audit row or structured audit payload.
- Timeline displays the operator action after it is persisted.

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
- Markdown/config sanity if docs or config changed: `git diff --check`

Validation discipline:

- Run fast, focused tests during implementation, but the final proof must include the complete validation list above.
- If Playwright is touched, final proof must include both Playwright command output and the location of generated ignored evidence artifacts.
- If admin UI is touched, final proof must include at least one browser-level or HTTP-level check that the timeline/dashboard route loads.
- If DB helpers/migrations are touched, final proof must include unit tests and migration/config validation.
- If `uv run mypy services libs` fails, do not finalize until it is fixed unless the failure is outside the changed milestone and documented with exact evidence. Prefer fixing it.

Minimum focused test matrix:

Before the final full validation, add or update focused tests so these behaviors are covered:

```text
DB timeline helper:
  - ordered timeline for fixture transitions
  - empty timeline returns [] or empty response cleanly
  - payload summary shortens unknown keys

Admin/API:
  - timeline JSON endpoint returns real fixture data
  - timeline HTML route renders key states
  - KPI endpoint handles empty DB honestly
  - review action persists audit event

Agent/runtime:
  - decision payload includes model/cost/latency/score fields where available
  - LiteLLM direct-provider guard still passes

Playwright/Cowork:
  - evidence manifest/metadata contains run ID, workflow name, status, and artifact paths
  - generated artifact paths are relative or under ignored testing directory
```

If a test target is infeasible because the code path is integration-only, document why and cover the pure helper/API behavior instead.

Evidence requirements:

The final response must include evidence, not just claims:

- exact validation commands run and their pass/fail result
- new or changed endpoint paths
- new or changed admin routes/pages
- where Playwright evidence manifests/artifacts are written
- where docs/runbooks were updated
- commit hash if committed
- push status
- final completion score from the 100-point scorecard

Completion evidence table:

The final response must include a table like this, with real evidence filled in:

```text
Requirement | Status | Evidence
Parallel subagents launched | pass/fail | subagent summaries reconciled
Timeline helper | pass/fail | test file + command
Admin timeline UI/API | pass/fail | endpoint/route + test/browser proof
Playwright evidence linking | pass/fail | manifest/artifact path + command
Agent decision visibility | pass/fail | payload fields + test
KPI/SLO dashboard | pass/fail | endpoint + test
Review hooks | pass/fail | endpoint/action + audit proof
Docs/runbook | pass/fail | doc paths
Ruff | pass/fail | command output
Format check | pass/fail | command output
Pytest | pass/fail | command output
Mypy | pass/fail | command output
Compose config | pass/fail | command output
Playwright/Cowork | pass/fail | command output or documented not touched
Commit, if requested | pass/fail | commit hash or not requested
Completion score | pass/fail | 100/100 required
```

If any row is `fail`, the agent must not use a normal completion response. It must either continue working or start the final response with `Not complete:` if a true external blocker prevents completion.

If a command cannot run because a binary is missing, include:

- command attempted
- exact error
- fallback command used
- why fallback is equivalent enough for this milestone

Global definition of done:

- [ ] Parallel subagents were launched for admin UI, DB/audit, Playwright evidence, agent decisions, KPI/review, and docs/validation.
- [ ] Subagent findings were reconciled into one integrated implementation before final edits.
- [ ] Visual lead timeline works from admin UI.
- [ ] Timeline is backed by real DB audit data.
- [ ] Playwright artifacts are produced and linked to runs where applicable.
- [ ] Agent decision details are visible and redacted.
- [ ] Commercial KPI dashboard is real-data-backed.
- [ ] Replay/recovery links to timeline behavior.
- [ ] LiteLLM-only rule still enforced.
- [ ] No fake production behavior.
- [ ] Ruff passes.
- [ ] Format check passes.
- [ ] Pytest passes.
- [ ] Mypy passes.
- [ ] Compose config validates.
- [ ] Playwright/Cowork checks pass if touched.
- [ ] Docs are updated.
- [ ] No commit is created unless explicitly requested; if requested, it is created only after all feasible validation passes.
- [ ] Do not push unless explicitly asked.

Final self-review before handoff or requested commit:

- [ ] Search for `TODO`, `mock`, `fake`, and direct provider SDK imports in changed files; remove or explicitly justify test-only usage.
- [ ] Check `git diff --stat` and ensure the scope matches this milestone.
- [ ] Check generated artifacts are ignored and not staged.
- [ ] Verify docs describe exactly how an operator uses the feature.
- [ ] Verify no secrets or `.env` files are staged.

Reviewer demo script:

Before final response, prepare a short operator demo path in docs or final output:

1. Start the stack or use the documented fallback.
2. Open admin UI.
3. Navigate to the lead/run timeline.
4. Inspect one lead's timeline states.
5. Open linked Playwright evidence if present.
6. Inspect KPI cards.
7. Run replay dry-run for the same lead.

This does not need to create fake data. If no local lead exists, document how to seed or capture a real dev lead using existing seed/smoke tooling.

Commit:

Do not create a commit unless the user explicitly asks. If a commit is requested, create one accurate commit only after the full definition of done passes, for example:

`feat(ops): add visual lead workflow timeline`

Do not create partial commits. If one validation command cannot run because of a local tool blocker, document the exact blocker and run the closest equivalent command before any requested commit.

Final response format:

1. What changed
2. Proof/validation output
3. Remaining caveats, if any
4. Commit hash if a commit was requested and created
5. Push status
6. Completion score out of 100
7. Completion evidence table

If the completion score is not 100/100, the final response must start with `Not complete:` and explain exactly what remains.

Forbidden final-response patterns before 100/100:

- “This is ready for the next phase.”
- “The foundation is done.”
- “Most of the work is complete.”
- “Remaining work:” followed by required checklist items.
- “I could not run X” without exact blocker evidence and fallback validation.

If you are about to write one of those, stop writing the final answer and continue implementation instead.
