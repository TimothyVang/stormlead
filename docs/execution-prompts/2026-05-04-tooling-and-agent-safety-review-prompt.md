# Tooling And Agent Safety Review Execution Prompt

Date: 2026-05-04

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Tooling And Agent Safety Review`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Tooling And Agent Safety Review` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

Current implemented base includes:

- Repo-local agent rules in `AGENTS.md`.
- StormLead-specific tool routing in `tools/TOOLS.md`.
- StormLead Local Ops MCP docs and implementation under `tools/mcp/`.
- Codex/OpenCode MCP configuration in `.codex/config.toml`, `opencode.json`, and `.docker/`.
- Reusable execution prompts under `docs/execution-prompts/`.

Current stack constraints:

- Python-first.
- FastAPI.
- Postgres.
- Alembic.
- Hatchet.
- LiteLLM only for model calls.
- Playwright for real, visible browser workflows.
- Docker Compose for dev and prod.
- No mocked production behavior.
- No fake KPI, buyer, lead, campaign, billing, or workflow data outside explicit test/seed paths.
- No TODO stubs shipped as complete.
- Every agent/workflow/business decision that affects paid delivery must be persisted for audit.
- Every completed task must include runnable code, tests or documented verification, docs, and validation evidence.

Goal:

`Review StormLead's agent/tooling documentation and local MCP configuration, then make the smallest docs/config improvements needed so future agents consistently choose the right tools, preserve local simulation safety, and know how to verify their work.`

Out of scope:

- Do not change StormLead runtime service code unless a documentation command is provably wrong because of a code/config mismatch.
- Do not add new MCP servers, dependencies, background agents, browser agents, computer-use agents, queues, databases, or auth flows.
- Do not install, clone, or run external Suna/OpenHands/OpenManus/OpenClaw/Agent OS repos.
- Do not contact real homeowners, buyers, ad platforms, payment processors, SMS/email/phone providers, public webhooks, or production services.
- Do not commit unless the user explicitly asks.

Milestone-safe examples:

- Clarify wording in `AGENTS.md`, `tools/TOOLS.md`, MCP docs, or execution prompt docs.
- Fix stale validation command references when `package.json` proves the documented command is wrong.
- Link docs instead of duplicating large safety sections across multiple files.

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Route future agents through local code, scripts, tests, and docs before extra tools.
- Keep StormLead Local Ops MCP narrow, local, redacted, read-mostly, and synthetic-confirmed for command tools.
- Keep Docker/Kubernetes MCP guidance inspect-first and local/dev by default, with explicit approval before destructive or production-like actions.
- Keep execution prompts inheriting `docs/execution-prompts/master-agent-execution-prompt.md`.
- Verify docs/config/MCP changes with documented commands.

Execution mode:

- Finish this milestone in one continuous pass if technically possible.
- Do not stop after each task for approval unless user approval is required by `AGENTS.md` or the master prompt.
- Use parallel subagents or parallel tool calls after initial inspection only when scopes are independent and safe to merge.
- The main agent owns final architecture decisions, code integration, validation, docs, and final response.
- Subagents may research and propose implementation details, but the main agent must verify all findings directly before editing.
- Only ask the user for clarification if there is a real product ambiguity, paid dependency choice, destructive action risk, production/external-action risk, or credential gap with no local fallback.
- Prefer the smallest correct vertical slice over broad scaffolding.
- A task is not done when an endpoint, doc, or UI exists; it is done only when backed by real repo behavior, documented, and validated.
- Do not commit unless the user explicitly asks.

Quality bar:

- Build vertical, working slices instead of broad scaffolding.
- Prefer readable boring code over clever abstractions.
- Keep new names, tables, dependencies, tools, and services to the minimum needed.
- Write tests against behavior, not implementation details.
- Treat generated Playwright evidence as local artifacts, not source files.
- Keep production runtime independent from Playwright test-only code.
- Browser automation for operator evidence must be visible/headed when UI behavior matters.
- Do not expose admin mutation endpoints publicly without auth or private ingress.
- Do not add new cloud dependencies unless the milestone cannot be validated with a local/manual path and the user approves.

Milestone-specific rules:

