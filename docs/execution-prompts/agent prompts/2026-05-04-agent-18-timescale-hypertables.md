# Agent-18: Timescale Hypertables & Data Retention Execution Prompt

Date: 2026-05-04

Wave: 3 — Run AFTER all Wave 2 agents are committed and migration 0008 is applied.

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-18 — Timescale Hypertables & Data Retention`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-18 — Timescale Hypertables & Data Retention` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

**Prerequisite:** All Wave 1 and Wave 2 agents are committed. Migration `0008_buyer_crm` is applied. Current Alembic head is `0008`.

Current implemented base includes:

- `ping_attempts` table has PK on `id` alone (UUID) — blocks hypertable creation
- `billing_events` table has PK on `id` alone (UUID) — blocks hypertable creation
- Timescale requires either `created_at` in the PK or as a partition column
- DB uses `timescale/timescaledb-ha:pg16-ts2.17` image (Timescale extension available)
- Alembic head is `0008`

Current stack constraints:

- Python-first.
- Postgres + TimescaleDB extension.
- Alembic for migrations (migration must chain from `0008`).
- PK refactor is irreversible (downgrade is a no-op with comment).
- No TODO stubs shipped as complete.

Known repo learnings and memory inputs:

- Hypertable creation SQL: `SELECT create_hypertable('ping_attempts', 'created_at', if_not_exists => TRUE)`
- Retention policy SQL: `SELECT add_retention_policy('ping_attempts', INTERVAL '180 days', if_not_exists => TRUE)`
- PK refactor: `ALTER TABLE ping_attempts DROP CONSTRAINT ping_attempts_pkey; ALTER TABLE ping_attempts ADD PRIMARY KEY (id, created_at)`
- Retention windows: 180 days for `ping_attempts`, 365 days for `billing_events`, no automated cleanup for `consent_audits` (7-year manual)
- PII retention: 2-year window for `leads` PII fields; `scripts/retention.py` handles the cleanup

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Create Alembic migration `0009_timescale_hypertables` that: (1) refactors PKs on `ping_attempts` and `billing_events` to include `created_at`, (2) enables hypertables on both, (3) adds retention policies. Create `scripts/retention.py` for lead PII cleanup with dry-run mode.

Out of scope:

- Continuous aggregates or Timescale compression
- Automated retention for consent_audits (7-year legal hold)
- UI for retention management
- Changes to any service code

Milestone-safe examples:

- Drop + recreate PK: `op.execute("ALTER TABLE ping_attempts DROP CONSTRAINT ping_attempts_pkey"); op.execute("ALTER TABLE ping_attempts ADD PRIMARY KEY (id, created_at)")`
- Hypertable: `op.execute("SELECT create_hypertable('ping_attempts', 'created_at', if_not_exists => TRUE)")`
- Retention script dry run: `uv run python scripts/retention.py` (default); `uv run python scripts/retention.py --execute` (real redaction)

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Run `uv run alembic upgrade head` and see migration `0009_timescale_hypertables` applied
- Run `uv run python scripts/retention.py` (dry run) and see count of leads that would be redacted
- Verify hypertable exists: `SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = 'ping_attempts'`

100% completion contract:

- Report `100/100` only when implementation, docs, tests, validation, and required Browser Use evidence are complete.
- If the score is below 100, start the final response with `Not complete:` and list the missing points, blocker, and best fallback proof.

Execution mode:

- Finish this milestone in one continuous pass if technically possible.
- Do not stop after each task for approval unless required by `AGENTS.md` or the master prompt.
- Prefer the smallest correct vertical slice over broad scaffolding.
- Do not commit unless the user explicitly asks.

Timed work block mode:

- Default milestone timebox: `1` hour when the user explicitly chooses a timebox; otherwise continue until completion, validation, or a stop condition.

Milestone-specific rules:

- The PK refactor is DESTRUCTIVE and IRREVERSIBLE — verify the table names and constraint names from `\d ping_attempts` before writing the migration
- The `downgrade()` function must be a no-op with a comment explaining why (cannot revert hypertables with data)
- `scripts/retention.py` must default to dry_run=True — `--execute` flag required for real redaction
- NEVER redact leads that are in `active`, `auctioned`, or `qualified` status — only `nurtured`, `dead`, `sold`
- PII fields to redact: `name`, `phone_e164`, `email`, `address_line1` (set to "[REDACTED]" or None)

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `libs/stormlead_db/tables.py` — find exact PK constraint names for `ping_attempts` and `billing_events`
2. Read `libs/stormlead_db/migrations/versions/` — find current head migration (should be `0008`)
3. Read existing scripts in `scripts/` to understand import patterns and async setup
4. Read `libs/stormlead_db/tables.py` — confirm `LeadRow` PII field names and `status` enum values
5. Check if TimescaleDB extension is enabled: inspect the initial migration or DB setup scripts

## Suggested Implementation Order

Build these in order after discovery:

1. Verify PK constraint names from the schema (read migrations or tables.py)
2. Create `libs/stormlead_db/migrations/versions/0009_timescale_hypertables.py`
3. Run `uv run alembic upgrade head` and verify
4. Verify hypertable via DB query if local DB is running
5. Create `scripts/retention.py` with dry-run and execute modes
6. Run dry-run: `uv run python scripts/retention.py`
7. Docs/runbooks/readiness checklist.
8. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `libs/stormlead_db/migrations/versions/0009_timescale_hypertables.py` exists with `revision="0009"` and `down_revision="0008"`
2. Migration includes PK refactor + hypertable + retention policy for both `ping_attempts` and `billing_events`
3. `downgrade()` is a no-op with explanatory comment
4. `uv run alembic upgrade head` exits 0 (or documents exact Timescale availability blocker)
5. `scripts/retention.py` exists with `redact_expired_leads(dry_run=True)` and `--execute` CLI flag
6. `uv run python scripts/retention.py` exits 0 and prints count
7. No secrets or `.env` files are staged.
8. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `libs/stormlead_db/tables.py`
- `libs/stormlead_db/migrations/versions/` (list files)
- `scripts/` (list existing scripts)

## Likely Changed Files

- `libs/stormlead_db/migrations/versions/0009_timescale_hypertables.py` (NEW)
- `scripts/retention.py` (NEW)

## Validation Suite

Required validation:

- `uv run alembic upgrade head`
- `uv run python scripts/retention.py`
- `uv run ruff check scripts/retention.py`
- `git diff --check`
