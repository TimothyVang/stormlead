# Agent-14: Ping-Post Integration Tests Execution Prompt

Date: 2026-05-04

Wave: 2 — Run AFTER all Wave 1 agents are committed and tested.

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-14 — Ping-Post Integration Tests`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-14 — Ping-Post Integration Tests` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

**Prerequisite:** Wave 1 is committed. Agent-11 buyer CRM fields are in place.

Current implemented base includes:

- `services/ping-post/api.py` has FastAPI app with buyer create, auction trigger, and admin endpoints
- `services/ping-post/tests/test_auction.py` has unit tests using mocks only (no HTTP server)
- `BuyerRow` now has `services_offered`, `exclusive_zips` (from Agent-11)
- Pattern: use `httpx.AsyncClient(transport=httpx.ASGITransport(app=app))` for in-process FastAPI testing
- `campaign_source=simulation` leads use the local simulation path (no LLM calls)

Current stack constraints:

- Python-first.
- FastAPI.
- Postgres (integration tests need a real DB connection).
- pytest-asyncio for async tests.
- No external services (buyer webhook can be mocked with a local handler).
- No TODO stubs shipped as complete.

Known repo learnings and memory inputs:

- `httpx.ASGITransport(app=app)` allows in-process FastAPI testing without a real server
- Exclusive zip conflict (409) is enforced by Agent-11's `check_exclusive_zip_conflict()` via Agent-17 — but Agent-14 tests verify the API layer returns 409 when Agent-17 has wired it (or test the function directly)
- Buyer creation endpoint: `POST /v1/buyers` requires `webhook_secret` of at least 32 chars
- For tests without a real DB, use pytest fixtures with `pytest_asyncio` and a test DB or skip DB-dependent tests with `@pytest.mark.skip`

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Create `services/ping-post/tests/test_integration.py` with in-process FastAPI integration tests for health check, buyer creation, and exclusive zip conflict detection. Tests should use `httpx.ASGITransport` for in-process HTTP without a real server.

Out of scope:

- Load testing
- Buyer webhook callback tests (requires real external server)
- Full auction flow integration (needs DB seeded data)
- Changes to `api.py` or any other service files

Milestone-safe examples:

- In-process client: `async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:`
- Unique zip per test run: `zip_code = str(uuid.uuid4())[:5]`
- Buyer payload: requires `name`, `company`, `phone_e164`, `email`, `webhook_url`, `webhook_secret` (32+ chars), `bid_per_lead_t1_t2`, `bid_per_lead_t3`, `filter_expression`, `target_zips`, `exclusive_zips`

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Run `uv run pytest services/ping-post/tests/test_integration.py -v`
- Pass health check test (`GET /healthz` → 200)
- Pass buyer creation test (`POST /v1/buyers` → 200/201 with `"id"` in response)
- Pass or meaningfully document exclusive zip conflict test (409 response)

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

- Use `@pytest.fixture` (not `@pytest.fixture(scope="session")`) for the test client — each test gets a fresh client
- If the buyer creation endpoint requires a real DB and that is not available, document the exact blocker and provide the test with `@pytest.mark.skip(reason="requires live DB")` — do not delete the test
- `webhook_secret` must be at least 32 characters — use `"test-secret-32chars-minimum-ok"` exactly
- Do NOT commit generated test artifacts

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `services/ping-post/api.py` — document buyer create endpoint signature, required fields, response format
2. Read `services/ping-post/tests/test_auction.py` — understand existing test patterns and fixtures
3. Read `services/ping-post/buyer_crm.py` (Agent-11 output) — understand `check_exclusive_zip_conflict()` integration point
4. Check if `pytest-asyncio` and `httpx` are in `services/ping-post/pyproject.toml`
5. Check `conftest.py` in ping-post tests for existing fixtures

## Suggested Implementation Order

Build these in order after discovery:

1. Create `services/ping-post/tests/test_integration.py` with `client` fixture
2. Add `test_health_check` test
3. Add `test_create_buyer_returns_id` test
4. Add `test_duplicate_exclusive_zip_returns_409` test
5. Run: `uv run pytest services/ping-post/tests/test_integration.py -v`
6. Fix any failures (update test expectations if needed, do not modify `api.py`)
7. Docs/runbooks/readiness checklist.
8. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `services/ping-post/tests/test_integration.py` exists with at least 3 tests
2. `test_health_check` passes: `GET /healthz` → 200
3. `test_create_buyer_returns_id` passes or has documented DB blocker with `@pytest.mark.skip`
4. `test_duplicate_exclusive_zip_returns_409` exists and either passes or has documented blocker
5. `uv run pytest services/ping-post/tests/test_integration.py -v` exits without collection errors
6. No secrets or `.env` files are staged.
7. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `services/ping-post/api.py`
- `services/ping-post/tests/test_auction.py`
- `services/ping-post/tests/` (list all files)
- `services/ping-post/pyproject.toml`

## Likely Changed Files

- `services/ping-post/tests/test_integration.py` (NEW)

## Validation Suite

Required validation:

- `uv run pytest services/ping-post/tests/test_integration.py -v`
- `uv run ruff check services/ping-post/tests/test_integration.py`
- `git diff --check`
