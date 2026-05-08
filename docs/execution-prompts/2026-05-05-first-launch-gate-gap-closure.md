# First Launch Gate Gap Closure Execution Prompt

Date: 2026-05-05

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to turn the current StormLead repo into a verified local first-launch-gate slice. This prompt is built from the gap list that starts with buyer CRM, territory matching, lead-class routing, admin KPIs, buyer reports, landing/capture, and production compose safety.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer closing StormLead's first technical launch gate for a local, synthetic, self-hosted lead marketplace proof.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

## Important Discovery Rule

The source gap list may be stale. Do not blindly rebuild items that already exist.

Start by auditing the current repo against each gap. For every item, classify it as:

- `implemented and verified`
- `implemented but missing docs/tests/evidence`
- `partially implemented`
- `missing`
- `unsafe/out of scope for local launch gate`

Only implement the smallest missing or incomplete slices needed for this milestone. If a feature already exists, add or repair verification, docs, or evidence instead of duplicating code.

Current implemented-base hypotheses to re-verify:

- `services/form-receiver` captures form leads, writes intake audit rows, and persists campaign/source attribution.
- `libs/stormlead_db` has buyer, lead, ping/post, billing, review, attribution, and workflow transition tables.
- `services/ping-post` has auction routing, buyer create/list/update/wallet endpoints, admin KPI endpoints, buyer daily report endpoint, launch-readiness endpoint, and `/admin` operator UI.
- `services/ping-post/src/ping_post/auction.py` includes lead-class, target-zip, service, daily-cap, monthly-budget, and wallet eligibility checks.
- `docs/research/v1-paid-pilot-runbook.md` documents local buyer controls, attribution, readiness, and evidence commands.
- `apps/landing`, `infra/compose/prod`, CI/CD, call tracking, mailer export, and voice bridge may still be missing or only represented by milestone prompts.

Use these as starting hypotheses, not truth. Verify against source, tests, migrations, docs, and command output before editing.

## Goal

Close the first technical launch gate for one local synthetic market:

StormLead can prove, with local code and evidence only, that three funded buyers in one market can be configured with services, target zips, exclusive zips, wallet balances, lead prices, daily caps, and monthly budgets; eligible class A/B homeowner leads with campaign attribution can route only to matching funded buyers; class C/D leads do not auto-route; admin and buyer reports show the resulting money and lead flow; and the production/config path fails closed for unimplemented public surfaces.

## Out Of Scope

- Real homeowners, real buyers, real calls, real ads, real mailers, real payments, or public webhooks.
- Full buyer portal.
- Full AI voice automation or production `voice-bridge`.
- Automated Google/Meta ad buying.
- Automated payment/refill rails.
- Production deployment to a public host.
- Rewriting ping-post in another language.
- Large CRM features beyond the fields, endpoints, and checks needed for launch-gate proof.

## Non-Negotiable Milestone Outcome

At the end of the session, a reviewer must be able to verify from code, tests, local service output, docs, admin UI, and evidence that StormLead can:

- Create or seed at least three active funded synthetic buyers in one market.
- Store each buyer's service list, target zips, exclusive zips, lead price, wallet balance, daily cap, monthly budget, low-balance threshold, sales stage, notes, and next follow-up where the current schema supports it.
- Block exclusive zip conflicts before activation or update.
- Capture or seed a homeowner lead with requested service, zip, lead class, qualification reason, campaign id, campaign source, first-touch source, and last-touch source.
- Auto-route only class A and class B leads.
- Hold or reject class C and class D leads from automatic sale.
- Select buyers only when status, wallet, target zip, service, daily cap, monthly budget, and price checks pass.
- Re-check buyer affordability and status before wallet debit.
- Write post result, billing, and audit/transition rows for successful local delivery.
- Produce admin KPIs for prepaid cash, active buyers, sold lead revenue, buyer adjustments, and campaign margin or clearly documented zero/null values when no source data exists.
- Produce a buyer daily report with delivered leads, reviewed adjustments, wallet balance, low-balance state, cap remaining, and refill recommendation.
- Provide one local homeowner acquisition surface or capture path that preserves campaign/source attribution. A single local landing page is enough; pSEO generation can remain out of scope.
- Validate production-like Compose/Caddy routing config without public exposure, with unimplemented services failing closed and no public database/admin ports.

