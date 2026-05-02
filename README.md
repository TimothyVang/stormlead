# stormlead

agentic storm-chase tree-removal lead-gen, fully self-hosted, python-first.

## what this is

a monorepo for a single-operator b2b lead-gen business: detect storm events, capture homeowner leads on pseo landing pages, qualify with agents, run a ping-post auction to a buyer roster of licensed tree services, and dial unsold leads via voice ai.

dev runs on windows + wsl2 with docker compose. prod runs on hetzner + proxmox + lxc/vm. push via git, deploy with docker compose under systemd.

## the moat

the **ping-post engine** in `services/ping-post/`. nothing forkable exists for this on github — boberdoo/leadconduit/leadspedia are all closed saas. that's our wedge.

## layout

```
services/
  ping-post/                fastapi, the auction engine + cel filters
  storm-watcher/            tropycal/nws/fema pollers, hatchet cron
  agent-runtime/            claude-agent-sdk workers: qualify_lead (opus, oauth) + hermes_self_evolution (weekly cron)

libs/
  stormlead_core/           shared pydantic models, cel evaluator wrapper
  stormlead_db/             sqlalchemy + alembic migrations

infra/
  compose/dev/              docker-compose for wsl2 (12 services post-cuts)
  compose/prod/             (placeholder) docker-compose for hetzner
  caddy/                    caddyfile + coraza waf rules (re-add when apps land)
  litellm/                  config.yaml (pinned image, cosign-verified)
  openbao/                  (deferred) see infra/openbao/README.md
  sql/                      bootstrap sql (postgis, timescale, pgvector)

docs/
  research/                 stack audit + integration risk register (informed the choices)

skills/                     (placeholder) hermes-style agent skills
scripts/                    (placeholder) one-shot ops
.github/workflows/          (placeholder) ci/cd
```

unimplemented yet (will return as they ship): `apps/landing`, `apps/buyer-portal`, `services/form-receiver`, `services/voice-bridge`, `services/enrich-worker`.

## quickstart (wsl2)

```bash
# 1. install uv + just (one time)
curl -LsSf https://astral.sh/uv/install.sh | sh
cargo install just

# 2. clone, env, up
cp .env.example .env
just up           # brings up the dev stack
just migrate      # runs alembic migrations
# just seed       # not yet implemented (scripts/seed_dev.py)
# just smoke      # not yet implemented (scripts/smoke_e2e.py)

# 3. dev loop
just logs ping-post
just test
```

## production (hetzner)

prod compose + deploy script are placeholders (`infra/compose/prod/`, `.github/workflows/`). add them when the first non-dev environment exists.

## known traps (read these)

1. **litellm**: pinned to a known-good image sha after the march 2026 supply-chain attack. do not `pip install litellm` anywhere. only the cosign-verified docker image. (current pin v1.83.4 is now CVE'd — bump to v1.83.7-stable; see `docs/research/2026-05-stack-improvements.md`.)
2. **claude agent sdk** ignores `ANTHROPIC_BASE_URL` from the bundled cli — set `cli_path` explicitly when `services/agent-runtime/` lands. two viable auth paths: (a) api key via litellm (default, full observability + cost caps), (b) `CLAUDE_CODE_OAUTH_TOKEN` for subscription-billed opus work that bypasses litellm. hybrid recommended; see `docs/research/2026-05-agent-auth-patterns.md`.
3. **postgres mcp**: anthropic's reference server is archived + exploitable. we use `crystaldba/postgres-mcp-pro` behind a read-only role. (pin a specific tag, not `:latest`.)
4. **suna**: not used. agent loop is direct on claude agent sdk + litellm. ~200 loc, no supabase.
5. **rust**: not used. python everywhere. rewrite ping-post hot path in go later if we cross 500 leads/sec sustained.
6. **hetzner region**: deploy to ashburn (us-east) or hillsboro (us-west). a falkenstein/helsinki box adds 150–200ms rtt to every buyer ping/post — eats the auction's <5s budget. see `docs/research/2026-05-architectural-fit.md`.
7. **nats / seaweedfs / openbao not in v1 compose**: cut after architectural-fit research. hatchet handles durable workflows on postgres; hetzner object storage replaces seaweedfs in prod; sops-encrypted `.env.prod` replaces openbao until 2nd operator. re-add any of these when a concrete need surfaces, not before.

## license

internal. not for redistribution. (no `LICENSE` file yet — decide before any external sharing.)