- Preserve LiteLLM-only runtime guidance.
- Preserve synthetic local simulation constraints.
- Preserve generated-evidence guidance under ignored `testing/` paths.
- Preserve secret, token, cookie, auth-header, kubeconfig, cloud credential, payment key, and `.env` protections.
- Prefer `AGENTS.md` for repo-local operating rules, `tools/TOOLS.md` for StormLead-specific tool routing, and `docs/execution-prompts/master-agent-execution-prompt.md` for reusable long-horizon prompt rules.

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents. Ask each subagent to return concise findings with file paths, recommended edits, risks, and test targets. Do not let subagents commit or edit overlapping files.

Required workstreams:

1. Agent instruction consistency across `AGENTS.md` and execution prompts.
2. StormLead tool-routing consistency across `tools/TOOLS.md`, MCP docs, and package scripts.
3. MCP safety review for `tools/mcp/stormlead-local-ops.mjs` and `tools/mcp/README.md`.
4. Codex/OpenCode/Docker/Kubernetes config review for credential-free, local/dev, inspect-first behavior.
5. Validation command alignment across docs and `package.json`.

Subagent output contract:

1. Existing facts: files/functions/endpoints/tables/docs found, with paths.
2. Minimal implementation: smallest set of edits that satisfies this workstream.
3. Tests to add/update: exact test files, commands, or assertions.
4. Risks/blockers: only real blockers, not speculative concerns.
5. Do-not-do list: changes that would overbuild or violate constraints.

## Suggested Implementation Order

Build these in order after discovery:

1. Inspect `AGENTS.md`, `tools/TOOLS.md`, MCP docs/config, execution prompts, and `package.json`.
2. Identify contradictions, stale commands, or duplicated safety rules that could confuse future agents.
3. Apply the smallest docs/config wording fixes.
4. Update execution-prompt index or master template only if inheritance or usage guidance is unclear.
5. Run required validation commands.
6. Docs/runbooks/readiness checklist.
7. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `AGENTS.md`, `tools/TOOLS.md`, `tools/mcp/README.md`, `.codex/config.toml`, `opencode.json`, and `docs/execution-prompts/` have no obvious contradictory safety/tool-routing guidance.
2. Execution prompt docs clearly say future milestone prompts should inherit `docs/execution-prompts/master-agent-execution-prompt.md`.
3. MCP, Docker, Kubernetes, browser proof, LiteLLM, secrets, generated evidence, and local simulation safety guidance is consistent across reviewed docs/config.
4. Validation commands for docs/config/MCP changes match `package.json` and are run.
5. Any changes are minimal and limited to docs/config unless a direct mismatch requires a tiny config fix.
6. Relevant docs explain exactly how to use or operate the changed behavior.
7. Generated screenshots, videos, traces, manifests, and logs remain uncommitted under ignored `testing/` paths.
8. No secrets or `.env` files are staged.
9. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `tools/TOOLS.md`
- `tools/mcp/README.md`
- `tools/mcp/stormlead-local-ops.mjs`
- `opencode.json`
- `.codex/config.toml`
- `.docker/README.md`
- `package.json`
- `docs/execution-prompts/README.md`
- `docs/research/README.md`

## Likely Changed Files

- `AGENTS.md`
- `tools/TOOLS.md`
- `tools/mcp/README.md`
- `docs/execution-prompts/README.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `.codex/config.toml`
- `opencode.json`

## Validation Suite

Run the smallest relevant checks during implementation, then run the required final suite before final handoff.

Required validation:

- `npm run validate:codex`
- `npm run mcp:stormlead:check`
- `npm run mcp:stormlead:smoke`
- `git diff --check`

Use these common commands when relevant:

- `docker compose --env-file .env.example -f infra/compose/dev/docker-compose.yml config --quiet`
- `uv run ruff check services libs scripts/smoke_e2e.py scripts/replay_lead.py scripts/simulate_v1_leads.py`
- `uv run pytest -q services libs`
- `uv run mypy services libs`
- `uv run python scripts/smoke_e2e.py`
- `uv run python scripts/simulate_v1_leads.py`
- `npm run test:playwright -- --project=chromium --reporter=line`
- `npm run validate:codex`
- `npm run mcp:stormlead:check`
- `npm run mcp:stormlead:smoke`

## Final Response

Final response must include:

- Completion score or readiness label if the milestone defines one.
- Exact validation commands and results.
- Changed files.
- Evidence paths if generated.
- Safety constraints preserved.
- Any local-only caveats.
- Clear statement of whether the milestone is complete or still blocked by technical work.
- Commit hash only if the user explicitly requested a commit and one was created.
