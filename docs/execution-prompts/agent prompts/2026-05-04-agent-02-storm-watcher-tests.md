# Agent-02: Storm-Watcher Test Suite Execution Prompt

Date: 2026-05-04

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-02 — Storm-Watcher Test Suite`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-02 — Storm-Watcher Test Suite` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

Current implemented base includes:

- `storm-watcher` service has `nws.py` with `fetch_nws_alerts()` and `normalize_alert()`, and `fema.py` with `fetch_fema_declarations()` and `normalize_declaration()`
- `tropycal_poller.py` (created by Agent-01) has `fetch_active_tropical_systems()` and `normalize_tropical_storm()`
- `stormlead_core.models` has `Storm`, `StormSeverity` enum (WARNING, WATCH, DECLARED, etc.)
- No test directory currently exists under `services/storm-watcher/tests/`
- Pattern: other services use `pytest` + `unittest.mock.AsyncMock` + `pytest-asyncio`

Current stack constraints:

- Python-first.
- FastAPI.
- Postgres.
- Alembic.
- Hatchet.
- LiteLLM only for model calls.
- No mocked production behavior.
- No TODO stubs shipped as complete.
- Every completed task must include runnable code, tests or documented verification, docs, and validation evidence.

Known repo learnings and memory inputs:

- NWS poller hits `https://api.weather.gov/alerts/active` — mock in tests, never call real API
- FEMA poller hits `https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries` — mock in tests
- `StormSeverity.WARNING` maps to NWS "Warning" event type keywords (Tornado Warning, Hurricane Warning)
- `StormSeverity.WATCH` maps to NWS "Watch" event type keywords
- `StormSeverity.DECLARED` maps to FEMA declared disasters with storm-type `incidentType`
- Non-storm FEMA `incidentType` values (e.g., "Earthquake", "Flood") should return `None` from `normalize_declaration()`

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Create `services/storm-watcher/tests/__init__.py`, `test_nws.py`, `test_fema.py`, and `test_tropycal.py` with unit tests for all normalize/fetch functions. All tests must pass with `uv run pytest services/storm-watcher/tests/ -v`.

Out of scope:

- Integration tests that call real NWS/FEMA/NHC APIs
- DB-layer tests for `StormRow` persistence
- Hatchet workflow scheduling tests
- Changes to `nws.py`, `fema.py`, `tropycal_poller.py`, or `worker.py`

Milestone-safe examples:

- Mock HTTP: `with patch("storm_watcher.nws.httpx.AsyncClient") as mock_client: mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=...)`
- In-memory fixture: `SAMPLE_NWS_FEATURE = {"properties": {...}, "geometry": {...}}`
- Enum assert: `assert storm.severity == StormSeverity.WARNING`

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Run `uv run pytest services/storm-watcher/tests/ -v` and see all tests PASS
- Test `normalize_alert()` with WARNING and WATCH event types
- Test `normalize_alert()` with missing geometry (should not raise, `geom_wkt` may be None)
- Test `normalize_declaration()` with a storm-type `incidentType` (returns Storm) and non-storm type (returns None)
- Test `normalize_tropical_storm()` with valid dict and empty dict

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

- Never make real HTTP calls in tests — all external API calls must be patched
- Test files must import from the service package (`from storm_watcher.nws import normalize_alert`), not relative imports
- Each test file must have at least 3 test functions with distinct scenarios
- Tests must be runnable in isolation: `uv run pytest services/storm-watcher/tests/test_nws.py -v`

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `services/storm-watcher/nws.py` — document function signatures, return types, `StormSeverity` mapping logic
2. Read `services/storm-watcher/fema.py` — document function signatures, return types, incident type filter list
3. Read `services/storm-watcher/tropycal_poller.py` (Agent-01 output) — document `normalize_tropical_storm()` contract
4. Read `libs/stormlead_core/models.py` — confirm `Storm` model fields and `StormSeverity` enum values
5. Check any existing `conftest.py` or pytest config in the monorepo root or `services/` for shared fixtures

## Suggested Implementation Order

Build these in order after discovery:

1. Create `services/storm-watcher/tests/__init__.py` (empty)
2. Create `services/storm-watcher/tests/test_nws.py` (3+ tests for `normalize_alert`)
3. Create `services/storm-watcher/tests/test_fema.py` (3+ tests for `normalize_declaration`)
4. Create `services/storm-watcher/tests/test_tropycal.py` (3+ tests for `normalize_tropical_storm`)
5. Run `uv run pytest services/storm-watcher/tests/ -v` and fix any failures
6. Docs/runbooks/readiness checklist.
7. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `services/storm-watcher/tests/__init__.py` exists (empty)
2. `test_nws.py` has tests for WARNING severity, WATCH severity, and missing geometry
3. `test_fema.py` has tests for storm `incidentType` returning Storm and non-storm returning None
4. `test_tropycal.py` has tests for valid storm dict and empty dict
5. `uv run pytest services/storm-watcher/tests/ -v` exits 0 with all PASS
6. Relevant docs explain exactly how to use or operate the changed behavior.
7. No secrets or `.env` files are staged.
8. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `services/storm-watcher/nws.py`
- `services/storm-watcher/fema.py`
- `services/storm-watcher/tropycal_poller.py`
- `libs/stormlead_core/models.py`
- `services/storm-watcher/tests/` (check if it exists)

## Likely Changed Files

- `services/storm-watcher/tests/__init__.py` (NEW)
- `services/storm-watcher/tests/test_nws.py` (NEW)
- `services/storm-watcher/tests/test_fema.py` (NEW)
- `services/storm-watcher/tests/test_tropycal.py` (NEW)

## Validation Suite

Required validation:

- `uv run pytest services/storm-watcher/tests/ -v`
- `uv run ruff check services/storm-watcher/`
- `git diff --check`