## Milestone-Specific Rules

- Treat `docs/research/README.md` next build sequence as the product priority order, but verify current code first.
- Prefer fixing existing V1 code and tests over creating new parallel endpoints.
- If `apps/landing` is missing, build the smallest local landing app that captures attribution into the existing form-receiver path. Do not add a frontend framework unless the repo already requires one.
- If buyer CRM fields are already partly represented in `BuyerRow`, do not rename or duplicate them. Add only missing fields required by the acceptance criteria.
- If admin KPI or buyer report endpoints already exist, strengthen their tests, docs, or evidence rather than adding alternate endpoints.
- If production compose is a placeholder, add only a config-checkable local/prod compose and Caddy route inventory that exposes implemented public services and fails closed for the rest.
- No test, fixture, seed, or prompt may imply commercial paid launch approval. Keep all generated data synthetic and local.

## Parallel Subagent Protocol

After initial inspection, launch read-only subagents only if the agent host supports safe independent subagents. The main agent owns all edits, integration, validation, and final synthesis.

Useful independent workstreams:

1. Gap audit: compare the Claude gap list, `docs/research/README.md`, V1 runbook, execution prompts, and current source.
2. Buyer/routing: inspect buyer schema, buyer endpoints, auction eligibility, wallet debit, and cap enforcement.
3. Lead capture: inspect form-receiver, attribution fields, landing app state, and capture tests.
4. Reporting/admin: inspect KPI endpoints, buyer daily report, admin UI, and Playwright coverage.
5. Production/config: inspect dev/prod compose, Caddy routes, CI placeholder state, and backup/restore docs.
6. Validation: identify the smallest test and smoke commands that prove the local launch gate.

Subagent output contract:

1. Existing facts: exact files/functions/endpoints/tables found.
2. Missing or weak pieces: only repo-verified gaps.
3. Minimal edits: smallest changes needed, with file paths.
4. Tests/evidence: exact commands or assertions to add/update.
5. Risks/blockers: only real blockers.
6. Do-not-do list: overbuilds or unsafe actions to avoid.

## Suggested Implementation Order

1. Inspect current dirty state and protect unrelated user/agent changes.
2. Build a launch-gate gap matrix from verified repo facts.
3. Close Phase 1 auction gaps first: buyer CRM fields/endpoints, territory/service matching, cap/budget checks, lead-class routing, admin KPI, buyer daily report.
4. Close the smallest Phase 2 capture gap: local landing or capture path with attribution.
5. Add or repair local launch-readiness checks for funded buyer coverage and campaign budget guardrails.
6. Add or repair production/config proof: Compose/Caddy route inventory, private/admin port stance, and implemented-service-only public routing.
7. Update docs/runbooks and operator evidence instructions.
8. Run targeted tests after each slice, then the final validation suite.
9. Use Browser Use or Playwright local browser proof for any admin, landing, or operator UI touched.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. The launch-gate gap matrix exists in docs or final handoff and each gap is classified with repo evidence.
2. Buyer records support launch-gate CRM/routing fields or the prompt documents the exact existing equivalent fields.
3. Buyer create/update/list/wallet/summary or daily-report paths cover target zips, exclusive zips, services, caps, budget, wallet, low-balance threshold, stage, notes, and follow-up where supported.
4. Exclusive zip conflicts are rejected deterministically before activation or update.
5. Ping-post eligibility checks lead class, buyer status, wallet balance, target zip, service, daily cap, monthly budget, and price before buyer selection.
6. Wallet debit re-checks status and affordability in the paid delivery path.
7. Class A/B leads can route locally; class C/D leads cannot auto-route.
8. Lead capture persists campaign/source attribution from the real local capture path or a documented synthetic smoke path.
9. Admin KPI endpoint returns real DB-backed values for prepaid cash, active buyers, sold lead revenue, buyer adjustments, and campaign margin, or honest zero/null values with reasons when rows do not exist.
10. Buyer daily report returns real DB-backed delivered leads, adjustments, wallet balance, cap remaining, low-balance state, and refill recommendation.
11. Local launch-readiness blocks campaign spend when funded buyer coverage is missing.
12. A single local homeowner acquisition surface or documented local capture workflow exists and is tested for attribution.
13. Prod/config proof validates Compose/Caddy routing locally without public exposure and with unimplemented services failing closed.
14. Relevant docs explain how to run and verify the local first launch gate.
15. Generated screenshots, traces, logs, and manifests remain under ignored `testing/` paths.
16. No secrets or `.env` files are staged.
17. Required validation passes, or the final response starts with `Not complete:` and gives exact blockers with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `docs/research/README.md`
- `docs/research/v1-paid-pilot-runbook.md`
- `docs/execution-prompts/2026-05-04-v1-execution-prompt.md`
- `libs/stormlead_db/src/stormlead_db/tables.py`
- `libs/stormlead_db/migrations/versions/`
- `services/ping-post/src/ping_post/api.py`
- `services/ping-post/src/ping_post/auction.py`
- `services/form-receiver/src/form_receiver/`
- `scripts/smoke_e2e.py`
- `tests/playwright/`
- `apps/`
- `infra/compose/dev/docker-compose.yml`
- `infra/compose/prod/`
- `infra/caddy/Caddyfile`
- `.github/workflows/`

