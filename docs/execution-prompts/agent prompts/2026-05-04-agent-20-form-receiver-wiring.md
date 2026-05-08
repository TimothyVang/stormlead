# Agent-20: Form-Receiver Route Wiring & Compliance Integration Execution Prompt

Date: 2026-05-04

Wave: 3 — Run AFTER all Wave 2 agents are committed.

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-20 — Form-Receiver Route Wiring & Compliance Integration`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-20 — Form-Receiver Route Wiring & Compliance Integration` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

**Prerequisite:** All Wave 1 and Wave 2 agents are committed. `call_tracking.py` and `compliance.py` (Agent-07) exist.

Current implemented base includes:

- `services/form-receiver/api.py` has the Formbricks webhook endpoint (`POST /webhooks/formbricks`)
- `services/form-receiver/call_tracking.py` (Agent-07) has `CallTrackingEvent` and `ingest_call_event()`
- `services/form-receiver/compliance.py` (Agent-07) has `verify_trustedform_cert()`
- `services/form-receiver/schemas.py` has Pydantic models for form data
- `CallEventRow` exists in `stormlead_db/tables.py`

Current stack constraints:

- Python-first.
- FastAPI.
- Postgres.
- This is the final wiring step — no new business logic, only integration of existing modules.
- No TODO stubs shipped as complete.

Known repo learnings and memory inputs:

- Call tracking webhook: `POST /webhooks/call-tracking` receives `CallTrackingEvent` JSON
- TrustedForm integration: after the existing consent extraction in the Formbricks handler, call `verify_trustedform_cert()` if `trustedform_cert_url` is in the form data
- `get_session()` is already imported in `api.py` — use the same pattern
- Webhook security: call tracking webhooks should validate a shared secret (use `CALL_TRACKING_WEBHOOK_SECRET` env var) or accept all (simpler MVP — document choice)
- `schemas.py` needs `CallOutcome` enum if not already present

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Wire `POST /webhooks/call-tracking` endpoint into `api.py` using Agent-07's `ingest_call_event()`. Integrate TrustedForm cert verification into the existing Formbricks webhook handler. Add `CallOutcome` enum to `schemas.py` if missing.

Out of scope:

- New business logic in call tracking or compliance modules (those are complete from Agent-07)
- UI for call tracking data
- Real call tracking vendor webhook testing (use curl with synthetic payload)
- Changes to the call tracking or compliance module internals

Milestone-safe examples:

- Call tracking endpoint: `@app.post("/webhooks/call-tracking") async def call_tracking_webhook(event: CallTrackingEvent): async with get_session() as session: result = await ingest_call_event(event, session); return result`
- TrustedForm integration: after lead creation in Formbricks handler: `if extracted.trustedform_cert_url: tf_result = await verify_trustedform_cert(extracted.trustedform_cert_url); ...`
- `CallOutcome` enum: `class CallOutcome(str, Enum): answered = "answered"; voicemail = "voicemail"; no_answer = "no_answer"; busy = "busy"`

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- `POST /webhooks/call-tracking` with a synthetic `CallTrackingEvent` payload and receive a response with `call_id`
- Verify TrustedForm cert verification is called in the Formbricks handler when `trustedform_cert_url` is present
- Run `uv run pytest services/form-receiver/tests/ -v` and see ALL tests PASS
- `curl -X POST http://localhost:8002/webhooks/call-tracking -H "Content-Type: application/json" -d '{"call_id": "test-001", "phone_e164": "+13215550001", "duration_seconds": 60, "outcome": "answered", "tracked_at": "2026-05-04T12:00:00Z"}'` returns JSON

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

- Do NOT modify `call_tracking.py` or `compliance.py` — only wire them into `api.py`
- TrustedForm verification must be non-blocking: wrap in `asyncio.create_task()` or `await` with exception catch — Formbricks handler must not fail if TrustedForm is down
- `CallOutcome` enum should be in `schemas.py` if not already there
- Run existing form-receiver tests BEFORE and AFTER api.py changes to detect regressions
- Document whether the call tracking webhook validates a secret (MVP: no secret validation required, document as future work)

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `services/form-receiver/api.py` — find the Formbricks webhook handler, understand `get_session()` usage and `extracted` data structure
2. Read `services/form-receiver/call_tracking.py` — confirm `CallTrackingEvent` model and `ingest_call_event()` signature
3. Read `services/form-receiver/compliance.py` — confirm `verify_trustedform_cert()` signature and return type
4. Read `services/form-receiver/schemas.py` — check if `CallOutcome` enum already exists
5. Read `services/form-receiver/tests/` — understand existing test structure to avoid regressions

## Suggested Implementation Order

Build these in order after discovery:

1. Add `CallOutcome` enum to `schemas.py` if missing
2. Run existing tests: `uv run pytest services/form-receiver/tests/ -v` (establish baseline)
3. Add `POST /webhooks/call-tracking` endpoint to `api.py`
4. Integrate `verify_trustedform_cert()` into existing Formbricks handler in `api.py`
5. Run tests again: `uv run pytest services/form-receiver/tests/ -v` (must pass)
6. Test call tracking endpoint with curl
7. Docs/runbooks/readiness checklist.
8. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `POST /webhooks/call-tracking` endpoint exists in `api.py` and uses `ingest_call_event()`
2. Formbricks webhook handler calls `verify_trustedform_cert()` when `trustedform_cert_url` is present
3. TrustedForm verification failure does not cause the Formbricks handler to return an error
4. `CallOutcome` enum exists in `schemas.py`
5. `uv run pytest services/form-receiver/tests/ -v` exits 0 with ALL tests PASS
6. Curl test to `/webhooks/call-tracking` returns JSON with `call_id` field
7. No secrets or `.env` files are staged.
8. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `services/form-receiver/api.py`
- `services/form-receiver/call_tracking.py`
- `services/form-receiver/compliance.py`
- `services/form-receiver/schemas.py`
- `services/form-receiver/tests/` (list files)

## Likely Changed Files

- `services/form-receiver/api.py` (add call tracking endpoint, integrate TrustedForm)
- `services/form-receiver/schemas.py` (add CallOutcome enum if missing)

## Validation Suite

Required validation:

- `uv run pytest services/form-receiver/tests/ -v`
- `uv run ruff check services/form-receiver/`
- `curl -X POST http://localhost:8002/webhooks/call-tracking -H "Content-Type: application/json" -d '{"call_id":"test-001","phone_e164":"+13215550001","duration_seconds":60,"outcome":"answered","tracked_at":"2026-05-04T12:00:00Z"}'`
- `git diff --check`
