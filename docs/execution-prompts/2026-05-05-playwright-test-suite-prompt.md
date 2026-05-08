# Playwright Test Suite — Autonomous Fix and Run Prompt

Date: 2026-05-05
Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`
Sandbox inventory: `tools/SANDBOX.md`
Shared tools reference: `C:\Users\newbi\Desktop\hadi projects\tools\`

Paste the block below directly into Opus. It is a self-directing loop — Opus runs it until done.

---

## Copy/Paste Prompt

```
You are an autonomous agent running inside the StormLead repo at:
  C:\Users\newbi\Desktop\hadi projects\stormlead

You will run a self-directed loop until the exit condition is met. You do not stop to ask unless you hit a real blocker (credential gap, destructive git op, real-world external contact, product decision only the user can make). Everything else: figure it out.

Before your first loop iteration, read these tool inputs in order:

1. `AGENTS.md` for StormLead operating limits.
2. `tools/SANDBOX.md` for the StormLead sandbox inventory, symptom-to-tool table, active MCP loadout, and isolation patterns.
3. `C:\Users\newbi\Desktop\hadi projects\tools\TOOLS.md` for shared workspace tool-routing guidance.
4. Other files under `C:\Users\newbi\Desktop\hadi projects\tools\` only when the shared routing guide points to something relevant to the current blocker.

Conflict rule: StormLead repo-local instructions win over shared tools guidance. Use the shared `tools` repo as a routing and learning reference, not as permission to install broad tool packs, touch secrets, mutate production systems, or bypass StormLead safety limits.

Safety hard limits (never violate):
- No destructive git commands. No commits unless user explicitly asks.
- No real external contact, no production deployments, no paid actions.
- No modifying .env files.
- All experiments inside the sandbox (Docker stack, testing/, worktrees).

Browser automation research findings (2026-05-05):
- Do not clone, fork, or build Chromium for this app test suite. Chromium source checkout/build is browser-engine-development work, requires large disk/tooling/time investment, and is unnecessary unless the browser itself must be modified.
- Treat Playwright or Puppeteer as the browser-control layer, not the reasoning layer. The THINK -> ACT -> OBSERVE -> DECIDE loop is what provides log-aware continuation and self-correction.
- Prefer the existing Playwright suite for repeatable E2E. If exact Chrome behavior or reproducible Chrome binaries matter, use installed Google Chrome (`channel: 'chrome'`) or Google Chrome for Testing rather than building Chromium.
- Chrome for Testing is Google's versioned, non-auto-updating Chrome flavor made for browser automation. Use it when stable replay of old test runs matters.
- Playwright can capture the evidence needed for agentic debugging: console messages, page errors, request/response events, WebSocket frames, screenshots, traces, videos, DOM snapshots, and HTML reports. Inspect those artifacts before editing.
- If Playwright is blocked for a specific reason, Puppeteer with Chrome for Testing is the closest Chrome-native fallback. Selenium/WebDriverIO is acceptable but does not solve self-learning by itself.
- The `chromium` project name in this prompt refers to the existing Playwright project target. It is not permission or a requirement to clone/build Chromium.

Chrome-based app-building and user-testing automation model:
- Use Chrome as the instrumented browser, not as the brain. The brain is this agent loop reading evidence, updating hypotheses, editing code, and rerunning focused checks.
- Preferred stack: Chrome for Testing or installed Chrome, Playwright for repeatable E2E, Puppeteer plus Chrome DevTools Protocol for Chrome-native inspection, Lighthouse user flows for performance/accessibility, and DevTools Recorder only as a way to seed or export manual flows.
- Build loop: make one small app change, run local build/typecheck/unit checks where relevant, start local services, open Chrome, drive the affected UI flow, read browser and service evidence, then fix or promote to a stable test.
- Exploratory QA loop: navigate as a synthetic user persona, capture screenshots, console errors, failed network calls, confusing states, slow transitions, and dead ends, then turn verified findings into app fixes or regression tests.
- Regression loop: do not leave important behavior as vague AI exploration. Once a flow is stable, convert it into deterministic Playwright tests with clear setup, selectors, assertions, and artifacts.
- User research loop: synthetic personas are useful for heuristic testing and early product friction discovery, but they are not a replacement for consented human user research. Do not contact real users from this workspace.
- Performance/accessibility loop: use Lighthouse user flows through Puppeteer when testing interactions beyond first page load. Use navigation for page loads, timespan for interactions and SPA transitions, and snapshot for deep UI states like open forms, dialogs, menus, and dashboards.
- Evidence to capture before changing code: browser console logs, page errors, failed requests, relevant response bodies, screenshots before/after key actions, Playwright traces or CDP traces, Lighthouse reports when performance/accessibility is in scope, and local service logs.
- Tool choice: use Playwright for CI-ready regression tests and traceable app E2E; use Puppeteer/CDP for Chrome-specific instrumentation, Lighthouse flows, and low-level browser inspection. Neither tool self-learns without this agent loop.
- Function-callable Chrome observer: when you need real-time browser evidence outside a full Playwright test run, call the local MCP tool `observe_chrome_page` with `confirm_synthetic_local=true` or run `npm run observe:chrome -- --url http://127.0.0.1:8003/admin --duration-seconds 10 --headless true`. It refuses non-loopback URLs and writes `testing/runs/<run-id>-chrome-observe/logs/chrome-events.jsonl` plus `chrome-summary.json`.
- Browser-test self-learning evidence: Cowork browser tests automatically stream console, page errors, document/fetch/XHR request-response metadata, failed requests, HTTP >=400 responses with body previews, WebSocket frames, navigations, and crashes to each run's `logs/browser-events.jsonl`. Read `logs/browser-summary.json` before deciding whether to edit code or tests.
- Functional verification for the observer should use the MCP tool `run_chrome_observer_functional_test` with `confirm_synthetic_local=true`. The fallback command is `npm run test:chrome-observer`. Both create a local loopback page, emit real Chrome console and HTTP events, then assert both `npm run observe:chrome` and the MCP `observe_chrome_page` function-call path captured the expected JSONL evidence.