## Likely Changed Files

Only edit files whose current state proves a gap. Likely candidates include:

- `libs/stormlead_db/src/stormlead_db/tables.py`
- `libs/stormlead_db/migrations/versions/*.py`
- `services/ping-post/src/ping_post/api.py`
- `services/ping-post/src/ping_post/auction.py`
- `services/ping-post/tests/`
- `services/form-receiver/src/form_receiver/`
- `services/form-receiver/tests/`
- `apps/landing/`
- `infra/compose/prod/`
- `infra/caddy/Caddyfile`
- `scripts/smoke_e2e.py`
- `tests/playwright/`
- `docs/research/v1-paid-pilot-runbook.md`
- `docs/research/current-milestone-validation.md`

## Validation Suite

Run the smallest meaningful checks during implementation, then run the required final suite before final handoff.

Required final validation:

```powershell
git status --short --branch
docker compose --env-file .env.example -f infra/compose/dev/docker-compose.yml config --quiet
uv run ruff check services libs scripts/smoke_e2e.py scripts/replay_lead.py scripts/simulate_v1_leads.py
uv run pytest -q services libs
uv run mypy services libs
uv run python scripts/smoke_e2e.py
uv run python scripts/simulate_v1_leads.py
npm run test:playwright -- --project=chromium --reporter=line
git diff --check
```

Also run these when relevant:

```powershell
docker compose --env-file .env.example -f infra/compose/prod/docker-compose.yml config --quiet
npm run validate:codex
npm run mcp:stormlead:check
npm run mcp:stormlead:smoke
```

If a required command cannot run because of Docker availability, missing local services, network restrictions, or sandbox/tool limits, record the exact blocker and run the best local fallback. Do not claim 100/100 unless the 100% completion contract from the master prompt is satisfied.

## Browser Proof

Use Browser Use for visible local proof if available and any UI was touched. If Browser Use is unavailable, use Playwright evidence and state the Browser Use blocker.

Minimum visible workflows when UI is touched:

- Admin `/admin`: buyer roster, wallet/KPI cards, launch readiness, buyer daily report or link, and any changed review/report controls.
- Landing/capture page if implemented: local page loads, attribution params are preserved, and the capture path reaches form-receiver or the documented local stub.

Store screenshots, traces, videos, and manifests under ignored `testing/` paths.

## Final Response

Final response must include:

- Completion score out of 100, with `100/100` only if the master prompt's 100% contract is met.
- What changed and why.
- Launch-gate gap matrix summary.
- Changed files.
- Exact validation commands and results.
- Browser Use or Playwright workflows exercised, local URLs visited, roles/users used, and evidence paths.
- Safety constraints preserved.
- Reusable learnings captured and where, or `none`.
- Prompt/code logic improvements made, or why none were needed.
- Known risks, incomplete work, and exact blockers.
- No commit hash unless the user explicitly requested a commit and one was created.
