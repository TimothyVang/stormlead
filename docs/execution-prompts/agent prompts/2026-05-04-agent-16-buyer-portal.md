# Agent-16: Buyer Portal Scaffold Execution Prompt

Date: 2026-05-04

Wave: 2 — Run AFTER all Wave 1 agents are committed and tested.

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-16 — Buyer Portal Scaffold`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-16 — Buyer Portal Scaffold` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

**Prerequisite:** Wave 1 is committed. Agent-11 buyer CRM fields are in place.

Current implemented base includes:

- `apps/landing/` created by Agent-09 (FastAPI + Jinja2 pattern)
- `services/ping-post/api.py` has buyer wallet endpoint `GET /v1/buyers/{id}/wallet` and post results
- Caddy `/buyer-portal` → 404 placeholder (fails closed)
- Buyer authentication: API key stored in buyer record; pass via cookie or header

Current stack constraints:

- Python-first.
- FastAPI + Jinja2 for SSR (same pattern as landing app).
- No direct DB access — call ping-post API endpoints only.
- Auth: simple API key in session cookie (buyer API key from BuyerRow).
- Port 8004 for dev.
- No TODO stubs shipped as complete.

Known repo learnings and memory inputs:

- Pattern: call `GET /v1/buyers/{id}/wallet` from ping-post API to get wallet balance and billing events
- Pattern: follow `apps/landing/` structure for pyproject.toml, main.py, Dockerfile, templates/
- Buyer API key is stored in `BuyerRow.api_key` (or similar) — verify exact field name before using
- Dev port: 8004 (landing = 8001, form-receiver = 8002, ping-post = 8003)
- MVP scope: wallet page, leads list page, return request form — no payment processing

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Create `apps/buyer-portal/` with FastAPI app, Jinja2 templates for wallet view, leads list, and return request form. Add to dev Docker Compose on port 8004. Auth via buyer API key cookie.

Out of scope:

- Payment processing or Stripe integration
- Real-time updates or WebSockets
- Buyer self-registration (admin creates buyers)
- Changes to ping-post API (call existing endpoints only)
- Admin-facing pages

Milestone-safe examples:

- Auth cookie check: `request.cookies.get("buyer_api_key")` → pass to ping-post as `Authorization: Bearer {key}`
- Wallet page: GET `/buyer-portal/wallet` → call `GET http://ping-post:8003/v1/buyers/{id}/wallet`
- Return form: POST `/buyer-portal/review` → call `POST http://ping-post:8003/v1/leads/{id}/return`

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Start buyer portal locally: `cd apps/buyer-portal && uvicorn main:app --port 8004`
- `curl http://localhost:8004/healthz` returns `{"status": "ok"}`
- Browser Use: open `http://localhost:8004/` and see a redirect to wallet or login page (not 500 error)
- `docker compose --env-file .env.example -f infra/compose/dev/docker-compose.yml config --quiet` passes

100% completion contract:

- Report `100/100` only when implementation, docs, tests, validation, and required Browser Use evidence are complete.
- If UI behavior changes, the final proof must include Browser Use against the running local app.
- If the score is below 100, start the final response with `Not complete:` and list the missing points, blocker, and best fallback proof.

Execution mode:

- Finish this milestone in one continuous pass if technically possible.
- Do not stop after each task for approval unless required by `AGENTS.md` or the master prompt.
- Use Browser Use to verify the portal loads in the local browser before reporting complete.
- Prefer the smallest correct vertical slice over broad scaffolding.
- Do not commit unless the user explicitly asks.

Timed work block mode:

- Default milestone timebox: `1.5` hours when the user explicitly chooses a timebox; otherwise continue until completion, validation, or a stop condition.

Milestone-specific rules:

- Buyer portal must NOT connect to the database directly — proxy all data through ping-post API
- Show the buyer's wallet balance and last 10 billing events on the wallet page
- Show a table of delivered leads (lead_id, date, service, status) on the leads page
- Return request form must POST to ping-post and display the response (success or error)
- Auth: unauthenticated requests redirect to a simple login page (buyer API key form)

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `apps/landing/main.py` — understand FastAPI + Jinja2 setup pattern to replicate exactly
2. Read `apps/landing/Dockerfile` — replicate for buyer portal
3. Read `services/ping-post/api.py` — document wallet endpoint, delivered leads endpoint, and return endpoint signatures
4. Read `infra/compose/dev/docker-compose.yml` — understand how landing service was added (replicate for buyer portal)
5. Read `.env.example` — identify buyer portal env vars needed

## Suggested Implementation Order

Build these in order after discovery:

1. Create `apps/buyer-portal/pyproject.toml`
2. Create `apps/buyer-portal/main.py` with routes: `/`, `/buyer-portal/wallet`, `/buyer-portal/leads`, `/buyer-portal/review`, `/healthz`, `/login`
3. Create `apps/buyer-portal/templates/wallet.html`, `leads.html`, `review.html`, `login.html`
4. Create `apps/buyer-portal/Dockerfile`
5. Add `buyer-portal` service to `infra/compose/dev/docker-compose.yml` on port 8004
6. Start the app and verify healthz
7. Browser Use: open portal and verify page loads
8. Docs/runbooks/readiness checklist.
9. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `apps/buyer-portal/main.py` exists with FastAPI app and all routes
2. Templates exist for wallet, leads, review, and login pages
3. `apps/buyer-portal/Dockerfile` exists
4. `apps/buyer-portal/pyproject.toml` exists
5. Buyer portal added to `infra/compose/dev/docker-compose.yml` on port 8004
6. `curl http://localhost:8004/healthz` returns 200
7. `docker compose --env-file .env.example -f infra/compose/dev/docker-compose.yml config --quiet` exits 0
8. Browser Use proof: portal homepage or wallet page loads without 500 error
9. No secrets or `.env` files are staged.
10. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `apps/landing/main.py`
- `apps/landing/Dockerfile`
- `services/ping-post/api.py`
- `infra/compose/dev/docker-compose.yml`

## Likely Changed Files

- `apps/buyer-portal/main.py` (NEW)
- `apps/buyer-portal/templates/wallet.html` (NEW)
- `apps/buyer-portal/templates/leads.html` (NEW)
- `apps/buyer-portal/templates/review.html` (NEW)
- `apps/buyer-portal/templates/login.html` (NEW)
- `apps/buyer-portal/Dockerfile` (NEW)
- `apps/buyer-portal/pyproject.toml` (NEW)
- `infra/compose/dev/docker-compose.yml` (add buyer-portal service)

## Validation Suite

Required validation:

- `docker compose --env-file .env.example -f infra/compose/dev/docker-compose.yml config --quiet`
- `curl http://localhost:8004/healthz` (after starting uvicorn)
- Browser Use: open `http://localhost:8004/` and capture screenshot
- `uv run ruff check apps/buyer-portal/`
- `git diff --check`