════════════════════════════════════════════════════════════
  AUTONOMOUS PLAYWRIGHT DEVELOPER CONTAINER
════════════════════════════════════════════════════════════

This prompt is the operating container for a human-like development loop. Your job is to keep cycling through local build, run, inspect, fix, and Playwright verification until the exit condition is met or a real blocker is documented.

Act like a careful developer, not a blind test runner:
- Start the local Docker Compose services needed for the app and inspect their health before testing.
- Run the narrowest Playwright test that can prove or disprove the current hypothesis before running the full project.
- When Playwright fails, read the failure output, relevant screenshots/traces, service logs, API response bodies, and source before editing.
- Prefer one smallest correct fix, then rerun the same failing test to prove the fix.
- Use generated scripts only to illuminate an unknown, then delete throwaway scripts after OBSERVE unless the script becomes a useful repo test or documented operator tool.
- Keep all generated evidence under ignored `testing/` paths and reference it in the handoff.

Self-improvement rules:
- Every repeated failure must improve the next loop: refine the hypothesis, create a focused diagnostic, spawn a read-only sub-agent, or update the prompt/session notes with a verified learning.
- Persist durable learning only when it is verified by passing tests, command output, source reads, or exact blocker evidence.
- Durable learning belongs in the smallest source of truth: Playwright tests/fixtures for behavior, helper code for reusable test mechanics, docs/runbooks/prompts for operator or agent workflow, and rare comments for non-obvious invariants.
- Never persist secrets, PII, auth headers, cookies, `.env` values, raw production payloads, or private local-machine assumptions.
- Do not weaken tests to pass. If an expectation is wrong, prove the real app behavior first, then update the expectation and document why.


════════════════════════════════════════════════════════════
  THE LOOP — run this until EXIT CONDITION is met
════════════════════════════════════════════════════════════

Each iteration of the loop has four steps: THINK → ACT → OBSERVE → DECIDE.
You must write all four steps out loud before moving to the next iteration.
Do not skip steps. Do not batch iterations. One at a time.

────────────────────────────────────────────────────────────
ITERATION TEMPLATE
────────────────────────────────────────────────────────────

## ITERATION N

### THINK
State in 3–5 sentences:
- What is the current system state? (what services are up, what tests are passing, what is failing)
- What is the gap between current state and exit condition?
- What is my hypothesis about the next thing blocking progress?
- What is the single smallest action that could close or disprove that gap?

Do NOT skip THINK to go straight to action. A wrong action costs more time than a slow thought.

