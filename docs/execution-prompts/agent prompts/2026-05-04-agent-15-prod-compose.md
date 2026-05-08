# Agent-15: Prod Compose Operationalization Execution Prompt

Date: 2026-05-04

Wave: 2 — Run AFTER all Wave 1 agents are committed and tested.

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-15 — Prod Compose Operationalization`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-15 — Prod Compose Operationalization` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

**Prerequisite:** Wave 1 is committed.

Current implemented base includes:

- `infra/compose/dev/docker-compose.yml` is complete with all development services
- `infra/compose/prod/docker-compose.yml` is a skeleton — incomplete service definitions
- No `infra/systemd/` directory exists yet
- No `scripts/deploy.sh` exists yet
- Docker image naming convention: `ghcr.io/stormlead/{service}` (from CI pipeline Agent-10)

Current stack constraints:

- Docker Compose v2 syntax.
- All secrets from env vars (no hardcoded values or defaults in prod).
- Caddy as single ingress (no direct port exposure from services except Caddy).
- `restart: unless-stopped` on all services.
- JSON file logging driver with 100m max-size.
- Do NOT touch production systems — this is a local config file edit only.

Known repo learnings and memory inputs:

- Prod image tag: `ghcr.io/stormlead/{service}:2026.05.0` (semantic versioning by month)
- Services in prod: ping-post, form-receiver, storm-watcher, enrich-worker, agent-runtime, postgres, redis, hatchet-engine, hatchet-api, langfuse-web, litellm, caddy
- Dev ports should be removed in prod (Caddy is the only ingress on 80/443)
- `EnvironmentFile=/opt/stormlead/.env.prod` in systemd unit
- `deploy.sh` uses `docker compose pull` then `up -d --remove-orphans` with health checks

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Complete `infra/compose/prod/docker-compose.yml` with pinned image tags, prod-appropriate env var refs, restart policies, and logging. Create `infra/systemd/stormlead.service` and `scripts/deploy.sh`.

Out of scope:

- Kubernetes/Helm manifests
- Blue-green or canary deployment
- Auto-TLS provisioning (operator sets up DNS and ACME separately)
- Changes to dev compose
- Actual deployment to any server

Milestone-safe examples:

- Image tag: `image: ghcr.io/stormlead/ping-post:2026.05.0`
- Logging driver: `logging: {driver: "json-file", options: {max-size: "100m", max-file: "3"}}`
- Health check: `curl -sf http://localhost:8002/healthz && echo "form-receiver: ok"`

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Run `docker compose --env-file .env.example -f infra/compose/prod/docker-compose.yml config --quiet` without errors
- Read `infra/systemd/stormlead.service` and see valid systemd unit syntax
- Read `scripts/deploy.sh` and see health check `curl` commands for form-receiver and ping-post

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

- NEVER include real credentials, API keys, or passwords in any config file — use `${ENV_VAR}` references only
- DO NOT push or deploy to any server — this milestone is config file authoring only
- `deploy.sh` must be `chmod +x` compatible (add shebang `#!/bin/bash` and `set -euo pipefail`)
- All service definitions must have `restart: unless-stopped`
- The systemd `WorkingDirectory` must be `/opt/stormlead` (the expected prod deployment path)

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `infra/compose/dev/docker-compose.yml` — document all service names, port mappings, env vars, and dependencies
2. Read `infra/compose/prod/docker-compose.yml` (skeleton) — identify what is already defined and what is missing
3. Read `.env.example` — identify all env vars needed for prod
4. Read `services/*/Dockerfile` patterns to understand build contexts vs pre-built image expectations
5. Read `infra/caddy/Caddyfile` — understand which services Caddy proxies to

## Suggested Implementation Order

Build these in order after discovery:

1. Complete `infra/compose/prod/docker-compose.yml` — fill in all missing service definitions
2. Create `infra/systemd/stormlead.service`
3. Create `scripts/deploy.sh`
4. Validate prod compose: `docker compose --env-file .env.example -f infra/compose/prod/docker-compose.yml config --quiet`
5. Docs/runbooks/readiness checklist.
6. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `infra/compose/prod/docker-compose.yml` has all services with pinned `ghcr.io/stormlead/` image tags
2. All services have `restart: unless-stopped` and JSON logging driver
3. No hardcoded credentials in prod compose — only `${ENV_VAR}` references
4. `infra/systemd/stormlead.service` exists with correct `WorkingDirectory` and `EnvironmentFile`
5. `scripts/deploy.sh` exists with `#!/bin/bash`, `set -euo pipefail`, `docker compose pull`, `up -d`, and health check curls
6. `docker compose --env-file .env.example -f infra/compose/prod/docker-compose.yml config --quiet` exits 0
7. No secrets or `.env` files are staged.
8. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `infra/compose/dev/docker-compose.yml`
- `infra/compose/prod/docker-compose.yml`
- `.env.example`
- `infra/caddy/Caddyfile`

## Likely Changed Files

- `infra/compose/prod/docker-compose.yml` (complete from skeleton)
- `infra/systemd/stormlead.service` (NEW)
- `scripts/deploy.sh` (NEW)

## Validation Suite

Required validation:

- `docker compose --env-file .env.example -f infra/compose/prod/docker-compose.yml config --quiet`
- `git diff --check`
