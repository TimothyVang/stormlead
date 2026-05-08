# Finish Lead Gen With Self-Learning Automation Execution Prompt

Date: 2026-05-06

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt to finish StormLead as a verified local lead-generation system with autonomous evidence loops, browser automation, MCP local ops, and runner prompts that keep improving the app from observed failures.

## Copy/Paste Prompt

```markdown
Operational mode for this request: build StormLead end-to-end until the local synthetic lead-gen system is complete or a real blocker is documented. Do not stop at planning. You may inspect files, edit code/docs/tests, run local commands, use local MCP tools, run browser automation, and generate or dispatch local runner prompts within the safety limits below.

You are a senior staff engineer inside this repository:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

Start by applying `AGENTS.md` and `docs/execution-prompts/master-agent-execution-prompt.md`.

## Mission

Finish StormLead as a local-first, self-hosted storm/tree-removal lead-gen engine that can prove the complete synthetic funnel:

- Detect or seed local storm-market demand.
- Capture homeowner leads with attribution.
- Enrich and qualify leads through LiteLLM-routed agent-runtime logic.
- Route class A/B leads through ping-post only to eligible funded synthetic buyers.
- Hold/reject class C/D or unsafe leads from automatic sale.
- Show operator/admin evidence for buyers, lead timelines, KPIs, returns, reports, readiness, and workflow health.
- Continuously improve through a THINK -> ACT -> OBSERVE -> DECIDE loop using MCP, Playwright, Puppeteer/Lighthouse, tests, and runner prompts.

This is not approval for real launch. The default target is local simulation and technical proof only.

## Hard Limits

- Use synthetic leads, synthetic buyers, local/dev services, and loopback browser targets only.
- Do not contact real homeowners, buyers, ad platforms, payment processors, SMS/email/phone providers, or public webhooks.
- Do not deploy, expose public services, buy ads, send real outreach, run real payments, or trigger production infrastructure.
- Do not modify `.env` files or commit secrets.
- Do not commit, push, amend, rewrite history, or run destructive git commands unless the user explicitly asks.
- Keep generated evidence under ignored `testing/` paths.
- Runtime LLM service calls must go through LiteLLM. Do not add direct provider SDK runtime calls.
- Browser automation must target `127.0.0.1`, `localhost`, or explicit local dev URLs.

## Starting Inputs

Read these first:

- `AGENTS.md`
- `README.md`
- `testing/README.md`
- `tools/mcp/README.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `docs/execution-prompts/2026-05-05-first-launch-gate-gap-closure.md`
- `docs/research/README.md`
- `docs/research/v1-paid-pilot-runbook.md`
- `docs/research/2026-05-04-project-improvement-plan.md`
- `package.json`
- `tools/mcp/stormlead-local-ops.mjs`
- `scripts/self_learning_loop.mjs`

Then inspect current implementation only as needed:

- `libs/stormlead_db/src/stormlead_db/tables.py`
- `libs/stormlead_db/migrations/versions/`
- `services/form-receiver/src/form_receiver/`
- `services/storm-watcher/src/storm_watcher/`
- `services/enrich-worker/src/enrich_worker/`
- `services/agent-runtime/src/agent_runtime/`
- `services/ping-post/src/ping_post/`
- `scripts/smoke_e2e.py`
- `scripts/simulate_v1_leads.py`
- `tests/playwright/`
- `infra/compose/dev/docker-compose.yml`
- `infra/compose/prod/`
- `infra/caddy/Caddyfile`
- `.github/workflows/`

## Self-Learning Loop Model

Use this loop throughout the session. Every iteration must produce a visible artifact in `testing/runs/` or the final handoff.

1. THINK: state current evidence, current gap, hypothesis, and smallest next action.
2. ACT: run one focused command, browser proof, MCP tool, file edit, or runner dispatch.
3. OBSERVE: read the output, screenshot, trace, browser log, service log, or test result.
4. DECIDE: either fix the smallest verified gap, create a runner prompt, add regression proof, or declare a blocker.

Use the built-in loop as the main evidence spine:

```powershell
npm run learn:loop
npm run learn:loop:api
npm run learn:loop:full
```

MCP equivalent when available:

```text
run_self_learning_loop(confirm_synthetic_local=true)
```