### ACT
Execute exactly one of these action types:

  TYPE A — Shell command
    Run it. Show the exact command before running.

  TYPE B — File edit
    Read the file first. State which lines change and why. Make the edit.

  TYPE C — Script generation
    When a shell command cannot isolate the question, generate a throwaway script.
    Pattern:
      1. Write testing/debug/diag-<reason>-<N>.{ts|py|sh}
      2. Run it
      3. Read its full output
      4. Delete it after OBSERVE
    Use TypeScript for API/webhook tests, Python for DB/service logic, bash for process/log inspection.
    Example triggers: unexpected status code, HMAC mismatch you cannot explain, response body shape unknown.

  TYPE D — Prompt generation + sub-agent
    When the investigation requires simultaneously reading logs, API responses, and source code
    that would overload your working context, generate a sub-prompt and spawn a sub-agent.
    Pattern:
      1. Write testing/debug/subprompt-<topic>-<N>.md with these exact sections:
           OBSERVED: [what you saw — specific output, status codes, error messages]
           INVESTIGATE: [exactly which files, endpoints, log streams, DB tables to check]
           RETURN: [structured list of facts with file paths and line numbers — no opinions, no fixes]
      2. Spawn a read-only sub-agent with that prompt
      3. Read the sub-agent's findings
      4. Delete the subprompt file
      5. Integrate the findings into your OBSERVE step
    Sub-agents do investigation only. You apply all fixes.

  TYPE E — State update (no external action)
    When you have enough information and just need to update your understanding.
    Write: "State update: [what changed in my model of the system]"

### OBSERVE
Write exactly:
  - Expected: [what you expected the action to produce]
  - Got: [what it actually produced — be specific, include status codes, error text, pass/fail counts]
  - Delta: [how this changes your understanding of the gap]

### DECIDE
Choose one:
  A. CONTINUE — gap is not closed. State what the next iteration will target.
  B. EXIT — exit condition is fully met. Write the handoff (see EXIT CONDITION below).
  C. BLOCKED — you cannot progress without user input. State the exact blocker in one sentence and stop.

────────────────────────────────────────────────────────────
SAME-FAILURE RULE
────────────────────────────────────────────────────────────

If the OBSERVE step for iteration N+1 shows the same failure as iteration N, you MUST:
1. State out loud: "Same failure twice — my hypothesis was wrong."
2. Use TYPE C (script) or TYPE D (sub-agent) before attempting another file edit.
3. Do not re-edit the same line a third time without new information.


════════════════════════════════════════════════════════════
  EXIT CONDITION
════════════════════════════════════════════════════════════

Exit when ALL of the following are true:

  [ ] api project: npm run test:playwright -- --project=api → 26/26 pass
  [ ] chromium project: npm run test:playwright -- --project=chromium → ran and results documented (no Chromium source checkout/build)
  [ ] testing/ contains run artifacts (service logs, browser console/network evidence, screenshots, or traces)
  [ ] Any remaining failure has: test name, exact error, root cause class, and whether it is
      fixable in this session or requires a blocker resolution

If you cannot reach 26/26 on api after 6 iterations on the same set of failures, document the
remaining failures with full diagnosis and exit. Do not loop forever.


════════════════════════════════════════════════════════════
  INITIAL CONTEXT — read before iteration 1
════════════════════════════════════════════════════════════

The test suite has already been built. It ran once and produced 14/26 passing. Root causes are
already diagnosed. Your first iterations should apply the known fixes and verify them before
investigating anything else.

### Known Fix 1 — decodeSecret() HMAC mismatch (causes ~12 × 401)

File: tests/playwright/helpers/webhook.ts, function decodeSecret()

Python's base64.b64decode(validate=False) silently drops non-base64 chars. The local dev
secret whsec_change-me contains '-' which is not valid standard base64. Python drops it.
Node.js Buffer.from(str,'base64') treats '-' as URL-safe base64 — different key → different
HMAC → 401 on every webhook POST.

Current code:
  const raw = secret.replace(/^whsec_/, '');
  const padded = raw + '='.repeat((4 - (raw.length % 4)) % 4);
  return Buffer.from(padded, 'base64');

Fixed code:
  const raw = secret.replace(/^whsec_/, '');
  // Python base64.b64decode(validate=False) silently drops non-base64 chars (e.g. '-').
  const cleaned = raw.replace(/[^A-Za-z0-9+/]/g, '');
  const padded = cleaned + '='.repeat((4 - (cleaned.length % 4)) % 4);
  return Buffer.from(padded, 'base64');

### Known Fix 2 — buyer creation 200 vs expected 201

File: tests/playwright/buyer-lifecycle.spec.ts, line 26
POST /v1/buyers returns 200 (FastAPI default — no status_code=201 decorator).
Change: expect(status).toBe(201) → expect([200, 201]).toContain(status)

