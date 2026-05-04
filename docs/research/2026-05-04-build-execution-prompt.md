# Build execution prompt (task-by-task with checklists)

Use this prompt in your coding agent (Codex/Claude Code/etc.) to execute the Stormlead build in implementation order.

---

## copy/paste prompt

You are a senior staff engineer building a **real, self-hosted, production-capable AI lead-gen platform** in this repository:

- Repo: `stormlead`
- Stack constraints: Python-first, FastAPI, Postgres, Alembic, Hatchet, LiteLLM.
- Business flow: `lead captured -> enriched -> qualified -> ping-post auction -> sold/unsold -> voice nurture`.
- Non-negotiables:
  1. No mocks or fake adapters unless explicitly marked `test-only`.
  2. No TODO stubs shipped as completed work.
  3. Every task must include runnable code, tests, and docs updates.
  4. Every agent decision must be persisted for audit.
  5. All LLM calls must go through LiteLLM.

When done with each task:
- Run checks.
- Show changed files.
- Explain exact commands to run locally.
- Stop and wait for approval before moving to next task.

---

### task 0 — repo + environment validation

**Goal:** Prove dev environment is runnable before coding.

**Implement**
- Verify compose stack boots.
- Verify migrations run.
- Verify tests execute.

**Checklist**
- [ ] `just up` succeeds.
- [ ] `just migrate` succeeds.
- [ ] `just test` runs.
- [ ] `.env.example` reviewed for missing required vars.
- [ ] Capture failures with exact remediation steps.

**Deliverables**
- `docs/research/boot-validation.md` with command outputs and fixes.

---

### task 1 — deterministic lead state machine

**Goal:** Add explicit pipeline state model and transition guardrails.

**Implement**
- Add typed state enum and transition rules in `libs/stormlead_core`.
- Add transition validator API:
  - `can_transition(from_state, to_state) -> bool`
  - `assert_transition(...)` raising typed exception.
- Add orchestration helper functions (no network side effects).

**Checklist**
- [ ] States include: `captured, enriched, qualified, auctioned, sold, unsold, nurtured`.
- [ ] Illegal transitions are blocked with clear errors.
- [ ] Unit tests cover full transition matrix.
- [ ] Mypy + Ruff pass for new module.

**Deliverables**
- `libs/stormlead_core/stormlead_core/pipeline.py`
- `libs/stormlead_core/tests/test_pipeline.py`

---

### task 2 — transition audit table + alembic migration

**Goal:** Persist every workflow step with idempotency key.

**Implement**
- Add `lead_state_transitions` table with:
  - `id`, `lead_id`, `from_state`, `to_state`, `event_type`, `idempotency_key`, `payload_json`, `created_at`.
- Unique constraint on `idempotency_key`.
- Indexes on `(lead_id, created_at desc)` and `to_state`.

**Checklist**
- [ ] Alembic migration created and reversible.
- [ ] SQLAlchemy model added.
- [ ] Duplicate idempotency key is safely rejected.
- [ ] Integration test verifies write/read order.

**Deliverables**
- `libs/stormlead_db/alembic/versions/<new>.py`
- model updates + tests.

---

### task 3 — hatchet workflow wiring (real workers)

**Goal:** Execute state transitions via Hatchet tasks, not ad-hoc async.

**Implement**
- Add worker module(s) under `services/agent-runtime`:
  - `lead.enrich`
  - `lead.qualify`
  - `lead.auction`
  - `lead.nurture.unsold`
- Each task:
  - Validates input schema.
  - Performs business action.
  - Writes transition audit row.
  - Returns structured result.

**Checklist**
- [ ] Retries configured per task.
- [ ] Timeout configured per task.
- [ ] Idempotency enforced on retry.
- [ ] Task-level logs include `lead_id`, `task_name`, `attempt`.
- [ ] Tests simulate retry behavior.

**Deliverables**
- `services/agent-runtime/src/workers/*.py`
- tests for success + retry + duplicate event handling.

---

### task 4 — enrich-worker service (self-hosted crawler integration)

**Goal:** Build real enrichment service that fetches and scores buyer/prospect data.

**Implement**
- Create `services/enrich-worker` package:
  - `main.py` (worker entrypoint)
  - `crawler_client.py` (HTTP client to crawler service)
  - `extractors.py` (structured signal extraction)
  - `scoring.py` (confidence scoring)
- Add Compose service for crawler runtime.
- Persist enrichment evidence JSON to DB.

**Checklist**
- [ ] Parses business name, phone, geography, emergency-intent indicators.
- [ ] Handles crawler timeout/error with retryable exception.
- [ ] Score threshold routes low-confidence records to manual review state.
- [ ] Unit tests include malformed HTML/text cases.

**Deliverables**
- new service directory + tests
- compose updates + env vars documented.

---

### task 5 — litellm-only model access + policy guard

**Goal:** Prevent any direct provider calls from app services.

**Implement**
- Create shared LLM client wrapper in `libs/stormlead_core`.
- Wrapper requires `base_url` and virtual key from env.
- Add static check / test to block direct SDK client instantiation outside wrapper.

**Checklist**
- [ ] All agent services call wrapper only.
- [ ] Direct `OpenAI(...)` usage outside wrapper fails CI check.
- [ ] Request/response metadata (model, tokens, latency) persisted to audit store.
- [ ] Fallback model chain implemented per task type.

**Deliverables**
- `libs/stormlead_core/stormlead_core/llm_client.py`
- lint/test guard for policy enforcement.

---

### task 6 — replay + recovery tooling

**Goal:** Enable deterministic reprocessing from checkpoint.

**Implement**
- Add CLI/script + Just target:
  - `just replay-lead LEAD_ID=<id> [FROM_STATE=<state>]`
- Reconstruct latest valid state from transition table.
- Re-enqueue correct Hatchet task(s).

**Checklist**
- [ ] Works for sold and unsold branches.
- [ ] Refuses replay when active in-flight run exists.
- [ ] Emits dry-run plan before execution.
- [ ] Tested with fixture leads.

**Deliverables**
- script/module + `justfile` target + tests.

---

### task 7 — observability + SLOs

**Goal:** Make failures and economics visible.

**Implement**
- Emit metrics/log fields for:
  - lead throughput
  - qualify latency
  - auction win rate
  - unsold recovery rate
  - cost/lead by model
- Add minimal dashboard spec + alert thresholds.

**Checklist**
- [ ] Structured logs standardized across services.
- [ ] Error budget/SLO doc created.
- [ ] At least 3 actionable alerts defined.

**Deliverables**
- instrumentation code + docs.

---

### global definition of done (must pass every task)

- [ ] `uv run ruff check services libs`
- [ ] `uv run ruff format --check services libs`
- [ ] `uv run mypy services libs`
- [ ] `uv run pytest -q services libs`
- [ ] `just smoke` (or documented blocker with root cause)
- [ ] docs updated for new env vars, commands, and architecture changes
- [ ] migration + rollback path validated

---

### output format required from agent after each task

1. **What changed** (file-by-file)
2. **Why** (design choice + tradeoffs)
3. **How to run** (exact commands)
4. **Proof** (test results)
5. **Risks / next step**

Do not continue to next task without explicit user approval.
