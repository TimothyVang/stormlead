# Agent-07: Call Tracking Webhook Ingestion Execution Prompt

Date: 2026-05-04

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-07 — Call Tracking Webhook Ingestion`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-07 — Call Tracking Webhook Ingestion` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

Current implemented base includes:

- `services/form-receiver/api.py` has the Formbricks webhook endpoint but no call tracking endpoint
- `LeadRow` in `stormlead_db/tables.py` has `trustedform_cert_url` column (Text, nullable)
- `TRUSTEDFORM_API_KEY` env var exists in `.env.example` (used for cert claim)
- `stormlead_db.engine` exports `get_session()` async context manager
- `stormlead_db.tables` uses SQLAlchemy 2.x ORM patterns with `Column`, `TIMESTAMP`, `UUID`, `ForeignKey`

Current stack constraints:

- Python-first.
- FastAPI.
- Postgres.
- Alembic for migrations (Wave 2 Agent-11 owns migration 0008; this agent adds `CallEventRow` to tables.py only — do NOT create a migration in Wave 1).
- No direct vendor SDK imports (call tracking via generic webhook).
- Docker Compose for dev and prod.
- No TODO stubs shipped as complete.

Known repo learnings and memory inputs:

- `CallEventRow` is a NEW table — Agent-07 adds the ORM class to `tables.py` but the migration that creates it is part of Wave 2 (or can be added to migration 0008)
- Call-to-lead matching: match by `phone_e164` (most recent lead with that phone number)
- Outcomes: `answered`, `voicemail`, `no_answer`, `busy`
- TrustedForm verify: POST to `cert_url` with `Authorization: Bearer TRUSTEDFORM_API_KEY` and `{"retain": True}`
- TrustedForm verify returns HTTP 201 on success; anything else is a soft failure (log and continue)

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Create `services/form-receiver/call_tracking.py` (event model + ingestion logic) and `services/form-receiver/compliance.py` (TrustedForm cert verification stub). Add `CallEventRow` ORM class to `libs/stormlead_db/tables.py`. The actual API endpoint wiring happens in Wave 3 Agent-20.

Out of scope:

- Wiring the call tracking endpoint into `api.py` (Agent-20, Wave 3)
- Creating the Alembic migration for `call_events` table (handled in migration 0008 or separately)
- Real call tracking vendor webhooks during testing
- RRWeb session capture (deferred)

Milestone-safe examples:

- Phone match query: `select(LeadRow).where(LeadRow.phone_e164 == event.phone_e164).order_by(LeadRow.created_at.desc()).limit(1)`
- TrustedForm claim: `POST cert_url` with `{"retain": True}` and Bearer auth — 201 = success
- `CallEventRow.lead_id` is nullable (call may arrive before lead is matched)

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Import `CallTrackingEvent` from `form_receiver.call_tracking`
- Import `ingest_call_event()` from `form_receiver.call_tracking`
- Import `verify_trustedform_cert()` from `form_receiver.compliance`
- Import `CallEventRow` from `stormlead_db.tables`
- Call `verify_trustedform_cert("", "")` and receive `None` without raising

100% completion contract:

- Report `100/100` only when implementation, docs, tests, validation, and required Browser Use evidence are complete.
- If the score is below 100, start the final response with `Not complete:` and list the missing points, blocker, and best fallback proof.

Execution mode:

- Finish this milestone in one continuous pass if technically possible.
- Do not stop after each task for approval unless required by `AGENTS.md` or the master prompt.
- Prefer the smallest correct vertical slice over broad scaffolding.
- Do not commit unless the user explicitly asks.

Timed work block mode:

- Default milestone timebox: `1` hour when the user explicitly chooses a timebox; otherwise continue until completion, validation, or a stop condition.

Milestone-specific rules:

- `CallEventRow` is added to `tables.py` but no migration is created in Wave 1 — the table will be created by migration 0008 or a subsequent migration
- `ingest_call_event()` must handle the case where no lead matches the phone number (set `lead_id=None`)
- `verify_trustedform_cert()` must return `None` if `TRUSTEDFORM_API_KEY` is empty or `cert_url` is empty
- All exceptions in compliance functions must be caught and return `None` (soft failure only)

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `services/form-receiver/api.py` — understand the existing endpoint structure and session injection pattern
2. Read `libs/stormlead_db/tables.py` — understand ORM class structure, imports, and `LeadRow.trustedform_cert_url` column
3. Read `services/form-receiver/schemas.py` — understand existing Pydantic schema patterns
4. Read `.env.example` — find `TRUSTEDFORM_API_KEY` entry and understand naming convention
5. Read any existing tests in `services/form-receiver/tests/` for mocking patterns

## Suggested Implementation Order

Build these in order after discovery:

1. Add `CallEventRow` ORM class to `libs/stormlead_db/tables.py`
2. Create `services/form-receiver/call_tracking.py` with `CallTrackingEvent` and `ingest_call_event()`
3. Create `services/form-receiver/compliance.py` with `verify_trustedform_cert()`
4. Run import smoke tests for all three new artifacts
5. Update `.env.example` with `TRUSTEDFORM_API_KEY` if not already present
6. Docs/runbooks/readiness checklist.
7. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `services/form-receiver/call_tracking.py` exists with `CallTrackingEvent` Pydantic model and `ingest_call_event(event, session) -> dict`
2. `services/form-receiver/compliance.py` exists with `verify_trustedform_cert(cert_url: str) -> dict | None`
3. `CallEventRow` ORM class exists in `libs/stormlead_db/tables.py` with correct column definitions
4. `CallEventRow.lead_id` is nullable ForeignKey to `leads.id`
5. Import smoke tests for all three pass
6. `verify_trustedform_cert("")` returns `None` without raising
7. No secrets or `.env` files are staged.
8. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `services/form-receiver/api.py`
- `libs/stormlead_db/tables.py`
- `services/form-receiver/schemas.py`
- `.env.example`

## Likely Changed Files

- `libs/stormlead_db/tables.py` (add CallEventRow)
- `services/form-receiver/call_tracking.py` (NEW)
- `services/form-receiver/compliance.py` (NEW)

## Validation Suite

Required validation:

- `uv run python -c "from form_receiver.call_tracking import CallTrackingEvent; print('ok')"`
- `uv run python -c "from form_receiver.compliance import verify_trustedform_cert; print('ok')"`
- `uv run python -c "from stormlead_db.tables import CallEventRow; print('ok')"`
- `uv run ruff check services/form-receiver/ libs/stormlead_db/`
- `git diff --check`
