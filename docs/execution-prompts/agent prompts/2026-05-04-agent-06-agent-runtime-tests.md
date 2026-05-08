# Agent-06: Agent-Runtime Test Suite Execution Prompt

Date: 2026-05-04

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-06 — Agent-Runtime Test Suite`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-06 — Agent-Runtime Test Suite` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

Current implemented base includes:

- `services/agent-runtime/tests/` has: `test_litellm_policy.py`, `test_nurture.py`, `test_replay_plan.py`
- `hermes.py` (after Agent-05) has `_fetch_weekly_traces()`, `_summarize_traces()`, `_persist_proposals()`
- `qualify.py` has `_local_simulation_result()` path (no LLM call when `campaign_source=simulation`)
- `qualify.py` has `_parse_qualification()` and `_class_from_score()` helper functions

Current stack constraints:

- Python-first.
- pytest + pytest-asyncio for all tests.
- Use `unittest.mock.AsyncMock` and `patch` for external calls — no real LLM or DB calls in unit tests.
- No TODO stubs shipped as complete.

Known repo learnings and memory inputs:

- `qualify.py` simulation path: pass `campaign_source="simulation"` in the lead row to skip real LLM calls
- `_parse_qualification()` expects a JSON string with keys: `damage_tier`, `qualification_score`, `reasoning`, `rejection_reason`
- `_class_from_score()`: 0.8+ → "a", 0.6-0.8 → "b", 0.4-0.6 → "c", below 0.4 → "d"
- Score out of range (> 1.0 or < 0.0) should raise `ValueError` in `_parse_qualification()`
- `_summarize_traces([])` should return string with "Traces analyzed: 0"

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Create `services/agent-runtime/tests/test_hermes.py` with unit tests for Hermes helper functions, and `services/agent-runtime/tests/test_qualify_edge_cases.py` with edge-case tests for `_parse_qualification` and `_class_from_score`. All tests must pass.

Out of scope:

- DB integration tests (no real Postgres connection)
- Full workflow orchestration tests
- Changes to `hermes.py`, `qualify.py`, or any other service files

Milestone-safe examples:

- Async mock: `mock_client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=Exception("connection refused"))`
- Score edge case: score 1.5 should raise ValueError
- Class boundary test: `assert _class_from_score(0.8) == "a"` and `assert _class_from_score(0.799) == "b"`

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Run `uv run pytest services/agent-runtime/tests/ -v` and see ALL tests PASS (including existing ones)
- Test Hermes trace summarizer with empty and non-empty trace lists
- Test Hermes trace fetcher with connection error (returns [])
- Test `_parse_qualification()` with valid JSON, invalid score range
- Test `_class_from_score()` at boundary values

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

- All tests must be isolated — no DB connections, no real HTTP calls
- Do NOT modify the functions being tested — only write tests
- Each test file must have at least 3 test functions with distinct scenarios
- Mark async tests with `@pytest.mark.asyncio`
- Test the BEHAVIOR, not the implementation details (do not assert on internal variable names)

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `services/agent-runtime/hermes.py` — document `_fetch_weekly_traces()`, `_summarize_traces()`, `_persist_proposals()` exact signatures and return types
2. Read `services/agent-runtime/qualify.py` — document `_parse_qualification()` and `_class_from_score()` signatures, score range validation logic
3. Read `services/agent-runtime/tests/test_nurture.py` — understand existing mocking pattern and fixture setup
4. Read any `conftest.py` in agent-runtime or repo root for shared fixtures
5. Check `services/agent-runtime/pyproject.toml` for pytest-asyncio configuration

## Suggested Implementation Order

Build these in order after discovery:

1. Create `services/agent-runtime/tests/test_hermes.py` with `_summarize_traces` and `_fetch_weekly_traces` tests
2. Create `services/agent-runtime/tests/test_qualify_edge_cases.py` with `_parse_qualification` and `_class_from_score` tests
3. Run all agent-runtime tests: `uv run pytest services/agent-runtime/tests/ -v`
4. Fix any failures (do not modify the functions under test — fix the test expectations)
5. Docs/runbooks/readiness checklist.
6. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `test_hermes.py` exists with at least 3 tests: empty traces digest, failure trace digest, connection error on fetch
2. `test_qualify_edge_cases.py` exists with at least 3 tests: valid parse, score > 1.0 raises ValueError, class boundary values
3. `uv run pytest services/agent-runtime/tests/ -v` exits 0 with ALL tests PASS (including pre-existing tests)
4. No existing tests are broken by the new files
5. No secrets or `.env` files are staged.
6. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `services/agent-runtime/hermes.py`
- `services/agent-runtime/qualify.py`
- `services/agent-runtime/tests/test_nurture.py`
- `services/agent-runtime/tests/` (list all files)

## Likely Changed Files

- `services/agent-runtime/tests/test_hermes.py` (NEW)
- `services/agent-runtime/tests/test_qualify_edge_cases.py` (NEW)

## Validation Suite

Required validation:

- `uv run pytest services/agent-runtime/tests/ -v`
- `uv run ruff check services/agent-runtime/tests/`
- `git diff --check`
