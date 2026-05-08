# Agent-11: Buyer CRM Fields & Territory Management Execution Prompt

Date: 2026-05-04

Wave: 2 — Run AFTER all Wave 1 agents are committed and tested.

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-11 — Buyer CRM Fields & Territory Management`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-11 — Buyer CRM Fields & Territory Management` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

**Prerequisite:** Wave 1 is committed. Migration `0007_skill_proposals` (Agent-05) is applied. Current Alembic head is `0007`.

Current implemented base includes:

- `BuyerRow` in `stormlead_db/tables.py` has: name, company, contact info, status, CEL `filter_expression`, bid prices, `deposit_balance`, `target_zips`, `exclusive_zips`, `daily_cap`, `monthly_budget`
- `BuyerRow` is MISSING: `sales_stage`, `services_offered`, `notes`, `follow_up_date`, `low_balance_threshold_cents`
- `exclusive_zips` is a JSONB column containing a list of zip strings
- `CallEventRow` was added by Agent-07 (Wave 1)

Current stack constraints:

- Python-first.
- FastAPI.
- Postgres.
- Alembic — migration must chain from `0007`.
- No TODO stubs shipped as complete.
- Territory conflict check raises HTTP 409 (not a soft failure).

Known repo learnings and memory inputs:

- `sales_stage` lifecycle: `prospect → contacted → agreement_sent → funded → active → low_balance → paused → suspended → churned`
- `services_offered` is a JSONB list of service strings (e.g., `["tree_removal", "roof_tarp"]`)
- `exclusive_zips` uses Postgres JSONB `?|` operator to check array overlap: `.op("?|")(exclusive_zips)`
- Territory conflict should check only `status == "active"` buyers, not paused/suspended
- `low_balance_threshold_cents` defaults to 10000 (= $100.00)

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Add CRM columns to `BuyerRow`, create Alembic migration `0008_buyer_crm`, and create `services/ping-post/buyer_crm.py` with `check_exclusive_zip_conflict()` that raises HTTP 409 on territory conflict.

Out of scope:

- Admin UI for CRM fields (buyer portal, Wave 2 Agent-16)
- Wiring buyer_crm into API endpoints (Agent-17, Wave 3)
- Sales stage automation (manual updates only)
- Changes to auction.py or any other ping-post files

Milestone-safe examples:

- JSONB overlap: `BuyerRow.exclusive_zips.op("?|")(exclusive_zips)` where `exclusive_zips` is a Python list
- Migration chain: `revision = "0008"; down_revision = "0007"`
- 409 detail: `f"ZIP conflict with buyers: {[str(r.id) for r in conflicts]}"`

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Run `uv run alembic upgrade head` and see migration `0008_buyer_crm` applied
- Import `check_exclusive_zip_conflict` from `ping_post.buyer_crm`
- Query `BuyerRow.sales_stage`, `BuyerRow.services_offered`, `BuyerRow.notes`, `BuyerRow.follow_up_date`, `BuyerRow.low_balance_threshold_cents` from the DB
- Call `check_exclusive_zip_conflict(None, [])` without raising

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

- This is the only Wave 2 agent that modifies `libs/stormlead_db/tables.py` — do not let Wave 2 peers edit it simultaneously
- Migration `0008` must also include the `call_events` table from Agent-07 if that migration was not yet created
- Add indexes: `ix_buyers_sales_stage` on `sales_stage`, `ix_buyers_follow_up_date` on `follow_up_date`
- The `check_exclusive_zip_conflict()` function must be `async` (uses `get_session()`)

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `libs/stormlead_db/tables.py` — document current `BuyerRow` columns and confirm current Alembic head
2. Read `libs/stormlead_db/migrations/versions/` — find the current head migration (should be `0007`)
3. Read `services/ping-post/api.py` — understand buyer create/update endpoint to identify where conflict check will be called by Agent-17
4. Read `services/ping-post/auction.py` — confirm `BuyerRow` import and usage pattern
5. Read existing tests in `services/ping-post/tests/` to understand test patterns

## Suggested Implementation Order

Build these in order after discovery:

1. Add 5 CRM columns to `BuyerRow` in `libs/stormlead_db/tables.py`
2. Create `libs/stormlead_db/migrations/versions/0008_buyer_crm.py` (chain from `0007`)
3. Create `services/ping-post/buyer_crm.py` with `check_exclusive_zip_conflict()`
4. Run `uv run alembic upgrade head`
5. Run import smoke test for `buyer_crm`
6. Docs/runbooks/readiness checklist.
7. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `BuyerRow` has 5 new columns: `sales_stage`, `services_offered`, `notes`, `follow_up_date`, `low_balance_threshold_cents`
2. Migration `0008_buyer_crm.py` exists with `revision="0008"` and `down_revision="0007"`
3. `uv run alembic upgrade head` exits 0 with `0008_buyer_crm` applied
4. `services/ping-post/buyer_crm.py` exists with `check_exclusive_zip_conflict(buyer_id, exclusive_zips)` async function
5. `check_exclusive_zip_conflict(None, [])` returns without raising
6. Import smoke tests pass
7. No secrets or `.env` files are staged.
8. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `libs/stormlead_db/tables.py`
- `libs/stormlead_db/migrations/versions/` (list files, find current head)
- `services/ping-post/api.py`

## Likely Changed Files

- `libs/stormlead_db/tables.py` (add 5 CRM columns to BuyerRow)
- `libs/stormlead_db/migrations/versions/0008_buyer_crm.py` (NEW)
- `services/ping-post/buyer_crm.py` (NEW)

## Validation Suite

Required validation:

- `uv run alembic upgrade head`
- `uv run python -c "from ping_post.buyer_crm import check_exclusive_zip_conflict; print('ok')"`
- `uv run ruff check services/ping-post/buyer_crm.py libs/stormlead_db/`
- `uv run pytest services/ping-post/tests/ -v`
- `git diff --check`
