# Agent-17: Ping-Post Routing Enforcement & API Wiring Execution Prompt

Date: 2026-05-04

Wave: 3 — Run AFTER all Wave 2 agents are committed and migration 0008 is applied.

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-17 — Ping-Post Routing Enforcement & API Wiring`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-17 — Ping-Post Routing Enforcement & API Wiring` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

**Prerequisite:** All Wave 1 and Wave 2 agents are committed. Migration `0008_buyer_crm` is applied. The following modules exist: `buyer_crm.py`, `guardrails.py`, `mailer.py`, `attribution.py`.

Current implemented base includes:

- `services/ping-post/auction.py` has `_select_eligible_buyers()` and `_buyer_matches_paid_pilot_rules()` but daily/monthly caps are NOT enforced
- `BuyerRow` now has `services_offered`, `daily_cap`, `monthly_budget`, `exclusive_zips` (from migration 0008)
- Lead class `a/b/c/d` field exists on `LeadRow` as `lead_class` (string)
- All four Wave 2 modules exist: `buyer_crm.py`, `guardrails.py`, `mailer.py`, `attribution.py`

Current stack constraints:

- Python-first.
- FastAPI.
- Postgres.
- This is the highest-risk Wave 3 agent — it modifies `auction.py` (core auction engine) and `api.py` (main API).
- Changes must not break existing tests.
- No TODO stubs shipped as complete.

Known repo learnings and memory inputs:

- `_buyer_within_caps()`: count `billing_events` for today (`> func.current_date()`) for daily cap; sum `amount_cents` for this month for monthly budget
- `_buyer_matches_paid_pilot_rules()`: add service check — if `buyer.services_offered` is non-empty AND lead's `requested_service` not in list, return False
- Lead class routing: class `d` → reject immediately; class `c` → set `hold_for_review=True` and return held status; class `a/b` → proceed with auction
- `LeadRow.lead_class` defaults to `"b"` if not set by enrich-worker
- Admin endpoints to wire: campaign ROI, roi-by-zip, mailer-csv export, guardrail evaluate

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Enforce daily/monthly caps in `auction.py`, enforce service matching in `_buyer_matches_paid_pilot_rules()`, enforce lead class routing in `run_auction()`, and wire Wave 2 modules into new admin endpoints in `api.py`.

Out of scope:

- UI for routing decisions (browser-based admin only)
- Monthly budget reset automation (Postgres cron or manual reset)
- Weighted auction scoring changes
- Changes to Wave 2 module internals

Milestone-safe examples:

- Daily cap: `select(func.count()).where(BillingEventRow.buyer_id == buyer.id, BillingEventRow.event_type == "lead.posted", BillingEventRow.created_at > func.current_date())`
- Service match: `if buyer.services_offered and lead.requested_service not in buyer.services_offered: return False`
- Class D reject: `if lead.lead_class == "d": await record_transition(..., to_state=LeadStatus.REJECTED, event_type="lead.rejected"); return {"status": "rejected", "reason": "lead_class_d"}`

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Run `uv run pytest services/ping-post/ -v` and see ALL tests PASS
- Call `GET /v1/admin/attribution/campaign/{id}` and receive ROI data or null
- Call `GET /v1/admin/attribution/by-zip?state=FL` and receive zip list
- Call `GET /v1/admin/export/mailer-csv` and receive CSV download
- Call `POST /v1/admin/guardrails/evaluate` and receive action list (empty if commercial not approved)
- Verify via code inspection that `_buyer_within_caps()` checks daily AND monthly limits

100% completion contract:

- Report `100/100` only when implementation, docs, tests, validation, and required Browser Use evidence are complete.
- If UI/admin endpoint behavior changes, the final proof must include Browser Use against the running local app.
- If the score is below 100, start the final response with `Not complete:` and list the missing points, blocker, and best fallback proof.

Execution mode:

