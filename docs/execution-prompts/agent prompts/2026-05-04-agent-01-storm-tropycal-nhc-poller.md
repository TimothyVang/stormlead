# Agent-01: Storm Tropycal/NHC Poller Execution Prompt

Date: 2026-05-04

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-01 — Storm Tropycal/NHC Poller`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-01 — Storm Tropycal/NHC Poller` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

Current implemented base includes:

- `storm-watcher` service has working `nws.py` (every 5min cron) and `fema.py` (every 30min cron) pollers
- `worker.py` already has Hatchet cron setup using `hatchet.workflow(on_crons=[...])`
- `stormlead_core.models` has `Storm`, `StormSeverity` (WARNING, WATCH, DECLARED, etc.)
- `stormlead_db.tables` has `StormRow` with `external_id`, `severity`, `raw`, `geom_wkt`, `detected_at` columns
- `stormlead_db.engine` exports `get_session()` async context manager

Current stack constraints:

- Python-first.
- FastAPI.
- Postgres.
- Alembic.
- Hatchet.
- LiteLLM only for model calls.
- Browser Use for visible local browser proof.
- Playwright for repeatable browser regression coverage.
- Docker Compose for dev and prod.
- No mocked production behavior.
- No fake KPI, buyer, lead, campaign, billing, or workflow data outside explicit test/seed paths.
- No TODO stubs shipped as complete.
- Every agent/workflow/business decision that affects paid delivery must be persisted for audit.
- Every completed task must include runnable code, tests or documented verification, docs, and validation evidence.

Known repo learnings and memory inputs:

- `storm-watcher/__init__.py` module docstring says: "Tropycal/NHC poller — during hurricane season jun-nov"
- Storm severity constant to use for active tropical systems: `StormSeverity.WARNING`
- Tropycal library: `tropycal.tracks.TrackDataset(basin=..., source="nhc")` fetches ATCF data
- NHC active storms have `operational_id` set in the storm dict; inactive systems have it empty/None
- Nominatim rate limit is 1 req/s — Tropycal data already has lat/lon so geocoding is not needed here

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Create `services/storm-watcher/tropycal_poller.py` with `fetch_active_tropical_systems()` and `normalize_tropical_storm()`, then register a Hatchet cron workflow in `services/storm-watcher/worker.py` that runs every 15 minutes and is season-gated (Jun-Nov).

Out of scope:

- Historical storm replay or season archive fetches
- Surge or wind radius polygon extraction (raw dict stored as-is)
- Any UI changes or admin page updates
- Real NHC API calls during testing (use unit-test mocks)
- Changes to `nws.py` or `fema.py` pollers

Milestone-safe examples:

- `from stormlead_core.models import Storm, StormSeverity` — correct import path
- Season guard: `month = datetime.now(timezone.utc).month; return 6 <= month <= 11`
- Conflict-safe upsert: `insert(...).on_conflict_do_update(index_elements=["external_id"], set_={...})`

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Import `tropycal_poller.py` without errors: `uv run python -c "from storm_watcher.tropycal_poller import normalize_tropical_storm; print('ok')"`
- Call `normalize_tropical_storm(sample_dict)` and receive a `Storm` model or `None`
- See the `NHCTropycalPoller` workflow registered in `worker.py` with `on_crons=["*/15 * * * *"]`
- Confirm the season guard skips execution outside Jun-Nov
- Pass all tests added by Agent-02 that import from this module

100% completion contract:

- Report `100/100` only when implementation, docs, tests, validation, and required Browser Use evidence are complete.
- If UI, admin, dashboard, routing, review, or workflow behavior changes, the final proof must include Browser Use against a running local app.
- If the score is below 100, start the final response with `Not complete:` and list the missing points, blocker, and best fallback proof.

Execution mode:

- Finish this milestone in one continuous pass if technically possible.
- Do not stop after each task for approval unless user approval is required by `AGENTS.md` or the master prompt.
- Use parallel subagents or parallel tool calls after initial inspection only when scopes are independent and safe to merge.
- The main agent owns final architecture decisions, code integration, validation, docs, and final response.
- Subagents may research and propose implementation details, but the main agent must verify all findings directly before editing.
- Only ask the user for clarification if there is a real product ambiguity, paid dependency choice, destructive action risk, production/external-action risk, or credential gap with no local fallback.
- Prefer the smallest correct vertical slice over broad scaffolding.
- A task is not done when an endpoint, doc, or UI exists; it is done only when backed by real repo behavior, documented, and validated.
- Do not commit unless the user explicitly asks.

