# StormLead V1 Execution Prompt

Date: 2026-05-04

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to take StormLead from the current audited workflow milestone to local V1 technical readiness.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building StormLead V1: a production-ready local technical slice for a self-hosted AI lead marketplace.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

Current implemented base includes:

- FastAPI services for form capture, storm watching, enrichment, agent runtime, and ping-post.
- Postgres/Alembic schema with lead, buyer, billing, ping/post, review, and transition audit tables.
- Buyer onboarding, activation, wallet deposits, KPI cards, workflow timeline, and review actions in `/admin`.
- LiteLLM-only model execution.
- Playwright/Cowork evidence manifests under ignored `testing/runs/` paths.

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
- No fake KPI, buyer, lead, campaign, or billing data outside explicit test/seed paths.
- No TODO stubs shipped as complete.
- Every agent/workflow/business decision that affects paid delivery must be persisted for audit.
- Every completed task must include runnable code, tests, docs, and validation evidence.

Goal:

Build StormLead to local V1 technical readiness as far as code, local validation, docs, and operator evidence can prove.

V1 does not mean the full long-term platform. Do not build the full buyer portal, full AI voice automation, full payment automation, n8n/Temporal migration, automated ad buying, or large CRM unless required to satisfy a V1 technical blocker.

V1-safe examples:

- Buyer portal: add a simple buyer daily report page/export or signed read-only report link, not a full portal.
- AI voice / `voice-bridge`: add call tracking ingestion or manual call disposition, not full AI voice automation.
- Payments/refills: add manual payment-link tracking or admin-recorded refill references, not automated wallet payment rails.
- Automated ad buying: add campaign spend gate and manual launch approval, not Google/Meta automation.
- n8n: at most document a future operator checklist use; do not make it core orchestration.
- OpenBao: keep SOPS/env for solo V1 unless multiple operators or real secret rotation is required now.
- Rust/Go ping-post rewrite: only revisit after load testing proves Python misses auction latency targets.

Non-negotiable V1 outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, and evidence that StormLead can:

- Validate a production-like stack locally/config-only unless the user approves internet exposure.
- Prove Caddy/Compose route inventory would expose only implemented public routes, while keeping admin/mutation surfaces private or authenticated.
- Capture a homeowner lead with campaign/source attribution and durable audit trail.
- Verify funded buyer coverage before campaign spend can run.
- Route a qualified lead to an active funded buyer and debit the wallet.
- Record a buyer review request with evidence, review it, and adjust the wallet when approved.
- Produce a daily buyer report with sold leads, reviewed leads, wallet balance, and refill recommendation.
- Show lifecycle, buyer, billing, review, and campaign state in the admin/operator surface.
- Prove all of the above with real local services, real Postgres state, tests, docs, and browser evidence.

Execution mode:

- Finish V1 in one continuous pass if technically possible.
- Do not stop after each task for approval.
- Use parallel subagents immediately after the initial repo inspection to compress discovery and reduce missed integration points.
- The main agent owns final architecture decisions, code integration, validation, docs, and final response.
- Subagents may research and propose implementation details, but the main agent must verify all findings directly before editing.
- Only ask the user for clarification if there is a real product ambiguity, paid dependency choice, destructive action risk, or credential gap with no local fallback.
- Prefer the smallest correct vertical slice over broad scaffolding.
- A task is not done when an endpoint exists; it is done only when backed by real database state, covered by tests, documented, and validated.

Quality bar:

- Build vertical, working slices instead of broad scaffolding.
- Prefer readable boring code over clever abstractions.
- Keep new names, tables, and dependencies to the minimum needed.
- Write tests against behavior, not implementation details.
- Treat generated Playwright evidence as local artifacts, not source files.
- Keep production runtime independent from Playwright test-only code.
- Browser automation for operator evidence must be visible/headed.
- Do not expose admin mutation endpoints publicly without auth or private ingress.
- Do not add new cloud dependencies unless V1 cannot be validated with a local/manual path.

Research-backed V1 rules:

- SRE monitoring rule: expose or log the four golden signals where practical for public capture, ping-post/auction, admin mutations, and billing/review paths: latency, traffic, errors, and saturation.
- Tail-latency rule: do not rely on average latency for lead capture, auction, delivery, or admin review.
- Overload rule: public capture, webhook, and buyer-delivery paths need bounded request sizes, timeouts, retry budgets, and fast rejection for invalid or unfunded work.
- Idempotency rule: wallet debits, wallet adjustments, buyer delivery attempts, review decisions, call-tracking events, and payment/refill references must be safe under duplicate requests or retries.
- API security rule: every public/admin endpoint touched for V1 must be checked against object-level auth, function-level auth, object property exposure, resource consumption, business-flow abuse, endpoint inventory, and third-party API use.
- LLM rule: untrusted text cannot control money movement, routing, spend launch, review approval, or buyer activation without deterministic code checks plus persisted audit rows.
- Webhook rule: if payment, refill, call-tracking, buyer, or ad-platform webhooks are added, verify provider signatures where available, preserve raw body for verification, store processed event IDs or equivalent idempotency keys, tolerate duplicate/out-of-order delivery, respond quickly, and defer heavy work.
- Deployment rule: if GitHub Actions or deploy scripts are touched, use environment gates, required review or explicit manual production approval, and concurrency so only one production deploy can run.
- Saga rule: long-running marketplace flows must use append-only state transitions and compensating actions, not distributed transactions.

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently. Ask each subagent to return concise findings with file paths, recommended edits, risks, and test targets. Do not let subagents commit.

