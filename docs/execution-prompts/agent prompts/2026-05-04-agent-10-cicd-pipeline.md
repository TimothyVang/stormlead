# Agent-10: CI/CD Pipeline Execution Prompt

Date: 2026-05-04

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-10 — CI/CD Pipeline`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-10 — CI/CD Pipeline` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

Current implemented base includes:

- `.github/workflows/` exists but contains only `.gitkeep` (no workflow files)
- Python monorepo uses `uv` workspace with `libs/` and `services/` directories
- Node tooling: `npm run test:playwright` runs Playwright tests
- Smoke test: `uv run python scripts/smoke_e2e.py`
- Docker images: multi-service (ping-post, form-receiver, storm-watcher, enrich-worker, agent-runtime)
- CI target: GitHub Actions on PR to `main` and push to `main`

Current stack constraints:

- `uv` for Python dependency management (not pip, not poetry)
- `astral-sh/setup-uv@v3` GitHub Action for uv setup
- `actions/setup-node@v4` for Node (version 20) for Playwright
- Docker image registry: `ghcr.io/stormlead/{service}` using `GITHUB_TOKEN`
- Ruff for linting; mypy for type checking
- Postgres service in CI: `timescale/timescaledb-ha:pg16-ts2.17`

Known repo learnings and memory inputs:

- `DATABASE_URL` for tests: `postgresql+psycopg://stormlead:stormlead@localhost:5432/stormlead_test`
- Matrix build: services are `ping-post`, `form-receiver`, `storm-watcher`, `enrich-worker`, `agent-runtime`
- Build images only on push to `main`, not on PRs (reduce CI cost)
- Smoke workflow is manual dispatch only (`workflow_dispatch`) — not auto-triggered
- Python test job needs Alembic migrations run before pytest

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Create `.github/workflows/ci.yml` (lint + type-check + pytest + Playwright + Docker build) and `.github/workflows/smoke.yml` (manual smoke dispatch). Remove the `.gitkeep` in `.github/workflows/`.

Out of scope:

- Kubernetes/Helm deployment steps
- Staging/production deployment from CI (only build and push images)
- Secrets rotation automation
- PR labeling or auto-assignment

Milestone-safe examples:

- uv sync: `uv sync --all-extras`
- Postgres service in CI: `image: timescale/timescaledb-ha:pg16-ts2.17` with `--health-cmd pg_isready`
- Matrix: `strategy: {matrix: {service: [ping-post, form-receiver, storm-watcher, enrich-worker, agent-runtime]}}`

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Read `.github/workflows/ci.yml` and see: lint-and-type job, test-python job, test-playwright job, build-images job
- Read `.github/workflows/smoke.yml` and see `workflow_dispatch` trigger with `environment` input
- Verify `ci.yml` is valid YAML with `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
- Verify `smoke.yml` is valid YAML with the same
- Confirm build-images job runs only on `github.ref == 'refs/heads/main'`

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

- Do NOT use `pip install` in CI — use `uv sync` exclusively
- The `build-images` job must `needs: [lint-and-type, test-python]` to prevent broken images from being pushed
- Use `actions/checkout@v4`, `docker/login-action@v3`, and `docker/build-push-action@v5` (pinned to v4/v3/v5)
- The `test-playwright` job does NOT need Postgres — it should be independent
- Remove `.gitkeep` from `.github/workflows/` when creating the first workflow file

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `pyproject.toml` (monorepo root) — confirm `uv` workspace config and test commands
2. Read any existing `services/*/Dockerfile` — understand build context and Docker image structure
3. Read `package.json` — confirm `npm run test:playwright` script name and any env vars needed
4. Read `scripts/smoke_e2e.py` — understand what env vars it needs
5. List `.github/workflows/` — confirm only `.gitkeep` exists

## Suggested Implementation Order

Build these in order after discovery:

1. Create `.github/workflows/ci.yml` with all 4 jobs
2. Create `.github/workflows/smoke.yml` with manual dispatch
3. Remove `.github/workflows/.gitkeep` if it exists
4. Validate YAML syntax for both files
5. Docs/runbooks/readiness checklist.
6. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `.github/workflows/ci.yml` exists with `lint-and-type`, `test-python`, `test-playwright`, `build-images` jobs
2. `.github/workflows/smoke.yml` exists with `workflow_dispatch` trigger and `smoke` job
3. `build-images` job conditions on `github.ref == 'refs/heads/main'` and `needs: [lint-and-type, test-python]`
4. `test-python` job includes Postgres service container and runs `uv run alembic upgrade head` before pytest
5. Both YAML files parse without errors
6. `.gitkeep` removed from `.github/workflows/` (no longer needed)
7. No secrets or `.env` files are staged.
8. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `.github/workflows/` (list contents)
- `pyproject.toml` (root)
- `package.json`
- `services/ping-post/Dockerfile` (for build context reference)

## Likely Changed Files

- `.github/workflows/ci.yml` (NEW)
- `.github/workflows/smoke.yml` (NEW)
- `.github/workflows/.gitkeep` (DELETE)

## Validation Suite

Required validation:

- `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ci.yml valid')"`
- `python -c "import yaml; yaml.safe_load(open('.github/workflows/smoke.yml')); print('smoke.yml valid')"`
- `git diff --check`
