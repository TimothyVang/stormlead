# Visual Agentic Workflow for Lead Generation & Lead Selling

_Date: 2026-05-04_

## Executive Summary

You can absolutely use Playwright to **show the agent in action**. It is one of the best foundations for browser-based automation demos because it is deterministic, scriptable, and already present in this repo. However, Playwright alone is not the full “visual agentic workflow” product layer.

For your use case (lead generation + selling leads), the strongest approach is:

1. **Playwright for deterministic UI execution** (agent performs repeatable browser tasks).
2. **An orchestration layer** (your `agent-runtime`) for decisions, retries, queueing, and business logic.
3. **A visual timeline UI** to display each action, decision, and handoff in real time.
4. **Evidence capture** (screenshots/video/DOM snapshots) for trust, compliance, and sales QA.

This gives you both the “wow” demo and production safety.

---

## Your Key Question: Is Playwright the Best Way to See the Agent Working?

### Short answer

- **Yes for browser automation visibility and reliability.**
- **No if used alone without orchestration + observability UX.**

### Why Playwright is a strong fit

- Native support in repo (`playwright.config.ts`, `tests/playwright/*`).
- Fast, reliable scripted interactions.
- Built-in tracing/video/screenshot support.
- Great for “operator theater”: stakeholders can watch browser sessions and replay runs.

### Where Playwright is not enough by itself

- It does not model business workflows end-to-end (lead scoring, ping/post routing, consent audits, payout rules).
- It does not provide executive-level workflow dashboards out-of-the-box.
- It can be brittle if you rely on selectors without guardrails.

---

## What “Visual Agentic Workflow” Should Mean in This App

A full visual agent workflow for storm-leadgen should show:

1. **Intake**: lead captured via form receiver.
2. **Qualification**: enrichment + policy checks + quality/fraud scoring.
3. **Decision**: accepted/rejected/manual review + rationale.
4. **Monetization**: ping/post or routed sale decision.
5. **Audit trail**: consent proof, signature checks, action-by-action evidence.
6. **Human-in-the-loop**: escalation UI with replay artifacts.

### Core UX views to build

- **Live Run Board** (Kanban or DAG): queued → running → review → sold/rejected.
- **Run Timeline**: each tool call/action with timestamps and outcome.
- **Browser Replay Pane**: Playwright video + screenshots + highlighted action log.
- **Decision Inspector**: why this lead was accepted/rejected/routed.
- **Compliance Panel**: consent artifacts and retention status.

---

## Recommended Architecture (Fits Current Repo)

### 1) Agent Orchestration Layer

Use `services/agent-runtime` as control plane for:

- task queue consumption,
- policy-driven decisioning,
- retries/backoff,
- idempotency,
- handoff to browser worker when UI action required.

### 2) Browser Action Worker (Playwright)

Run Playwright as a specialized worker profile:

- receives signed step plans from `agent-runtime`,
- executes atomic actions,
- emits structured events after each step,
- stores artifacts in `testing/`-like evidence storage conventions.

### 3) Event Bus + Structured Logs

Use `stormlead_core.events`/logging patterns to standardize events:

- `run.started`, `step.started`, `step.succeeded`, `step.failed`, `run.completed`.
- include correlation IDs: `lead_id`, `run_id`, `session_id`, `buyer_id`.

### 4) Visual Workflow App

Add a lightweight operations UI:

- websocket stream for live runs,
- timeline/event table,
- replay tabs linking screenshots/videos/traces,
- human approval buttons for gated steps.

---

## Build Plan (Phased)

### Phase 0 — Demo Quickly (1–2 days)

Goal: show agent visibly working.

- Wrap one high-value workflow in Playwright (e.g., admin review or partner post simulation).
- Enable trace/video/screenshots for every run.
- Add a “Run Detail” page that renders:
  - status,
  - step list,
  - artifacts.

Deliverable: clickable demo where a user watches end-to-end automation on a sample lead.

### Phase 1 — Production Skeleton (1 week)

- Add a run state machine in `agent-runtime`.
- Emit normalized events at every state transition.
- Persist decision rationale and policy outcomes.
- Add retry strategy and fallback to manual review queue.