Timed work block mode:

- Default milestone timebox: `1` hour when the user explicitly chooses a timebox; otherwise continue until completion, validation, or a stop condition.

Milestone-specific rules:

- Do not call real NHC/Tropycal APIs during automated tests — mock `TrackDataset` in pytest fixtures
- The workflow must be guarded inside the `run()` step body (not at cron registration time) so Hatchet can still register it year-round
- Add `"tropycal>=1.2"` to `services/storm-watcher/pyproject.toml` dependencies
- Use `asyncio.get_event_loop().run_in_executor(None, ...)` to wrap synchronous Tropycal calls
- Non-fatal errors per basin: log warning and continue to next basin rather than raising

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `services/storm-watcher/worker.py` and `nws.py` to understand current Hatchet cron pattern and `StormRow` upsert logic
2. Read `libs/stormlead_core/models.py` to confirm `Storm`, `StormSeverity` model field names
3. Read `libs/stormlead_db/tables.py` to confirm `StormRow` schema and which columns exist
4. Check `services/storm-watcher/pyproject.toml` for current dependencies
5. Check `services/storm-watcher/tests/` for existing test patterns (may not exist yet)

## Suggested Implementation Order

Build these in order after discovery:

1. Add `tropycal>=1.2` to `services/storm-watcher/pyproject.toml`
2. Create `services/storm-watcher/tropycal_poller.py` with `fetch_active_tropical_systems()` and `normalize_tropical_storm()`
3. Add `_is_hurricane_season()` helper and `NHCTropycalPoller` workflow class to `worker.py`
4. Run import smoke test: `uv run python -c "from storm_watcher.tropycal_poller import normalize_tropical_storm; print('ok')"`
5. Update `docs/` or service README if the storm-watcher README lists supported pollers
6. Docs/runbooks/readiness checklist.
7. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `services/storm-watcher/tropycal_poller.py` exists with `fetch_active_tropical_systems() -> list[dict]` and `normalize_tropical_storm(dict) -> Storm | None`
2. `NHCTropycalPoller` Hatchet workflow class is registered in `worker.py` with `on_crons=["*/15 * * * *"]`
3. Season guard returns `{"skipped": True, "reason": "outside_hurricane_season"}` when month is outside Jun-Nov
4. `normalize_tropical_storm({})` returns `None` without raising
5. `uv run python -c "from storm_watcher.tropycal_poller import normalize_tropical_storm; print('ok')"` exits 0
6. Relevant docs explain exactly how to use or operate the changed behavior.
7. Generated screenshots, videos, traces, manifests, and logs remain uncommitted under ignored `testing/` paths.
8. No secrets or `.env` files are staged.
9. Browser Use proof exists for any changed UI/operator workflow, or an exact tool-availability blocker and fallback proof is documented.
10. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `services/storm-watcher/worker.py`
- `services/storm-watcher/nws.py`
- `libs/stormlead_core/models.py`
- `libs/stormlead_db/tables.py`
- `services/storm-watcher/pyproject.toml`

## Likely Changed Files

- `services/storm-watcher/tropycal_poller.py` (NEW)
- `services/storm-watcher/worker.py` (add NHCTropycalPoller class + import)
- `services/storm-watcher/pyproject.toml` (add tropycal dependency)

## Validation Suite

Run the smallest relevant checks during implementation, then run the required final suite before final handoff.

Required validation:

- `uv run python -c "from storm_watcher.tropycal_poller import normalize_tropical_storm; print('ok')"`
- `uv run ruff check services/storm-watcher/`
- `uv run mypy services/storm-watcher/ --ignore-missing-imports`
- `git diff --check`

Use these common commands when relevant:

- `uv run pytest services/storm-watcher/ -v` (once Agent-02 tests are written)
- `uv run ruff check services libs scripts/smoke_e2e.py scripts/replay_lead.py scripts/simulate_v1_leads.py`

## Final Response

Final response must include:

- Completion score or readiness label if the milestone defines one.
- Exact validation commands and results.
- Changed files.
- Evidence paths if generated.
- Safety constraints preserved.
- Reusable learnings captured and where, or `none`.
- Prompt/code logic improvements made, or why none were needed.
- Any local-only caveats.
- Clear statement of whether the milestone is complete or still blocked by technical work.
- If completion is below 100/100, start with `Not complete:` and explain exactly what remains.
