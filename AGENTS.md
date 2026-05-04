# StormLead Agent Guide

Use this file as the repo-local operating guide for coding agents.

## Operating Mode

- Default target is local simulation and technical proofing, not commercial paid launch.
- Use synthetic leads and local/dev services only unless the user explicitly approves a real external action.
- Do not contact real homeowners, buyers, ad platforms, payment processors, SMS/email/phone providers, or public webhooks from this workspace.
- Keep evidence under ignored `testing/` paths and do not commit generated artifacts.
- Do not commit, push, amend, rewrite history, or run destructive Git commands unless the user explicitly asks.

## Tool Routing

- Start with existing code, scripts, tests, and docs before adding new tools.
- Prefer official vendor documentation and repo-local scripts over community tool packs.
- Use Playwright for browser proof and screenshots; do not replace browser proof with mocked API setup.
- Use Docker Compose for local service orchestration. Treat Docker/Kubernetes MCP access as inspect-first and local/dev by default.
- OpenCode reads `opencode.json`; Codex reads `.codex/config.toml` after the project is trusted. Both use the same Docker MCP profile exports in `.docker/`.
- Codex CLI is available through repo npm scripts: `npm run codex`, `npm run codex:readonly`, and `npm run codex:exec -- "<prompt>"`.
- StormLead Local Ops MCP lives in `tools/mcp/` and exposes local read tools plus explicitly confirmed synthetic smoke/simulation tools.
- Ask before destructive or production-like Docker/Kubernetes actions, including deleting volumes, deleting clusters, applying manifests, or changing remote contexts.
- Keep credentials in local secret stores or `.env` files that are ignored. Never commit tokens, auth headers, cookies, kubeconfigs, cloud credentials, or payment keys.

## Validation

- Python quality gate: `uv run ruff check services libs scripts/smoke_e2e.py scripts/replay_lead.py scripts/simulate_v1_leads.py`.
- Python tests: `uv run pytest -q services libs`.
- Type checks: `uv run mypy services libs`.
- Local smoke: `uv run python scripts/smoke_e2e.py`.
- V1 simulation: `uv run python scripts/simulate_v1_leads.py`.
- Browser proof: `npm run test:playwright -- --project=chromium --reporter=line`.
- Codex config check: `npm run validate:codex`.
- StormLead MCP smoke: `npm run mcp:stormlead:smoke`.