- Finish this milestone in one continuous pass if technically possible.
- Do not stop after each task for approval unless required by `AGENTS.md` or the master prompt.
- Use Browser Use to verify the new admin endpoints via the running local app before reporting complete.
- Prefer the smallest correct vertical slice over broad scaffolding.
- Do not commit unless the user explicitly asks.

Timed work block mode:

- Default milestone timebox: `2` hours when the user explicitly chooses a timebox; otherwise continue until completion, validation, or a stop condition.

Milestone-specific rules:

- Run existing ping-post tests BEFORE and AFTER each auction.py edit to detect regressions immediately
- `hold_for_review` field: verify `LeadRow` has this column before using it; add to migration if missing
- All 4 new admin endpoints must use the same admin auth as existing endpoints
- New endpoints must be added to `api.py` — do not create a separate router file
- Monthly budget check: use `date_trunc('month', now())` via SQLAlchemy `text()` for month boundary

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `services/ping-post/auction.py` — document `_select_eligible_buyers()`, `_buyer_matches_paid_pilot_rules()`, `run_auction()` exactly — find TODOs and incomplete sections
2. Read `libs/stormlead_db/tables.py` — confirm `BillingEventRow` columns, `LeadRow.lead_class` and `LeadRow.hold_for_review` fields
3. Read `services/ping-post/api.py` — document existing admin endpoints and auth pattern to replicate
4. Read `services/ping-post/tests/test_auction.py` — understand test structure to verify no regressions
5. Read Wave 2 module files: `buyer_crm.py`, `guardrails.py`, `mailer.py`, `attribution.py` — confirm function signatures

## Suggested Implementation Order

Build these in order after discovery:

1. Add `_buyer_within_caps(session, buyer)` to `auction.py` with daily + monthly checks
2. Add service match check to `_buyer_matches_paid_pilot_rules()`
3. Add lead class D reject and class C hold logic to `run_auction()`
4. Run tests: `uv run pytest services/ping-post/tests/ -v` (must pass before continuing)
5. Add 4 admin endpoints to `api.py` (attribution x2, mailer-csv, guardrails)
6. Wire `check_exclusive_zip_conflict()` into buyer create/update endpoint
7. Run full test suite again
8. Browser Use: test new admin endpoints via running local app
9. Docs/runbooks/readiness checklist.
10. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `_buyer_within_caps()` in `auction.py` enforces daily cap (count) AND monthly budget (sum)
2. `_buyer_matches_paid_pilot_rules()` returns False if lead's `requested_service` not in buyer's `services_offered`
3. Lead class `d` → rejected with `record_transition()` call; class `c` → held with `hold_for_review=True`
4. `GET /v1/admin/attribution/campaign/{campaign_id}` endpoint exists and returns data
5. `GET /v1/admin/attribution/by-zip` endpoint exists and returns list
6. `GET /v1/admin/export/mailer-csv` endpoint exists and returns CSV with correct Content-Type
7. `POST /v1/admin/guardrails/evaluate` endpoint exists and returns action list
8. `uv run pytest services/ping-post/ -v` exits 0 with ALL tests PASS
9. No secrets or `.env` files are staged.
10. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `services/ping-post/auction.py`
- `services/ping-post/api.py`
- `libs/stormlead_db/tables.py`
- `services/ping-post/buyer_crm.py`
- `services/ping-post/guardrails.py`
- `services/ping-post/mailer.py`
- `services/ping-post/attribution.py`

## Likely Changed Files

- `services/ping-post/auction.py` (add cap/territory/class enforcement)
- `services/ping-post/api.py` (add 4 admin endpoints, wire CRM conflict check)

## Validation Suite

Required validation:

- `uv run pytest services/ping-post/ -v`
- `uv run ruff check services/ping-post/`
- `uv run mypy services/ping-post/ --ignore-missing-imports`
- `uv run python scripts/smoke_e2e.py` (if local stack is running)
- Browser Use: test admin endpoints at `http://localhost:8003/v1/admin/`
- `git diff --check`