Deliverable: reliable, observable workflow engine.

### Phase 2 — Sales/Compliance Hardening (1–2 weeks)

- Add consent/evidence retention rules.
- Add lead-quality explanations for buyer trust.
- Add SLA metrics (time-to-contact, time-to-sale, reject reasons).
- Add role-based access for sales ops/reviewers.

Deliverable: buyer-safe and operator-safe lead automation platform.

---

## Tooling Comparison for “Visible Agent” UX

| Option | Best For | Strengths | Weaknesses | Recommendation |
|---|---|---|---|---|
| Playwright | Browser automation + demos | Reliable, scriptable, strong artifacts | Not full orchestration UX | **Use as core browser executor** |
| Headless-only HTTP agents | API-heavy back-office flows | Fast/cheap | No visible interaction | Use for non-UI steps |
| RPA suites (UiPath/Power Automate) | Enterprise desktop apps | Rich visual tooling | Cost, lock-in, less code-native | Not first choice here |
| “Computer-use” LLM agents only | Open-ended exploratory tasks | Flexible | Nondeterministic, risky for compliance | Use only in sandbox/human-approved mode |

---

## Design Principles for Lead Generation + Lead Selling

1. **Determinism over novelty** for revenue-critical paths.
2. **Explain every decision** (scoring, filters, routing).
3. **Evidence by default** (video/screenshot/log bundle).
4. **Human takeover in <10 seconds** on failures.
5. **Policy-first execution** (never post leads before consent checks pass).

---

## Suggested KPIs

- Lead processing success rate.
- Median run duration per lead.
- Manual intervention rate.
- Buyer acceptance rate.
- Revenue per accepted lead.
- Compliance exception count.
- Artifact completeness rate (runs with full replay evidence).

---

## Concrete Recommendation for Your Team

Yes—continue with Playwright, but position it as the **execution camera + hands** of the agent, not the whole brain.

If your goal is “I want to see the agent in action,” the best next move is:

1. Productize one end-to-end workflow with Playwright artifacts.
2. Stream step events from `agent-runtime` into a live Run Timeline page.
3. Add explicit decision cards (why accepted/rejected/sold) to build trust with operators and buyers.

This gives you immediate demo value and a path to production-grade automation.

---

## Next 7-Day Implementation Backlog

1. Add `run_events` schema/table for normalized workflow telemetry.
2. Instrument `agent-runtime` with step lifecycle events.
3. Add Playwright worker mode with per-step screenshots + final video.
4. Build minimal `/ops/runs/:id` page with timeline + artifacts.
5. Add manual approval gate for risky steps.
6. Add summary card: lead quality + sale routing rationale.
7. Run pilot on test leads and measure intervention + success rates.

---

## Copy/Paste Master Build Prompt (for 100% Completion)

Use the following prompt in your coding agent (Cursor/Codex/Claude Code/etc.) to execute the full implementation end-to-end:

```text
You are the lead engineer for the StormLead repository. Implement the Visual Agentic Workflow for Lead Generation & Lead Selling to production-ready completion.

Repository root: /workspace/stormlead

Primary objective:
Build an end-to-end, observable, and reliable agent workflow that:
1) captures and qualifies leads,
2) executes deterministic browser actions with Playwright,
3) records complete evidence and decision trails,
4) supports human-in-the-loop approvals,
5) routes/sells leads safely with compliance guardrails,
6) exposes a visual operations UI with run timeline + replay.

Non-negotiable constraints:
- Deterministic execution for revenue-critical paths.
- Every step must emit structured events with correlation IDs.
- Every run must retain replay artifacts (video/screenshot/log/trace links).
- Policy checks (consent/compliance) must gate selling/posting actions.
- Failures must support retry + escalation to manual review.
- Add tests and runnable verification commands.
- Keep changes incremental and commit in logical units.

Existing areas to use:
- services/agent-runtime
- services/form-receiver
- services/ping-post
- libs/stormlead_core (events/logging/observability)
- libs/stormlead_db (migrations + tables)
- tests/playwright + playwright.config.ts
- testing/ artifacts folders

Implementation scope:
A) Data + migrations
1. Add run/event persistence:
   - run_sessions table (run_id, lead_id, status, started_at, completed_at, assignee, escalation_reason, retry_count)
   - run_steps table (run_id, step_id, step_type, status, started_at, completed_at, error_code, error_message)
   - run_events table (event_id, run_id, step_id nullable, event_type, payload_json, ts)
   - run_artifacts table (run_id, step_id nullable, artifact_type, uri, metadata_json, ts)
2. Add indexes on run_id, lead_id, status, ts.
3. Add migration + ORM/table definitions.

B) Agent runtime orchestration
1. Implement explicit state machine:
   queued -> running -> awaiting_approval (optional) -> completed | failed | canceled
2. Emit standard events:
   run.started, step.started, step.succeeded, step.failed, run.awaiting_approval, run.completed, run.failed
3. Add retry policy (exponential backoff + max retry count).
4. Add idempotency protection for duplicated messages.
5. Add manual escalation path and assignment metadata.

C) Playwright execution worker
1. Add worker interface for browser-only steps.
2. For each executed step:
   - start trace,
   - capture screenshot(s),
   - capture terminal step result,
   - finalize trace/video.
3. Persist artifact metadata into run_artifacts.
4. Return structured step outputs and typed errors.

D) Compliance + gating
1. Before ping/post or sale action, enforce:
   - consent presence/valid signature check,
   - required data completeness,
   - fraud/quality threshold checks.
2. If check fails: emit policy failure event and route to manual review.
3. Persist decision rationale for accept/reject/sell routing.

E) Ops visualization API
1. Add API endpoints:
   - GET /ops/runs
   - GET /ops/runs/{run_id}
   - GET /ops/runs/{run_id}/events
   - GET /ops/runs/{run_id}/artifacts
   - POST /ops/runs/{run_id}/approve
   - POST /ops/runs/{run_id}/reject
2. Add websocket/SSE stream for live run updates.

F) Minimal ops UI
1. Build /ops/runs page:
   - status columns (queued/running/awaiting_approval/completed/failed)
   - search/filter by lead_id, buyer_id, status.
2. Build /ops/runs/:id page:
   - run summary card,
   - step timeline,
   - decision rationale panel,
   - artifact panel (video/screenshot/trace links),
   - approve/reject controls for gated steps.

G) Tests + quality gates
1. Unit tests:
   - state transitions,
   - retry/idempotency,
   - policy gates,
   - event emission.
2. Integration tests:
   - end-to-end run creation to completion,
   - failed step retry path,
   - manual approval flow.
3. Playwright tests:
   - ops run list rendering,
   - run detail timeline updates,
   - approval action lifecycle.
4. Provide commands and expected outcomes in final report.

H) Documentation + runbooks
1. Update docs/research and add implementation runbook:
   - architecture diagram (ASCII acceptable),
   - event schema reference,
   - operational SOP for failed runs.
2. Add “how to demo the agent live” checklist.

Acceptance criteria (must all pass):
- Can process a sample lead end-to-end with visible timeline.
- Can replay artifacts for each major step.
- Can gate risky actions on approval.
- Can explain why a lead was accepted/rejected/sold.
- Automated tests pass for new logic.
- No broken existing workflows.

Execution style:
- First produce a concise implementation plan with file-by-file edits.
- Then implement in small commits with clear messages.
- After each major section (A-H), run tests and summarize results.
- End with a final verification checklist mapped to acceptance criteria.
```

### How to use this prompt effectively

1. Paste it into your coding agent.
2. Ask the agent to execute sections A→H in order.
3. Require a checkpoint after each section with:
   - changed files,
   - commands run,
   - pass/fail status,
   - blockers and next step.
4. Do not let the agent skip tests or migration checks.


---

## Repo-Specific Execution Prompt V2 (Exact File Targets)

