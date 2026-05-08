# Agent-13: Mailer CSV Export Execution Prompt

Date: 2026-05-04

Wave: 2 — Run AFTER all Wave 1 agents are committed and tested.

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-13 — Mailer CSV Export`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-13 — Mailer CSV Export` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

**Prerequisite:** Wave 1 is committed.

Current implemented base includes:

- `LeadRow` has: `name`, `address_line1`, `city`, `state`, `zip`, `requested_service`, `damage_description`, `status`, `id` (UUID)
- `stormlead_db.engine` exports `get_session()` async context manager
- `services/ping-post/api.py` has admin endpoints under `/v1/admin/` pattern
- Python stdlib `csv` and `io.StringIO` are available (no new dependencies)

Current stack constraints:

- Python-first.
- FastAPI.
- Postgres.
- Python stdlib `csv` module for CSV generation (no pandas, no external CSV libs).
- No direct homeowner contact — this is export for ops team use only.
- No TODO stubs shipped as complete.

Known repo learnings and memory inputs:

- Tracking code format: `TRACK-{lead_id[:8].upper()}` — ops team uses this when homeowner calls back
- CSV limit: 5000 rows per export to prevent memory issues
- `damage_description` should be truncated to 200 chars in CSV to prevent oversized files
- Admin endpoint wiring (`GET /v1/admin/export/mailer-csv`) is Agent-17's job (Wave 3); this agent creates the function only
- Lead `status` filter defaults to `"unsold"` — operators export unsold leads for direct mail outreach

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Create `services/ping-post/mailer.py` with `export_mailer_csv(state, service, status) -> str` that returns a CSV string of filtered leads with tracking codes. The admin endpoint is wired in Wave 3 Agent-17.

Out of scope:

- Admin API endpoint (Agent-17, Wave 3)
- QR code generation (tracking code string only for MVP)
- Sending or uploading the CSV to any external service
- Buyer-facing CSV export (admin-only)
- PII encryption in CSV (ops team handles this offline)

Milestone-safe examples:

- Tracking code: `f"TRACK-{str(lead.id)[:8].upper()}"`
- CSV header: `["tracking_code", "name", "address_line1", "city", "state", "zip", "requested_service", "damage_description"]`
- Status filter: `select(LeadRow).where(LeadRow.status == status)` (default `"unsold"`)

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Import `export_mailer_csv` from `ping_post.mailer`
- Call `await export_mailer_csv(None, None, "unsold")` and receive a CSV string with a header row
- Verify tracking codes use the `TRACK-{id[:8]}` format

100% completion contract:

- Report `100/100` only when implementation, docs, tests, validation, and required Browser Use evidence are complete.
- If the score is below 100, start the final response with `Not complete:` and list the missing points, blocker, and best fallback proof.

Execution mode:

- Finish this milestone in one continuous pass if technically possible.
- Do not stop after each task for approval unless required by `AGENTS.md` or the master prompt.
- Prefer the smallest correct vertical slice over broad scaffolding.
- Do not commit unless the user explicitly asks.

Timed work block mode:

- Default milestone timebox: `30` minutes when the user explicitly chooses a timebox; otherwise continue until completion, validation, or a stop condition.

Milestone-specific rules:

- CSV must always include a header row even if no leads match the filter
- `damage_description` must be truncated to 200 characters
- Function must be `async` (uses `get_session()`)
- Limit query results to 5000 rows with `.limit(5000)`
- Never expose phone or email in the CSV — direct mail only needs address fields

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `libs/stormlead_db/tables.py` — confirm `LeadRow` field names for the CSV columns
2. Read `services/ping-post/api.py` — understand admin endpoint patterns and auth
3. Read `services/ping-post/auction.py` — understand async `get_session()` usage

## Suggested Implementation Order

Build these in order after discovery:

1. Create `services/ping-post/mailer.py` with `export_mailer_csv(state, service, status) -> str`
2. Run import smoke test
3. Verify CSV output format manually
4. Docs/runbooks/readiness checklist.
5. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `services/ping-post/mailer.py` exists with async `export_mailer_csv(state, service, status) -> str`
2. CSV header row is always present
3. Tracking codes use `TRACK-{id[:8].upper()}` format
4. `damage_description` is truncated to 200 chars
5. Phone and email are NOT included in CSV columns
6. Import smoke test passes
7. No secrets or `.env` files are staged.
8. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `libs/stormlead_db/tables.py`
- `services/ping-post/api.py`

## Likely Changed Files

- `services/ping-post/mailer.py` (NEW)

## Validation Suite

Required validation:

- `uv run python -c "from ping_post.mailer import export_mailer_csv; print('ok')"`
- `uv run ruff check services/ping-post/mailer.py`
- `git diff --check`
