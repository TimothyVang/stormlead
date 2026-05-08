# Agent-09: Landing Page Scaffold Execution Prompt

Date: 2026-05-04

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-09 — Landing Page Scaffold`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-09 — Landing Page Scaffold` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

Current implemented base includes:

- `apps/` directory exists but is empty (or has only `.gitkeep`)
- Caddy serves the main domain; landing page intended at `http://localhost:8001` in dev
- Formbricks is the form platform: embed via `<script>` tag referencing `FORMBRICKS_ENV_ID`
- `infra/compose/dev/docker-compose.yml` already defines core services (form-receiver, ping-post, etc.)
- Pattern: other services use `uvicorn` as the ASGI server with `--host 0.0.0.0`

Current stack constraints:

- Python-first.
- FastAPI + Jinja2 for SSR (no React/Node frontend).
- Docker Compose for dev and prod.
- No direct DB access from the landing app (stateless, no user accounts).
- No JavaScript frameworks — plain HTML with Formbricks script embed.
- No TODO stubs shipped as complete.

Known repo learnings and memory inputs:

- Formbricks config via `window.formbricksConfig = { environmentId: ..., surveyId: ..., hiddenFields: {...} }`
- UTM params (`utm_source`, `utm_campaign`) must be propagated to Formbricks `hiddenFields`
- Landing app port: `8001` (form-receiver is 8002, ping-post is 8003)
- Caddy route `/` will point to landing app in prod (currently 404)
- Healthz endpoint required: `GET /healthz` → `{"status": "ok"}`

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Create `apps/landing/` with `main.py` (FastAPI app), `templates/index.html` (Jinja2 template with Formbricks embed), `Dockerfile`, and `pyproject.toml`. Add the landing service to `infra/compose/dev/docker-compose.yml`.

Out of scope:

- Multi-page routing (single page only for MVP)
- SEO-optimized PSEO page variants
- Backend form submission handling (Formbricks handles that)
- Authentication
- Changes to Caddy config (update in prod compose by Agent-15/19)

Milestone-safe examples:

- Jinja2 template context: `{"request": request, "formbricks_env_id": ..., "utm_source": ...}`
- Hidden field attribution: pass UTM params via `window.formbricksConfig.hiddenFields`
- Healthz: `@app.get("/healthz") async def health(): return {"status": "ok"}`

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Start landing app locally: `cd apps/landing && uvicorn main:app --port 8001`
- `curl http://localhost:8001/` returns HTML with Formbricks script embed
- `curl http://localhost:8001/healthz` returns `{"status": "ok"}`
- `curl "http://localhost:8001/?utm_source=google&utm_campaign=spring"` returns HTML with UTM values in `hiddenFields`
- `docker compose config --quiet` (dev compose) passes without errors after service addition

100% completion contract:

- Report `100/100` only when implementation, docs, tests, validation, and required Browser Use evidence are complete.
- If UI behavior changes, the final proof must include Browser Use against the running local app showing the landing page.
- If the score is below 100, start the final response with `Not complete:` and list the missing points, blocker, and best fallback proof.

Execution mode:

- Finish this milestone in one continuous pass if technically possible.
- Do not stop after each task for approval unless required by `AGENTS.md` or the master prompt.
- Use Browser Use to verify the landing page visually in the local browser before reporting complete.
- Prefer the smallest correct vertical slice over broad scaffolding.
- Do not commit unless the user explicitly asks.

Timed work block mode:

- Default milestone timebox: `1` hour when the user explicitly chooses a timebox; otherwise continue until completion, validation, or a stop condition.

Milestone-specific rules:

- Do NOT embed real homeowner data or contact information in templates
- The Formbricks `environmentId` and `surveyId` must come from env vars, not hardcoded values
- Jinja2 autoescape must be enabled (default in `Jinja2Templates`) to prevent XSS
- The landing app must NOT connect to the database

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `infra/compose/dev/docker-compose.yml` — understand service definition pattern (image, build, ports, environment, depends_on)
2. Read `apps/` directory structure — confirm it is empty or has only gitkeep
3. Read any existing `apps/*/Dockerfile` pattern from other services for reference
4. Read `.env.example` — find Formbricks env var names
5. Read `services/form-receiver/api.py` — understand FastAPI app setup pattern used elsewhere

## Suggested Implementation Order

Build these in order after discovery:

1. Create `apps/landing/pyproject.toml` with fastapi, uvicorn, jinja2 dependencies
2. Create `apps/landing/main.py` with FastAPI app, `/` and `/healthz` routes
3. Create `apps/landing/templates/index.html` with Formbricks embed and UTM hidden fields
4. Create `apps/landing/Dockerfile`
5. Add `landing` service to `infra/compose/dev/docker-compose.yml`
6. Verify: start the app and run curl tests
7. Browser Use: open `http://localhost:8001` and verify Formbricks embed renders
8. Docs/runbooks/readiness checklist.
9. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `apps/landing/main.py` exists with FastAPI app, `/` and `/healthz` routes
2. `apps/landing/templates/index.html` embeds Formbricks with UTM hidden fields from query params
3. `apps/landing/Dockerfile` exists and builds without errors
4. `apps/landing/pyproject.toml` exists with correct dependencies
5. Landing service added to `infra/compose/dev/docker-compose.yml` on port 8001
6. `docker compose --env-file .env.example -f infra/compose/dev/docker-compose.yml config --quiet` exits 0
7. Browser Use proof: landing page loads and Formbricks embed is visible
8. No secrets or `.env` files are staged.
9. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `infra/compose/dev/docker-compose.yml`
- `apps/` (list contents)
- `.env.example`

## Likely Changed Files

- `apps/landing/main.py` (NEW)
- `apps/landing/templates/index.html` (NEW)
- `apps/landing/Dockerfile` (NEW)
- `apps/landing/pyproject.toml` (NEW)
- `infra/compose/dev/docker-compose.yml` (add landing service)

## Validation Suite

Required validation:

- `docker compose --env-file .env.example -f infra/compose/dev/docker-compose.yml config --quiet`
- `uv run ruff check apps/landing/`
- `curl http://localhost:8001/healthz` (after starting uvicorn)
- Browser Use: open `http://localhost:8001/` and capture screenshot
- `git diff --check`