Required workstreams:

1. Production deploy, security, and ops.
2. Landing, capture, and campaign attribution.
3. Buyer coverage, wallets, and campaign spend gate.
4. Buyer reviews, evidence, billing, and buyer reports.
5. Lead delivery, call tracking, and manual pilot path.
6. End-to-end evidence, Playwright, and smoke tests.
7. Docs, business launch gate, and validation.

Subagent output contract:

1. Existing facts: files/functions/endpoints/tables found, with paths.
2. Minimal implementation: smallest set of edits that satisfies this workstream.
3. Tests to add/update: exact test files and assertions.
4. Risks/blockers: only real blockers, not speculative concerns.
5. Do-not-do list: changes that would overbuild or violate constraints.

## Suggested Implementation Order

Build these in order after discovery:

1. Paid-pilot charter: one-market ICP, buyer commitment/pricing placeholders, timeline, success metrics, onboarding checklist, communication cadence, conversion trigger, and stop criteria.
2. Production safety foundation: private/admin ingress, implemented-only routes, endpoint inventory, golden-signal logs/metrics where practical, deploy/backup/restore validation docs/scripts.
3. Campaign attribution and form capture: persist source/campaign fields from real capture path.
4. Buyer coverage and campaign spend gate: block paid spend without funded market coverage.
5. Buyer review workflow: request, review, approve/reject, wallet adjustment audit.
6. Buyer daily report and refill recommendation: endpoint/admin view/export if minimal.
7. Call tracking or manual call workflow: generic webhook or documented/tested manual path.
8. Real E2E smoke and Playwright/Cowork V1 evidence.
9. Docs/runbooks/readiness checklist.
10. Full validation, final readiness label, commit only if explicitly requested, final report.

## V1 Acceptance Criteria

Technical V1 implementation is complete only when all of these are true:

1. Paid-pilot charter exists with one-market ICP, buyer qualification, price/commitment, timeline, success metrics, onboarding checklist, feedback cadence, conversion trigger, and stop criteria.
2. Direct buyer outreach/onboarding plan exists.
3. Production-like deployment has a documented and validated local/config path.
4. Caddy/prod routing is validated config-only unless the user approves internet exposure, and route inventory would expose only implemented public routes.
5. Admin and mutation endpoints are private or authenticated.
6. Backup and restore path is documented and locally validated where possible.
7. Update/rollback path is documented, including image/version pinning guidance if container images are changed.
8. Endpoint inventory exists for public and admin routes, including auth/private-ingress status, mutation status, and intended exposure.
9. Public capture/webhook routes have bounded input, timeout/resource controls, and no unsafe URL fetch path.
10. Lead capture writes audit and campaign/source attribution.
11. Launch readiness can block campaign spend when buyer coverage is missing.
12. Buyer coverage requires active funded buyers with services, target zips, caps, and prices.
13. A qualified lead can route to a funded buyer and debit wallet through real code paths.
14. Wallet debits, wallet adjustments, review decisions, and inbound event processing are idempotent under duplicate/retry scenarios.
15. A buyer review request can be created with evidence, reviewed, and approved/rejected.
16. Approved buyer reviews adjust the buyer wallet and write linked billing/audit rows.
17. Buyer daily report exists and shows sold leads, reviewed leads, wallet, and refill recommendation.
18. Call tracking or a manual call workflow is implemented/documented/tested for pilot needs.
19. AI-assisted decisions are audited, deterministic gates control money/routing/spend, and untrusted content cannot become model instructions.
20. Admin shows enough state for operator control: buyers, wallets, launch readiness, timeline, reviews, reports, and campaign attribution.
21. Golden-signal/tail-latency evidence exists through metrics, structured logs, or smoke output for the core V1 path.
22. Full E2E smoke passes against real local services and Postgres.
23. Playwright/Cowork evidence proves the operator flow without mocked routes.
24. Docs explain exactly how to run V1 locally and how to operate the first pilot.
25. No generated screenshots/videos/traces/manifests are committed.
26. No secrets or `.env` files are staged.
27. Full validation suite passes.

## Validation Suite

Run the full suite before final handoff. Do not commit unless the user explicitly asks.

```powershell
git status --short --branch
docker compose --env-file .env.example -f infra/compose/dev/docker-compose.yml config --quiet
$env:DATABASE_URL="postgresql+psycopg://stormlead:change-me-in-openbao@localhost:5433/stormlead"
uv run python scripts/init_db.py
Push-Location libs/stormlead_db; uv run alembic upgrade head; Pop-Location
uv run ruff check services libs scripts
uv run ruff format --check services libs scripts
uv run pytest -q services libs
uv run mypy services libs
npm run test:playwright -- --project=chromium --reporter=line
npm run cowork:admin:record
```

## Final Response

Final response must include:

- V1 score out of 100.
- Readiness label.
- Commit hash if a commit was created; otherwise state that no commit was created and why.
- Exact validation commands and results.
- Any local-only caveats.
- Clear statement of whether StormLead is technically ready or still blocked by technical work.
