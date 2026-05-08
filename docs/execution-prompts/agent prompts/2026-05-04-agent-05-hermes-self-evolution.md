# Agent-05: Hermes Self-Evolution Execution Prompt

Date: 2026-05-04

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-05 — Hermes Self-Evolution`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-05 — Hermes Self-Evolution` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

Current implemented base includes:

- `services/agent-runtime/hermes.py` has `hermes_self_evolution()` workflow, LiteLLM call pattern, and model policy — but three TODOs remain: Langfuse trace fetch, skill registry load, proposal persistence
- `libs/stormlead_db/` uses Alembic for migrations; latest revision is `0006`
- `stormlead_db.engine` exports `get_session()` async context manager
- Langfuse API: `${LANGFUSE_HOST}/api/public/traces` with `Authorization: Bearer ${LANGFUSE_SECRET_KEY}`
- `skills/` directory exists at repo root with a `.gitkeep` — intended for JSONL skill files

Current stack constraints:

- Python-first.
- FastAPI.
- Postgres.
- Alembic (new migration must chain from current head revision).
- LiteLLM only for model calls.
- No direct provider SDK imports in runtime code.
- Docker Compose for dev and prod.
- No TODO stubs shipped as complete.

Known repo learnings and memory inputs:

- Migration revision numbering: current head is `0006`; new migration is `0007`
- Langfuse trace list endpoint returns `{"data": [...], "meta": {...}}` — use `data` key
- Proposal types: `prompt_update`, `new_skill`, `retire_skill`
- Max 5 proposals per weekly run to control DB growth
- `SkillProposalRow` needs to be added to `libs/stormlead_db/tables.py` AND the migration
- Hermes runs weekly via Hatchet cron (`0 8 * * 1` = every Monday at 08:00 UTC)

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Implement the three TODO sections in `hermes.py`: (1) fetch last-week Langfuse traces via API, (2) load skill registry from `skills/*.jsonl` files, (3) persist up to 5 proposals to new `skill_proposals` DB table. Create migration `0007_skill_proposals.py`. Add `SkillProposalRow` to `tables.py`.

Out of scope:

- Operator UI for reviewing proposals (Wave 3 / buyer portal)
- Automated proposal application (proposals are pending_review by default)
- Changes to other hermes workflow triggers or model policy
- Real Langfuse API calls during testing (mock in unit tests)

Milestone-safe examples:

- Migration chain: `revision = "0007"; down_revision = "0006"`
- Langfuse trace fetch: `GET ${LANGFUSE_HOST}/api/public/traces?fromTimestamp=...&limit=100&orderBy=timestamp.desc`
- Proposal status default: `"pending_review"` (operators must review before applying)

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Run `uv run alembic upgrade head` and see migration `0007_skill_proposals` applied
- Import `SkillProposalRow` from `stormlead_db.tables`
- Call `_fetch_weekly_traces()` and receive `[]` when Langfuse is unreachable (no raise)
- Call `_summarize_traces([])` and receive a string with trace count = 0
- Call `_persist_proposals([], date.today())` and receive `0` without raising

100% completion contract:

- Report `100/100` only when implementation, docs, tests, validation, and required Browser Use evidence are complete.
- If the score is below 100, start the final response with `Not complete:` and list the missing points, blocker, and best fallback proof.

Execution mode:

- Finish this milestone in one continuous pass if technically possible.
- Do not stop after each task for approval unless required by `AGENTS.md` or the master prompt.
- Prefer the smallest correct vertical slice over broad scaffolding.
- Do not commit unless the user explicitly asks.

Timed work block mode:

- Default milestone timebox: `1.5` hours when the user explicitly chooses a timebox; otherwise continue until completion, validation, or a stop condition.

Milestone-specific rules:

- Migration `0007` must chain from `0006` — verify the current head before writing the migration file
- `SkillProposalRow` must be added to `libs/stormlead_db/tables.py` (not just the migration)
- Langfuse fetch errors must be caught silently — Hermes must still produce proposals from empty trace set
- Proposals from LLM response must be JSON-parsed — if parse fails, log warning and return 0 saved
- `_persist_proposals` must cap at 5 rows per week regardless of how many LLM proposes

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `services/agent-runtime/hermes.py` — document the three TODO locations, existing `run_agent_task()` call signature, and `SYSTEM_PROMPT` variable
2. Read `libs/stormlead_db/tables.py` — confirm current table class structure, UUID/Column imports, and latest revision info
3. Read `libs/stormlead_db/migrations/versions/` — find the current head migration filename and revision value
4. Read `libs/stormlead_db/migrations/env.py` — confirm migration environment setup
5. Read `.env.example` — identify existing Langfuse env var names (`LANGFUSE_HOST`, `LANGFUSE_SECRET_KEY`)

## Suggested Implementation Order

Build these in order after discovery:

1. Add `SkillProposalRow` ORM class to `libs/stormlead_db/tables.py`
2. Create `libs/stormlead_db/migrations/versions/0007_skill_proposals.py` (chain from current head)
3. Implement `_fetch_weekly_traces()` in `hermes.py`
4. Implement `_summarize_traces()` in `hermes.py`
5. Implement `_persist_proposals()` in `hermes.py`
6. Wire all three into `hermes_self_evolution()` main function
7. Run `uv run alembic upgrade head` to verify migration
8. Docs/runbooks/readiness checklist.
9. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `libs/stormlead_db/migrations/versions/0007_skill_proposals.py` exists with correct `revision="0007"` and `down_revision="0006"`
2. `SkillProposalRow` is importable from `stormlead_db.tables`
3. `_fetch_weekly_traces()` returns `[]` when Langfuse is unreachable
4. `_summarize_traces([])` returns a string containing "Traces analyzed: 0"
5. `_persist_proposals([], date.today())` returns `0` without raising
6. `uv run alembic upgrade head` exits 0 with `0007_skill_proposals` applied
7. `hermes_self_evolution()` no longer has TODO stubs
8. No secrets or `.env` files are staged.
9. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `services/agent-runtime/hermes.py`
- `libs/stormlead_db/tables.py`
- `libs/stormlead_db/migrations/versions/` (list files)
- `.env.example`

## Likely Changed Files

- `services/agent-runtime/hermes.py` (implement 3 TODOs + helper functions)
- `libs/stormlead_db/tables.py` (add SkillProposalRow)
- `libs/stormlead_db/migrations/versions/0007_skill_proposals.py` (NEW)

## Validation Suite

Required validation:

- `uv run alembic upgrade head`
- `uv run python -c "from stormlead_db.tables import SkillProposalRow; print('ok')"`
- `uv run ruff check services/agent-runtime/ libs/stormlead_db/`
- `uv run mypy services/agent-runtime/ libs/stormlead_db/ --ignore-missing-imports`
- `git diff --check`
