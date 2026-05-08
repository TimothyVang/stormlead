# Agent-08: Campaign Attribution & ROI Tracking Execution Prompt

Date: 2026-05-04

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-08 — Campaign Attribution & ROI Tracking`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-08 — Campaign Attribution & ROI Tracking` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

Current implemented base includes:

- `LeadRow` has: `campaign_id`, `campaign_source`, `first_touch_source`, `last_touch_source`, `state`, `zip`, `requested_service`, `qualification_score`
- `BillingEventRow` has: `event_type` (`lead.posted`, `lead.returned`, `deposit.added`), `amount_cents`, `metadata_json` (JSONB), `buyer_id`
- `PostResultRow` has: `lead_id`, `buyer_id`, `status`
- `stormlead_db.engine` exports `get_session()` async context manager
- The ping-post `api.py` admin endpoints are the integration point (Agent-17 in Wave 3 wires them in)

Current stack constraints:

- Python-first.
- FastAPI.
- Postgres.
- SQLAlchemy 2.x with async session.
- No TODO stubs shipped as complete.
- No direct DB access from outside the service boundary.

Known repo learnings and memory inputs:

- `BillingEventRow.metadata_json` is a JSONB column; access campaign_id with `.astext` for text comparison
- `BillingEventRow.amount_cents` for `lead.returned` events is stored as negative (deducted from balance)
- The `get_roi_by_zip()` function queries across three tables — use raw SQL for clarity over complex ORM joins
- Max 50 zip codes returned per state query to prevent oversized responses
- Admin endpoints are wired in Wave 3 Agent-17 — this agent only creates the module functions

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Create `services/ping-post/attribution.py` with `get_campaign_roi(campaign_id: str) -> CampaignROI | None` and `get_roi_by_zip(state: str) -> list[dict]`. These will be imported and wired into API endpoints by Agent-17 in Wave 3.

Out of scope:

- API endpoint creation (Agent-17, Wave 3)
- Campaign budget tracking (no budget table exists)
- Multi-touch attribution modeling (use first/last touch only)
- Changes to any existing ping-post files

Milestone-safe examples:

- JSONB text comparison: `BillingEventRow.metadata_json["campaign_id"].astext == campaign_id`
- Raw SQL for zip ROI: use SQLAlchemy `text()` with named params `:state`
- `CampaignROI` is a dataclass (not Pydantic) — no serialization needed in this module

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Import `get_campaign_roi` and `get_roi_by_zip` from `ping_post.attribution`
- Call `get_campaign_roi("nonexistent-id")` and receive `None` without raising
- Call `get_roi_by_zip("FL")` and receive a list (possibly empty) without raising
- Import `CampaignROI` dataclass from `ping_post.attribution`

100% completion contract:

- Report `100/100` only when implementation, docs, tests, validation, and required Browser Use evidence are complete.
- If the score is below 100, start the final response with `Not complete:` and list the missing points, blocker, and best fallback proof.

Execution mode:

- Finish this milestone in one continuous pass if technically possible.
- Do not stop after each task for approval unless required by `AGENTS.md` or the master prompt.
- Prefer the smallest correct vertical slice over broad scaffolding.
- Do not commit unless the user explicitly asks.

Timed work block mode:

- Default milestone timebox: `45` minutes when the user explicitly chooses a timebox; otherwise continue until completion, validation, or a stop condition.

Milestone-specific rules:

- `get_campaign_roi()` must return `None` (not raise) if no leads found for the campaign
- `get_roi_by_zip()` must limit results to 50 rows and never raise even if tables are empty
- Use `func.sum(...).abs()` for returned amounts to avoid sign confusion
- The `leads_sold` and `leads_returned` fields may remain 0 as TODO — label with a comment explaining which join is needed, but this is the one acceptable incomplete field

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `libs/stormlead_db/tables.py` — document `LeadRow`, `BillingEventRow`, `PostResultRow` column names and types exactly
2. Read `services/ping-post/api.py` — understand existing admin endpoint patterns and import structure
3. Read any existing `services/ping-post/attribution.py` (may not exist) and `test_auction.py` for patterns
4. Check `services/ping-post/pyproject.toml` for SQLAlchemy version and available imports
5. Read `services/ping-post/auction.py` — understand existing async session usage pattern

## Suggested Implementation Order

Build these in order after discovery:

1. Create `services/ping-post/attribution.py` with `CampaignROI` dataclass
2. Implement `get_campaign_roi(campaign_id: str) -> CampaignROI | None`
3. Implement `get_roi_by_zip(state: str) -> list[dict]`
4. Run import smoke test
5. Docs/runbooks/readiness checklist.
6. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `services/ping-post/attribution.py` exists with `CampaignROI` dataclass, `get_campaign_roi()`, and `get_roi_by_zip()`
2. `get_campaign_roi("nonexistent")` returns `None` without raising
3. `get_roi_by_zip("XX")` returns a list without raising
4. Import smoke test passes
5. No secrets or `.env` files are staged.
6. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `libs/stormlead_db/tables.py`
- `services/ping-post/api.py`
- `services/ping-post/auction.py`

## Likely Changed Files

- `services/ping-post/attribution.py` (NEW)

## Validation Suite

Required validation:

- `uv run python -c "from ping_post.attribution import get_campaign_roi, get_roi_by_zip; print('ok')"`
- `uv run ruff check services/ping-post/attribution.py`
- `git diff --check`
