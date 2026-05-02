# stormlead

agentic storm-chase tree-removal lead-gen, fully self-hosted, python-first.

## what this is

a monorepo for a single-operator b2b lead-gen business: detect storm events, capture homeowner leads on pseo landing pages, qualify with agents, run a ping-post auction to a buyer roster of licensed tree services, and dial unsold leads via voice ai.

dev runs on windows + wsl2 with docker compose. prod runs on hetzner + proxmox + lxc/vm. push via git, deploy with docker compose under systemd.

## the moat

the **ping-post engine** in `services/ping-post/`. nothing forkable exists for this on github — boberdoo/leadconduit/leadspedia are all closed saas. that's our wedge.

## layout

```
apps/
  landing/                  next.js pseo (one repo, 50k pages from postgres)
  buyer-portal/             next.js, buyers see leads + bids + invoices

services/
  ping-post/                fastapi, the auction engine + cel filters
  storm-watcher/            tropycal/nws/fema pollers, hatchet cron
  form-receiver/            formbricks webhook → consent audit → leads
  voice-bridge/             jambonz audio.jambonz.org ws ↔ pipecat
  agent-runtime/            claude agent sdk + litellm + hermes self-evolution
  enrich-worker/            attom/regrid/florence-2 photo classifier

libs/
  stormlead_core/           shared pydantic models, cel evaluator wrapper
  stormlead_db/             sqlalchemy + alembic migrations

infra/
  compose/dev/              docker-compose for wsl2
  compose/prod/             docker-compose for hetzner
  caddy/                    caddyfile + coraza waf rules
  litellm/                  config.yaml (pinned image, cosign-verified)
  openbao/                  policies + bootstrap
  sql/                      bootstrap sql (postgis, timescale, pgvector)

skills/                     hermes-style agent skills, evolved nightly
scripts/                    one-shot ops (db restore, lead replay, etc.)
.github/workflows/          ci/cd: ssh deploy via openbao-issued certs
```

## quickstart (wsl2)

```bash
# 1. install uv + just (one time)
curl -LsSf https://astral.sh/uv/install.sh | sh
cargo install just

# 2. clone, env, up
cp .env.example .env
just up           # brings up the dev stack
just migrate      # runs alembic migrations
just seed         # loads sample buyers + a fake storm event
just smoke        # end-to-end: form → ping-post → buyer accept

# 3. dev loop
just logs ping-post
just test
```

## production (hetzner)

```bash
just deploy prod
```

ci does this for you on tag push. see `.github/workflows/deploy.yml`.

## known traps (read these)

1. **litellm**: pinned to a known-good image sha after the march 2026 supply-chain attack. do not `pip install litellm` anywhere. only the cosign-verified docker image.
2. **claude agent sdk** ignores `ANTHROPIC_BASE_URL` from the bundled cli — we set `cli_path` explicitly. see `services/agent-runtime/src/runtime.py`.
3. **postgres mcp**: anthropic's reference server is archived + exploitable. we use `crystaldba/postgres-mcp-pro` behind a read-only role.
4. **suna**: not used. agent loop is direct on claude agent sdk + litellm. ~200 loc, no supabase.
5. **rust**: not used. python everywhere. rewrite ping-post hot path in go later if we cross 500 leads/sec sustained.

## license

internal. not for redistribution. see `LICENSE`.
