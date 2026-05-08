# Sandbox Inventory

This doc is the single-source-of-truth for tools and environments available to agents working in this repo. Reach for these freely; they are designed to make wrong attempts cheap.

The sandbox is safe. The only thing that is *not* safe is real-world contact — real homeowners, real buyers, real ad platforms, production webhooks, paid actions, real SMS/email/voice providers. All experiments stay inside the sandbox.

For routing rules (which tool to prefer over which), see `tools/TOOLS.md`. This doc complements it with a symptom-to-tool reference, the active MCP loadout, and isolation patterns for safe experimentation.

## Symptom-to-Tool Reference

Reach for the cheapest tool that can illuminate the question before guessing. Default to *reaching* before *thinking*.

| Symptom or question | First tool to reach |
| --- | --- |
| What is actually in the database? | `just psql` then SQL. |
| What did a service log? | `just logs <service>` or `docker compose logs --tail=200 <service>`. |
| Is a service healthy? | `docker compose ps` then read the health column. |
| What is the workflow status? | Hatchet UI at `http://localhost:8080`. |
| Did my LLM call route correctly? | Langfuse UI at `http://localhost:3001`. |
| What does this library actually do? | `context7` MCP `query-docs`. Treat training-era memory as suspect. |
| Did my edit land? | `Read` the file or `git diff <path>`. |
| Does this code match repo conventions? | `Grep`/`Read` 1–2 sibling files in the same area. |
| Does the UI render correctly? | Browser Use snapshot against `http://127.0.0.1:8003/admin`. |
| Will this UI regress? | `npm run test:playwright -- --project=chromium --reporter=line`. |
| Will this migration apply cleanly? | Run on an ephemeral DB. See Isolation Patterns below. |
| Failing test? | `uv run pytest -x services/<svc> -k <test_name> -s` before adding prints. |
| Is Compose config valid? | `docker compose --env-file .env.example -f infra/compose/dev/docker-compose.yml config --quiet`. |
| Lead workflow correctness? | `uv run python scripts/replay_lead.py <LEAD_ID>`. |
| End-to-end correctness? | `just smoke` or `uv run python scripts/smoke_e2e.py`. |
| Are MCP tools wired? | `npm run mcp:stormlead:check` then `npm run mcp:stormlead:smoke`. |

## Active MCP Servers

Wired in `opencode.json` and `.codex/config.toml`:

- `stormlead` — local ops: KPI reads, lead timeline reads, evidence manifest reads, gated synthetic simulations. Full tool list in `tools/mcp/README.md`.
- `docker` — Docker MCP Toolkit. Inspect-first; mutation tools require explicit approval.
- `kubernetes` — Kubernetes MCP Toolkit. Read-only/local-dev first. Confirm context before any state-changing call.
- `context7` — current library/framework/SDK docs. Use whenever a library question comes up; do not rely on training-era syntax.

## Available To Wire

Not active yet but known low-cost additions worth enabling when their use case appears. Wire one only when a concrete task surfaces a need the existing loadout cannot answer.

- **Postgres MCP** (`crystaldba/postgres-mcp-pro`, pinned tag — never `:latest`): structured DB queries without dropping into psql. Closes the training-prior gap on schema assumptions.
- **Hatchet API MCP**: programmatic workflow trace inspection so the agent can read traces without screenshots.
- **Langfuse API MCP**: programmatic LLM-call trace inspection.

## Isolation Patterns

The sandbox is genuinely safe to experiment in. Use these patterns before any potentially destructive change.

### Per-session worktree

```powershell
git worktree add ../stormlead-experiment-<short> HEAD
```

Run the experiment there. If it works, cherry-pick or rebase back. If it does not, `git worktree remove`.

### Per-session Compose project

```powershell
$env:COMPOSE_PROJECT_NAME = "stormlead-experiment-<short>"
docker compose -f infra/compose/dev/docker-compose.yml up -d
# experiment
docker compose -f infra/compose/dev/docker-compose.yml down -v
```

Isolated from the default `stormlead` project, so `down -v` is always safe.

### Per-session DB

```sql
CREATE DATABASE stormlead_experiment_<short> TEMPLATE stormlead_dev;
```

Point `DATABASE_URL_HOST` at the new DB for the experiment. Drop when done.

### Per-evidence directories

- `testing/runs/<YYYY-MM-DD>-<short>/` for smoke and replay artifacts.
- `testing/browser-use/<YYYY-MM-DD>-<short>/` for Browser Use screenshots, DOM, traces, video.
- `testing/playwright/<YYYY-MM-DD>-<short>/` for Playwright traces.

All under git-ignored `testing/` paths. Reference the path in handoff; never commit the artifacts.

## Reach Defaults

These are protocol W (Tool-First Reach) made concrete. See the master execution prompt for the full Opus-Grade Cognitive Protocol.

- Schema or data question → query the DB (psql or Postgres MCP) before guessing from migrations alone.
- Library API question → `context7` query-docs before relying on training-era syntax.
- Service behavior question → `docker compose logs` before inferring from code paths alone.
- UI behavior question → Browser Use snapshot before inferring from JSX/template alone.
- Test failure → `pytest -x -s` against the specific test before adding print statements.
- Convention question → Grep/Read sibling files before writing generic code from training data.

## Safety Model

- Read/inspect MCP tools and shell commands are always safe.
- Mutation MCP tools (Docker prune, Kubernetes apply, image deletes, etc.) require explicit user approval.
- Synthetic-only data — never seed real homeowner, buyer, campaign, or billing data outside explicit test/seed paths.
- LiteLLM proxy is the only path for runtime model calls. Direct provider SDK imports are banned in services.
- Browser Use targets only `localhost`, `127.0.0.1`, or explicit local dev URLs.
- Never commit `.env`, tokens, kubeconfigs, cookies, payment keys, or generated credential config.
- Real-world activation (live ad spend, paid SMS/voice, public webhooks, payment processors) is blocked at the prompt level until explicitly approved.

For the full constraint surface, see `AGENTS.md` and `CLAUDE.md`.
