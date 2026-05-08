# Tool Routing

This project uses a small, local-first tool loadout. Add or enable more tools only when the repo cannot answer the task with its existing scripts, tests, docs, and source code.

## Default Order

1. Read the relevant source, tests, and docs in this repo.
2. Run targeted repo scripts or tests.
3. Use official/vendor docs for external APIs or platform behavior.
4. Use MCP tools only when they provide a concrete advantage for the current task.
5. Add new automation only when it will be reused.

## Browser Proof

- Use Playwright for visible admin and workflow proof.
- Use Codex App in-app browser only for local unauthenticated previews, visual comments, and small UI iterations; it does not replace required Playwright proof.
- Keep generated screenshots, videos, traces, and evidence manifests under `testing/`.
- Do not replace headed browser proof with route mocks or direct database setup.
- Main command: `npm run test:playwright -- --project=chromium --reporter=line`.
- Cowork demo command: `npm run cowork:admin:record`.

## Docker And Kubernetes MCP

- Project MCP config lives in `opencode.json`, `.codex/config.toml`, `tools/mcp/`, and `.docker/`.
- The custom StormLead Local Ops MCP is started by `npm run mcp:stormlead` and documented in `tools/mcp/README.md`.
- Import profiles with `docker mcp profile import .docker/mcp-profile-docker.json` and `docker mcp profile import .docker/mcp-profile-kubernetes.json`.
- OpenCode starts MCP servers from `opencode.json`.
- Codex starts MCP servers from `.codex/config.toml` after the project is trusted.
- Docker MCP is for docs, image lookup, and local/dev inspection first.
- Kubernetes MCP is read-only/local-dev first. Confirm context before any action that changes cluster state.
- Default Docker/Kubernetes MCP profiles should stay inspect-first allowlists; do not enable mutation tools without explicit approval.
- Ask for explicit approval before deleting containers, volumes, images, namespaces, clusters, or applying Kubernetes manifests.

## Codex

- Codex reads `AGENTS.md` for repo-local instructions.
- Codex project config is `.codex/config.toml`; keep it credential-free and project-safe.
- Codex CLI is installed as the repo dev dependency `@openai/codex`; use npm scripts instead of requiring a global `codex` install.
- Use `npm run codex` for normal interactive work, `npm run codex:app` for Codex Desktop/in-app browser workflows, `npm run codex:readonly` for inspection, `npm run codex:exec -- "<prompt>"` for non-interactive tasks, and `npm run codex:review` for local review.
- Use `npm run codex:mcp:list` or `/mcp` in the Codex TUI to inspect active MCP servers.
- Do not put user-level model preferences, auth tokens, or machine-specific paths in `.codex/config.toml`.

## Safety Rules

- Never commit secrets, `.env`, kubeconfigs, cookies, auth headers, payment keys, or provider tokens.
- Runtime LLM calls must go through the LiteLLM proxy; do not add direct OpenAI/Anthropic SDK calls to services.
- Commercial launch remains blocked unless the user explicitly approves real-world activation and the code/config gate supports it.
- Prefer a small MCP loadout; remove unused tool dependencies instead of accumulating them.

## Common Commands

- Compose config: `docker compose --env-file .env.example -f infra/compose/dev/docker-compose.yml config --quiet`.
- Codex config: `npm run validate:codex`.
- Codex CLI: `npm run codex`.
- Codex App/browser: `npm run codex:app`.
- Codex non-interactive: `npm run codex:exec -- "Review the current diff"`.
- StormLead MCP syntax check: `npm run mcp:stormlead:check`.
- StormLead MCP smoke: `npm run mcp:stormlead:smoke`.
- Markdown/config sanity: `git diff --check`.
- Ruff: `uv run ruff check services libs scripts/smoke_e2e.py scripts/replay_lead.py scripts/simulate_v1_leads.py`.
- Mypy: `uv run mypy services libs`.
- Tests: `uv run pytest -q services libs`.
- Smoke: `uv run python scripts/smoke_e2e.py`.
- V1 simulation: `uv run python scripts/simulate_v1_leads.py`.
- Playwright: `npm run test:playwright -- --project=chromium --reporter=line`.