The loop writes `testing/runs/<run-id>-self-learning-loop/` with `self-learning-summary.json`, `self-learning-loop.md`, per-iteration notes, browser logs, optional Puppeteer/Lighthouse reports, and `runner-prompts/`.

Do not treat Playwright, Puppeteer, or MCP as the reasoning layer. They are evidence tools. The self-learning behavior comes from reading evidence, updating hypotheses, editing the smallest verified gap, and rerunning focused checks.

## Runner Dispatch Rules

Use runners to improve the app only when they are bounded by evidence.

Allowed runner types:

- Read-only investigator: inspect code, logs, evidence, docs, and tests; return facts with file paths and line numbers.
- Minimal fix runner: implement the smallest verified code/test/docs change for one gap; run the narrowest validation.
- Regression runner: convert verified behavior or a reproduced bug into deterministic tests and browser evidence.
- QA runner: attempt to disprove completion using local-only tests, MCP checks, and browser proof.

Runner safety rules:

- Main agent owns integration, final edits, and final verification.
- Do not dispatch vague “improve the app” runners. Every runner must receive exact observed findings and return exact files/commands/results.
- Do not run more than three runners in parallel unless the user explicitly asks.
- Do not let runners contact public services or real people.
- Do not let runners commit, push, rewrite history, or touch secrets.
- Runner prompts belong under `testing/runs/<run-id>/runner-prompts/` unless they become durable docs.
- If using Codex runner dispatch, prefer generated prompt files and keep dispatch local:

```powershell
npm run codex:exec -- "<bounded prompt>"
```

The self-learning loop can dispatch Codex only when explicitly requested:

```powershell
npm run learn:loop -- --dispatch-codex true --max-runners 1
```

## Execution Phases

### Phase 0 - Baseline And Gap Matrix

Build a gap matrix before implementation. Classify each area as `implemented and verified`, `implemented but missing proof`, `partial`, `missing`, or `unsafe/out of scope`.

Areas:

- Local Docker/dev service boot path.
- Database migrations and seed/synthetic data path.
- Storm event watcher or synthetic storm-market seeding.
- Form receiver lead capture and attribution.
- Enrichment worker and idempotent lead enrichment.
- Agent runtime qualification through LiteLLM proxy.
- Ping-post auction, buyer eligibility, wallet debit, caps, budget, lead class gating, and audit rows.
- Buyer roster, CRM fields, deposits, daily report, low-balance state, and return/review flow.
- Admin UI, KPIs, readiness gates, workflow KPIs, lead timeline, and operator actions.
- Playwright browser regression proof.
- Puppeteer/Lighthouse performance/accessibility flow proof.
- MCP local ops coverage and refusal behavior.
- CI/config/prod-compose fail-closed proof.
- Docs/runbooks/evidence handoff.

### Phase 1 - Local Stack Reliability

Make the local stack boring to start and verify.

Acceptance:

- `docker compose --env-file .env.example -f infra/compose/dev/docker-compose.yml config --quiet` passes.
- Local services expose expected `/healthz` and `/readyz` checks.
- `npm run mcp:stormlead:smoke` passes.
- `check_local_services` reports healthy services after the stack is started, or the blocker is exact.

### Phase 2 - Synthetic Lead Funnel

Finish capture -> enrichment -> qualification -> auction -> delivery/hold evidence.

Acceptance:

- Synthetic lead capture preserves campaign/source attribution.
- Enrichment and qualification are idempotent and auditable.
- Agent runtime uses LiteLLM proxy only.
- Class A/B leads can route locally to eligible funded buyers.
- Class C/D leads do not auto-sell.
- Buyer eligibility checks status, service, target zip, exclusive zip, wallet, lead price, daily cap, monthly budget, and lead class before sale.
- Wallet debit re-checks affordability/status before mutation.
- State transitions and workflow audit rows are visible through local admin/timeline APIs.

### Phase 3 - Buyer And Operator Surfaces

Finish buyer/admin functionality needed for one local market.

Acceptance:

