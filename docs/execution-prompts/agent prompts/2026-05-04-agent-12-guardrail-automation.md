# Agent-12: Guardrail Automation Execution Prompt

Date: 2026-05-04

Wave: 2 — Run AFTER all Wave 1 agents are committed and tested.

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-12 — Guardrail Automation`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-12 — Guardrail Automation` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

**Prerequisite:** Wave 1 is committed.

Current implemented base includes:

- `services/ping-post/api.py` has KPI endpoints and `KpiThresholdConfig`
- `BuyerRow` has `status` column with values: `active`, `paused`, `suspended`, `low_balance`, etc.
- `PostResultRow` tracks post outcomes by `buyer_id`
- `ReturnRequestRow` tracks return requests with `status` (approved, pending, denied)
- `PingAttemptRow` tracks ping attempts with `response_ms` and `buyer_id`
- Hatchet cron workflows registered in `worker.py` files

Current stack constraints:

- Python-first.
- FastAPI.
- Postgres.
- Hatchet for cron scheduling.
- `STORMLEAD_COMMERCIAL_LAUNCH_APPROVED=true` env var must be set for guardrails to run (safety gate).
- No TODO stubs shipped as complete.

Known repo learnings and memory inputs:

- Adjustment rate threshold: >25% of posts returned → pause buyer
- Response time threshold: avg ping response >10 minutes (600,000ms) → pause buyer
- Guardrail only affects `status == "active"` buyers — paused/suspended buyers are not re-evaluated
- `STORMLEAD_COMMERCIAL_LAUNCH_APPROVED` defaults to `"false"` — must be explicitly set to `"true"` to run
- Daily cron: `0 6 * * *` (06:00 UTC)

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Create `services/ping-post/guardrails.py` with `evaluate_buyer_guardrails() -> list[dict]` and register a Hatchet daily cron workflow (`0 6 * * *`) in the ping-post worker.

Out of scope:

- Admin UI for guardrail history
- Wiring `POST /v1/admin/guardrails/evaluate` endpoint (Agent-17, Wave 3)
- Email/SMS notifications when buyers are paused
- Custom per-buyer thresholds (global thresholds only for MVP)

Milestone-safe examples:

- Commercial gate: `COMMERCIAL_APPROVED = os.getenv("STORMLEAD_COMMERCIAL_LAUNCH_APPROVED", "false").lower() == "true"`
- Empty return when not approved: `if not COMMERCIAL_APPROVED: return []`
- Adjustment rate: `returned / total if total > 0 else 0.0`

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Import `evaluate_buyer_guardrails` from `ping_post.guardrails`
- Call `evaluate_buyer_guardrails()` with `STORMLEAD_COMMERCIAL_LAUNCH_APPROVED=false` (default) and receive `[]`
- See the `GuardrailEvaluation` Hatchet workflow registered with `on_crons=["0 6 * * *"]`

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

- Guardrails MUST NOT run unless `STORMLEAD_COMMERCIAL_LAUNCH_APPROVED=true` — this is a critical safety gate
- Auto-pause via DB update is acceptable; never call external services (no email/SMS)
- Log each auto-pause action with `structlog` at WARNING level including `buyer_id` and `reasons`
- The `_adjustment_rate()` and `_avg_ping_response_ms()` helper functions must be separate from the main function for testability
- Look up `PingAttemptRow` table name from existing tables.py before writing queries

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `libs/stormlead_db/tables.py` — confirm `PostResultRow`, `ReturnRequestRow`, `PingAttemptRow` column names and `BuyerRow.status` enum values
2. Read `services/ping-post/api.py` — understand `KpiThresholdConfig` and existing KPI query patterns
3. Read `services/ping-post/worker.py` (if exists) or `services/agent-runtime/worker.py` — understand Hatchet cron class pattern
4. Read `services/ping-post/auction.py` — understand `get_session()` usage pattern for async DB queries
5. Read `.env.example` — find `STORMLEAD_COMMERCIAL_LAUNCH_APPROVED` entry

## Suggested Implementation Order

Build these in order after discovery:

1. Create `services/ping-post/guardrails.py` with commercial launch gate check
2. Implement `_adjustment_rate(session, buyer_id) -> float`
3. Implement `_avg_ping_response_ms(session, buyer_id) -> float`
4. Implement `evaluate_buyer_guardrails() -> list[dict]`
5. Register `GuardrailEvaluation` Hatchet cron workflow in the ping-post worker
6. Run import smoke test
7. Docs/runbooks/readiness checklist.
8. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `services/ping-post/guardrails.py` exists with `evaluate_buyer_guardrails()`
2. Returns `[]` when `STORMLEAD_COMMERCIAL_LAUNCH_APPROVED` is not `"true"`
3. `GuardrailEvaluation` Hatchet workflow registered with `on_crons=["0 6 * * *"]`
4. Import smoke test passes
5. `_adjustment_rate` and `_avg_ping_response_ms` are separate testable functions
6. No secrets or `.env` files are staged.
7. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `libs/stormlead_db/tables.py`
- `services/ping-post/api.py`
- `services/ping-post/auction.py`
- `.env.example`

## Likely Changed Files

- `services/ping-post/guardrails.py` (NEW)
- `services/ping-post/worker.py` or wherever Hatchet crons are registered (add GuardrailEvaluation)

## Validation Suite

Required validation:

- `uv run python -c "from ping_post.guardrails import evaluate_buyer_guardrails; print('ok')"`
- `uv run ruff check services/ping-post/guardrails.py`
- `git diff --check`