```text
You are implementing in /workspace/stormlead. Execute in this exact order and touch only the listed targets unless required by compiler/tests.

PHASE A (DB schema + migrations) targets:
1) libs/stormlead_db/migrations/versions/0005_agent_run_tables.py
2) libs/stormlead_db/src/stormlead_db/tables.py
3) libs/stormlead_db/src/stormlead_db/__init__.py (only if exports are needed)
4) docs/research/2026-05-04-visual-agentic-workflow-leadgen.md (progress notes)

Implementation details:
- Add tables: run_sessions, run_steps, run_events, run_artifacts.
- Include FKs to leads and between run tables.
- Include indexes on run_id/lead_id/status/ts and step linkage.
- Ensure downgrade cleanly drops indexes then tables.
- Keep migration idempotent where practical using IF EXISTS / IF NOT EXISTS.

Verification commands:
- python -m compileall libs/stormlead_db/src/stormlead_db
- alembic -c libs/stormlead_db/alembic.ini upgrade head
- alembic -c libs/stormlead_db/alembic.ini downgrade -1
- alembic -c libs/stormlead_db/alembic.ini upgrade head

Commit strategy:
- Commit 1: migration file only.
- Commit 2: ORM model/table definitions.
- Commit 3: docs updates + task board sync.

Output requirements for every checkpoint:
- Changed files
- Exact commands run
- Pass/fail per command
- Any follow-up fixes needed
```

---

## One-Shot Task Breakdown Board (Execution Tickets)

### EPIC A — Data Layer (Phase A)

- [x] **A1: Create migration scaffold**
  - File: `libs/stormlead_db/migrations/versions/0005_agent_run_tables.py`
  - Done when: migration adds all 4 run tables with PK/FK and lifecycle timestamps.
- [x] **A2: Add indexed query paths**
  - File: `libs/stormlead_db/migrations/versions/0005_agent_run_tables.py`
  - Done when: indexes exist for lead/status/run_id/step_id/ts lookups.
- [x] **A3: Add downgrade safety**
  - File: `libs/stormlead_db/migrations/versions/0005_agent_run_tables.py`
  - Done when: downgrade drops dependent indexes then tables cleanly.
- [x] **A4: Add ORM mappings**
  - File: `libs/stormlead_db/src/stormlead_db/tables.py`
  - Done when: `RunSessionRow`, `RunStepRow`, `RunEventRow`, `RunArtifactRow` exist and match schema.

### EPIC B — Runtime Orchestration

- [ ] **B1: Add run state machine module**
  - Target: `services/agent-runtime/src/agent_runtime/execution.py`
- [ ] **B2: Emit lifecycle events**
  - Targets: `services/agent-runtime/src/agent_runtime/worker.py`, `libs/stormlead_core/src/stormlead_core/events.py`
- [ ] **B3: Add retry + idempotency controls**
  - Targets: `services/agent-runtime/src/agent_runtime/worker.py`, `services/agent-runtime/src/agent_runtime/hermes.py`

### EPIC C — Playwright Worker & Evidence

- [ ] **C1: Define browser step contract**
  - Target: `services/agent-runtime/src/agent_runtime/execution.py`
- [ ] **C2: Capture trace/video/screenshot artifacts**
  - Targets: `tests/playwright/helpers/cowork.ts`, `playwright.config.ts`, worker glue code
- [ ] **C3: Persist artifact metadata to run_artifacts**
  - Targets: agent runtime persistence layer + DB integration

### EPIC D — Compliance Gate Controls

- [ ] **D1: Consent and signature validation before post/sell**
  - Targets: `services/form-receiver/src/form_receiver/signatures.py`, runtime policy checks
- [ ] **D2: Fraud/quality threshold enforcement**
  - Targets: `services/agent-runtime/src/agent_runtime/qualify.py`, `services/ping-post/src/ping_post/auction.py`
- [ ] **D3: Decision rationale persistence**
  - Targets: runtime write path + run_events payload

### EPIC E — Ops APIs + UI

- [ ] **E1: Add run listing/detail endpoints**
  - Target: `services/agent-runtime/src/agent_runtime/worker.py` or API module split
- [ ] **E2: Add event/artifact APIs + approve/reject actions**
  - Target: API module(s)
- [ ] **E3: Build minimal ops UI pages**
  - Target: UI app module (create if absent)

### EPIC F — Testing & Demo

- [ ] **F1: Unit tests for transitions/retries/gates**
- [ ] **F2: Integration test for full run lifecycle**
- [ ] **F3: Playwright demo flow with replay artifacts**
- [ ] **F4: Demo runbook and checklist in docs**