- At least three synthetic funded buyers can be created or seeded in one market.
- Buyer create/update/list/deposit/report paths expose services, target zips, exclusive zips, caps, monthly budget, wallet, low-balance threshold, sales stage, notes, and follow-up fields where schema supports them.
- Exclusive zip conflicts are rejected deterministically.
- Admin KPIs show prepaid cash, active buyers, sold revenue, returns/adjustments, and campaign margin or honest zero/null states.
- Buyer daily report shows delivered leads, adjustments, wallet balance, cap remaining, low-balance state, and refill recommendation.
- Return/review flow is auditable and browser-visible.

### Phase 4 - Automation And Regression Proof

Convert meaningful behavior into deterministic tests and browser proof.

Acceptance:

- Python quality gate passes or exact blocker is documented:

```powershell
uv run ruff check services libs scripts/smoke_e2e.py scripts/replay_lead.py scripts/simulate_v1_leads.py
uv run mypy services libs
uv run pytest -q services libs
```

- Local smoke and V1 simulation pass or exact blockers are documented:

```powershell
uv run python scripts/smoke_e2e.py
uv run python scripts/simulate_v1_leads.py
```

- Playwright proof passes for API and touched UI flows:

```powershell
npm run test:playwright -- --project=api --reporter=line
npm run test:playwright -- --project=chromium --reporter=line
```

- Chrome observer functional test passes:

```powershell
npm run test:chrome-observer
```

- Self-learning loop produces an evidence folder and runner prompts:

```powershell
npm run learn:loop:api
```

### Phase 5 - Puppeteer/Lighthouse And UX Quality

Use Puppeteer/Lighthouse for Chrome-native flow evidence where Playwright is not enough.

Acceptance:

- Puppeteer/Lighthouse flow artifacts exist under `testing/runs/`.
- Reports cover navigation, a short interaction timespan, and a snapshot.
- Accessibility/performance findings below threshold become either code fixes, regression tests, or documented follow-up blockers.
- Browser console, page errors, request failures, HTTP errors, screenshots, traces, and Lighthouse reports are read before code changes.

### Phase 6 - CI, Config, And Fail-Closed Production Readiness

Finish enough operational proof that the project is safe to keep building.

Acceptance:

- CI or documented local equivalent runs lint/type/test/browser gates.
- Dependency/security gate decision is documented; do not blindly run unsafe auto-fixes.
- Prod compose/Caddy config validates locally without public exposure.
- Unimplemented public surfaces fail closed.
- No database/admin ports are publicly exposed by production-like config.
- Docs explain what is local-ready versus not commercial-launch-ready.

## Durable Learning Rules

Persist learning only when verified by command output, code reads, tests, browser evidence, or exact blocker evidence.

Durable learning locations:

- Behavior -> tests and fixtures.
- Browser/operator proof -> Playwright/Cowork tests and `testing/README.md`.
- Local ops tools -> `tools/mcp/README.md` and MCP smoke tests.
- Self-learning process -> execution prompts and generated runner prompts.
- Product/ops decisions -> docs under `docs/research/`.
- Temporary evidence -> ignored `testing/runs/` only.

Never persist secrets, raw production payloads, contact details, auth headers, cookies, or `.env` values.

## Final Definition Of Done

You may report complete only when all are true:

- Gap matrix exists and is backed by repo evidence.
- Local synthetic funnel is implemented and verified from lead capture through buyer routing or safe hold/reject.
- Admin/buyer/operator surfaces needed for local proof are implemented and browser-tested.
- MCP local ops tools pass syntax and smoke tests.
- Self-learning loop runs and writes evidence plus runner prompts.
- Playwright evidence exists for critical browser/API flows.
- Puppeteer/Lighthouse evidence exists for at least one key app flow or a precise blocker explains why it cannot run.
- Python quality, tests, local smoke, V1 simulation, Playwright, Chrome observer, MCP smoke, and `git diff --check` have been run or have exact blockers.
- Docs/runbooks explain how to reproduce the local proof.
- No real external contact, paid action, production deployment, secret exposure, or destructive git operation occurred.

If anything is incomplete, final response must start with:

`Not complete:`

Then list every missing item with exact blocker, evidence path, and next command.

## Final Handoff Format

Return:

- Status: `complete` or `not complete`.
- Changed files grouped by feature/test/docs/tooling.
- Evidence folders under `testing/runs/`.
- Runner prompts generated or dispatched.
- Validation commands and results.
- Known risks and what remains before commercial launch.
```