### Environment setup required before first test run

1. Start services (skip landing — port 8001 conflicts with another local project):
   docker compose -f infra/compose/dev/docker-compose.yml up -d \
     form-receiver ping-post enrich-worker agent-runtime hatchet-engine storm-watcher

2. Health check (must pass before any test run):
   curl -sf http://localhost:8002/healthz && echo ok
   curl -sf http://localhost:8003/healthz && echo ok

3. Seed buyers (idempotent):
   uv run python scripts/seed_dev.py

   Without this, qualified_sold and return-workflow tests get "unsold" instead of "sold".
   Buyer A: UUID 00000000-0000-0000-0000-0000000000a1 (TX/78701/tree_removal)

### Failure diagnosis reference (use in THINK step)

401 → HMAC mismatch. Re-check decodeSecret() and which secret is in scope.
404 → Wrong endpoint path. Read the actual route in ping-post/api.py or form-receiver/api.py.
422 → Missing/invalid request field. Read the response body — it names the field. Read the Pydantic model.
409 → Replay guard (timestamp >300s old), idempotency guard, or already-approved return request.
Timeout on "sold" → Hatchet stall. Check: docker logs hatchet-engine, docker logs enrich-worker,
  docker logs agent-runtime. Then: GET http://localhost:8003/v1/buyers/00000000-0000-0000-0000-0000000000a1
  to confirm Buyer A is active with positive balance.
"body.xxx is undefined" → Response shape changed. Use TYPE C script to print the full response body.

### Architecture facts (trust these)

- No GET /v1/admin/leads/{id} endpoint exists. Status comes from GET /v1/admin/leads/{id}/timeline → body.current_state
- Webhook signing: "{webhook_id}.{unix_timestamp}." + raw_body (trailing dot after timestamp — critical)
- Replay window: ±300s. buildExpiredHeaders sets timestamp 600s in past → intentional 409
- KPI fields: prepaid_cash_cents, active_buyers, sold_leads, returned_leads, lead_revenue_cents (no total_leads, no conversion_rate)
- Readiness: GET /v1/admin/launch-readiness (not /v1/admin/readiness)
- Return response field: return_request_id (not return_id)
- Return review: POST /v1/return-requests/{id}/review with {action, notes, operator}
- POST /v1/buyers requires: name, company, contact_email, contact_phone_e164, webhook_url,
  webhook_secret, bid_per_lead_t1_t2, bid_per_lead_t3, bid_per_call, filter_expression

### Isolation pattern for safe code experiments

If you want to test a code change without affecting the working tree:
  git worktree add ../stormlead-pw-fix HEAD
  # make changes in worktree
  # run tests from worktree
  git worktree remove ../stormlead-pw-fix  (if it worked, cherry-pick back; if not, discard)

For per-session DB isolation:
  CREATE DATABASE stormlead_experiment_pw TEMPLATE stormlead_dev;
  (see tools/SANDBOX.md for the full pattern)


════════════════════════════════════════════════════════════
  SUGGESTED FIRST 3 ITERATIONS
════════════════════════════════════════════════════════════

These are suggestions, not commands. Use your THINK step to decide if they still make sense
given what you observe in iteration 1.

Iteration 1: Bring the environment up. Apply both known fixes. Verify health endpoints.
Iteration 2: Smoke-test Fix 1 (one security test), smoke-test Fix 2 (one buyer test).
Iteration 3: Run full api project. Read every failure. Classify each by the diagnostic reference above.

After iteration 3, the loop drives itself based on what you observe.


════════════════════════════════════════════════════════════
  HANDOFF FORMAT (write this when EXIT CONDITION is met)
════════════════════════════════════════════════════════════

## Session Handoff

**Iterations run:** N
**Tools used:** [list which ACT types were used and what they found]
**Scripts generated:** [list files written to testing/debug/ and what they revealed]
**Sub-agents spawned:** [topics and key findings]

**api project result:** X/26 passing
**chromium project result:** X/Y passing

**Remaining failures (if any):**
  - Test: [name]
  - Error: [exact message]
  - Root cause: [classification]
  - Fixable this session: yes/no — [if no, what is blocking]

**Files changed:**
  - [path] — [one line why]

**Artifacts:** testing/[path]

**Reusable learnings:** [any new failure patterns beyond the two known root causes]
  Persisted to: [file where the learning was recorded, or "none — already in this prompt"]

**Safety preserved:** no commits, no real external contact, no production access
```
