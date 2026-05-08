# Agent-19: Caddy WAF Hardening Execution Prompt

Date: 2026-05-04

Wave: 3 — Run AFTER all Wave 2 agents are committed.

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-19 — Caddy WAF Hardening`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-19 — Caddy WAF Hardening` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

**Prerequisite:** All Wave 1 and Wave 2 agents are committed.

Current implemented base includes:

- `infra/caddy/Caddyfile` has Coraza WAF configured for form-receiver
- CrowdSec bouncer plugin is commented out (`# crowdsec {...}`) — needs re-enabling
- Ping-post admin routes (`/v1/admin/*`) are on dev admin port `:81` — no WAF rule
- No rate limiting is configured
- `infra/caddy/coraza/` has existing OWASP CRS rule files

Current stack constraints:

- Caddy v2 with Coraza WAF plugin and CrowdSec plugin.
- Rate limiting via Caddy rate-limit module.
- WAF rules: OWASP CRS from `infra/caddy/coraza/`.
- Admin routes must be restricted to internal network IPs (RFC1918) only.
- Do NOT expose or modify production Caddy/CrowdSec services.

Known repo learnings and memory inputs:

- CrowdSec bouncer plugin order: `order crowdsec first` in global block
- CrowdSec API URL in compose: `http://crowdsec:8080`
- Rate limit target: `/webhooks/formbricks` — 100 requests/minute per IP
- Admin WAF: restrict `/v1/admin/*` to `remote_ip 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16`
- Coraza WAF directive: `SecRuleEngine On` + `Include @owasp_crs/*.conf`

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Update `infra/caddy/Caddyfile` to: (1) re-enable CrowdSec bouncer, (2) add rate limiting to `/webhooks/formbricks`, (3) add Coraza WAF + internal-only restriction to `/v1/admin/*`.

Out of scope:

- CrowdSec dashboard or alert configuration
- TLS certificate provisioning
- Changes to Coraza rule files themselves (use existing `@owasp_crs/*.conf`)
- Caddy plugin installation (assume plugins are already in the Caddy image)
- Any production Caddy service changes

Milestone-safe examples:

- CrowdSec global block: `crowdsec { api_url http://crowdsec:8080; api_key {env.CROWDSEC_BOUNCER_KEY}; ticker_interval 15s }`
- Rate limit: `rate_limit { zone formbricks_webhooks { key {remote_host}; events 100; window 1m } }`
- Admin restrict: `@internal { remote_ip 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 }` followed by `respond @external 403`

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Read `infra/caddy/Caddyfile` and see CrowdSec block re-enabled in global config
- Read `infra/caddy/Caddyfile` and see rate limit directive on `/webhooks/formbricks`
- Read `infra/caddy/Caddyfile` and see internal-network restriction on `/v1/admin/*`
- Validate Caddyfile syntax: `docker run --rm -v $(pwd)/infra/caddy:/etc/caddy caddy:2 caddy validate --config /etc/caddy/Caddyfile`

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

- Add `CROWDSEC_BOUNCER_KEY` to `.env.example` if not present (no default value — operator must set)
- CrowdSec block must use `{env.CROWDSEC_BOUNCER_KEY}` — never hardcode the key
- The internal-only restriction for admin routes must use a named matcher (`@internal`) not inline
- Rate limiting must target the specific webhook path, not all routes
- If Caddy validate command is unavailable locally, document the exact command for operator to run

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `infra/caddy/Caddyfile` — document current structure: global block, site blocks, handle blocks, existing WAF directives
2. Read `infra/caddy/coraza/` — confirm OWASP CRS file paths referenced in Caddyfile
3. Read `infra/compose/dev/docker-compose.yml` — confirm CrowdSec service name and port
4. Read `.env.example` — find `CROWDSEC_BOUNCER_KEY` entry status
5. Read any existing Caddy docs in `docs/` for setup notes

## Suggested Implementation Order

Build these in order after discovery:

1. Update global block to re-enable CrowdSec bouncer
2. Add rate limit zone definition to global block
3. Add rate limit handler to `/webhooks/formbricks` route
4. Add internal-only restriction + Coraza WAF to `/v1/admin/*` route
5. Add `CROWDSEC_BOUNCER_KEY` to `.env.example` if missing
6. Validate Caddyfile syntax
7. Docs/runbooks/readiness checklist.
8. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `infra/caddy/Caddyfile` global block has CrowdSec block with `api_url`, `api_key {env.CROWDSEC_BOUNCER_KEY}`, and `ticker_interval`
2. Rate limit (100/min per IP) applied to `/webhooks/formbricks`
3. `/v1/admin/*` restricted to RFC1918 IP ranges with Coraza WAF enabled
4. `.env.example` has `CROWDSEC_BOUNCER_KEY` entry
5. Caddyfile syntax validates (or exact validation blocker documented)
6. No secrets or `.env` files are staged.
7. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `infra/caddy/Caddyfile`
- `infra/caddy/coraza/` (list files)
- `infra/compose/dev/docker-compose.yml` (crowdsec service)
- `.env.example`

## Likely Changed Files

- `infra/caddy/Caddyfile` (re-enable CrowdSec, add rate limit, admin WAF)
- `.env.example` (add CROWDSEC_BOUNCER_KEY if missing)

## Validation Suite

Required validation:

- `docker run --rm -v ${PWD}/infra/caddy:/etc/caddy caddy:2 caddy validate --config /etc/caddy/Caddyfile` (if Docker available)
- `git diff --check`
