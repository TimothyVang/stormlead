# Agent-04: Agent-Runtime Nurture Outreach Execution Prompt

Date: 2026-05-04

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-04 — Agent-Runtime Nurture Outreach`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-04 — Agent-Runtime Nurture Outreach` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

Current implemented base includes:

- `services/agent-runtime/nurture.py` has `nurture_lead()` workflow function that marks the lead `NURTURED` but does NOT send any outreach
- `LeadRow` has: `name`, `phone_e164`, `email`, `city`, `state`, `damage_description`, `requested_service`
- `record_transition()` helper exists in agent-runtime for persisting state transitions
- `emit_metric()` and `emit_event()` helpers are used throughout the service
- `get_session()` is the async DB session context manager from `stormlead_db.engine`

Current stack constraints:

- Python-first.
- FastAPI.
- Postgres.
- LiteLLM only for model calls — nurture outreach uses HTTP webhook, NOT an LLM call.
- No direct SMS/email provider SDK imports.
- No real homeowner contact during local simulation (webhook URL defaults to empty string).
- Docker Compose for dev and prod.
- No TODO stubs shipped as complete.

Known repo learnings and memory inputs:

- The outreach webhook is POST-based: send JSON payload to `NURTURE_WEBHOOK_URL` env var
- When `NURTURE_WEBHOOK_URL` is empty, log a warning and return `{"sent": False, "reason": "NURTURE_WEBHOOK_URL not set"}` — do not raise
- Lead transitions must go through `record_transition()` to ensure audit trail
- `LeadStatus.NURTURED` is the destination state
- Pattern: use `httpx.AsyncClient(timeout=15.0)` for outgoing webhook calls (same as ping-post)

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Replace the stub in `services/agent-runtime/nurture.py` with a real HTTP POST to `NURTURE_WEBHOOK_URL`, persist the outreach result in the lead transition payload, and add `NURTURE_WEBHOOK_URL` to `.env.example`.

Out of scope:

- Direct SMS or email provider API integration (webhook abstraction only)
- Lead data changes or new DB columns
- Template rendering for outreach messages (plain JSON payload)
- Changes to any other agent-runtime files (qualify.py, hermes.py, etc.)

Milestone-safe examples:

- Webhook env var: `NURTURE_WEBHOOK_URL=http://localhost:9998/nurture  # POST target for SMS/email outreach`
- Graceful HTTP error: `except httpx.HTTPStatusError as exc: return {"sent": False, "reason": f"http_{exc.response.status_code}"}`
- Audit field: pass `{"outreach": outreach_result}` as the `payload` arg to `record_transition()`

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Call `nurture_lead(context)` with `NURTURE_WEBHOOK_URL=""` and receive `{"sent": False, "reason": "NURTURE_WEBHOOK_URL not set"}`
- Call `nurture_lead(context)` with a mock webhook URL and see an HTTP POST attempt
- Verify that `record_transition()` is still called and lead status is set to `NURTURED`
- Pass all existing nurture tests: `uv run pytest services/agent-runtime/tests/test_nurture.py -v`

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

- NEVER call real SMS/email/phone services — the webhook URL is the only integration point
- The outreach result dict `{"sent": bool, ...}` must be stored in `record_transition()` payload for audit
- Handle all three error cases: empty URL, HTTP status error, unexpected exception
- Truncate `damage_description` to 500 chars in the webhook payload to avoid oversized POSTs
- `.env.example` must be updated with the new env var and a comment

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `services/agent-runtime/nurture.py` — document the current stub, `LeadStatus` import, `record_transition` call signature
2. Read `services/agent-runtime/tests/test_nurture.py` — understand existing test structure and mocking patterns
3. Read `services/agent-runtime/qualify.py` — understand `httpx` usage pattern (if any) and `LeadRow` field names
4. Read `.env.example` — identify where to add the new env var
5. Read `services/agent-runtime/pyproject.toml` — confirm `httpx` is already a dependency

## Suggested Implementation Order

Build these in order after discovery:

1. Add `_send_nurture_outreach(lead: LeadRow) -> dict` private function to `nurture.py`
2. Wire `_send_nurture_outreach` into `nurture_lead()`, replacing the stub
3. Update `.env.example` with `NURTURE_WEBHOOK_URL` entry
4. Run existing tests: `uv run pytest services/agent-runtime/tests/test_nurture.py -v`
5. Verify no regressions in other agent-runtime tests
6. Docs/runbooks/readiness checklist.
7. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `nurture.py` has `_send_nurture_outreach()` that POSTs JSON to `NURTURE_WEBHOOK_URL`
2. Empty `NURTURE_WEBHOOK_URL` returns `{"sent": False, "reason": "NURTURE_WEBHOOK_URL not set"}` without raising
3. HTTP errors are caught and returned as `{"sent": False, "reason": "http_{status_code}"}`
4. `record_transition()` receives `payload={"outreach": outreach_result}` for audit trail
5. `.env.example` includes `NURTURE_WEBHOOK_URL` with comment
6. `uv run pytest services/agent-runtime/tests/test_nurture.py -v` exits 0 with all PASS
7. No secrets or `.env` files are staged.
8. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `services/agent-runtime/nurture.py`
- `services/agent-runtime/tests/test_nurture.py`
- `services/agent-runtime/qualify.py`
- `.env.example`

## Likely Changed Files

- `services/agent-runtime/nurture.py` (replace stub with real outreach)
- `.env.example` (add NURTURE_WEBHOOK_URL)

## Validation Suite

Required validation:

- `uv run pytest services/agent-runtime/tests/test_nurture.py -v`
- `uv run ruff check services/agent-runtime/`
- `git diff --check`
