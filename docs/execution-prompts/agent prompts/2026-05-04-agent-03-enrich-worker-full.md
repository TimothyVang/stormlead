# Agent-03: Enrich-Worker Full Completion Execution Prompt

Date: 2026-05-04

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

Use this prompt in a coding agent session to complete `Agent-03 — Enrich-Worker Full Completion`.

## Copy/Paste Prompt

Operational mode for this request: build, not read-only planning. You may edit files, run commands, and use available tools as needed to complete the requested task.

Safety limits still apply: do not run destructive git commands, expose public services, contact real people, trigger paid actions, commit unrelated changes, or handle secrets unless explicitly approved.

Start by applying the rules from `docs/execution-prompts/master-agent-execution-prompt.md`.

You are a senior staff engineer building `Agent-03 — Enrich-Worker Full Completion` for StormLead.

Repo:

`C:\Users\newbi\Desktop\hadi projects\stormlead`

Current implemented base includes:

- `services/enrich-worker/enrich.py` fetches page HTML, extracts title, infers `requested_service` via regex (tree_removal, roof_tarp, water_mitigation)
- `EnrichmentEvidence` dataclass is frozen
- `LeadRow` has `geom` (PostGIS GEOGRAPHY POINT) and `avm` fields and `photo_s3_keys` (JSONB list)
- LiteLLM proxy is at `${LITELLM_PROXY_URL}` (default `http://litellm:4000`) for all model calls
- An S3 helper (`fetch_from_s3(s3_key)`) exists in the service for fetching photo bytes

Current stack constraints:

- Python-first.
- FastAPI.
- Postgres + PostGIS.
- LiteLLM only for model calls (route `claude-vision` model name).
- No direct provider SDK calls (no `anthropic` or `openai` imports in runtime code).
- Docker Compose for dev and prod.
- No TODO stubs shipped as complete.

Known repo learnings and memory inputs:

- Nominatim rate limit: 1 req/s per user-agent; use `stormlead-enrich/1.0 (newbieone56@gmail.com)` as User-Agent
- Nominatim returns `[{"lat": ..., "lon": ..., "display_name": ...}]`; empty list means no result
- LiteLLM vision: POST to `/v1/chat/completions` with `"model": "claude-vision"` and base64 image in `image_url` content block
- Photo classification should be best-effort: return `None` on any error, never raise
- Max 3 photos classified per lead to control LiteLLM cost
- PostGIS `geom` column uses WKT: `POINT({lon} {lat})` format

Use these as starting hypotheses, not unquestioned truth. Re-verify stale or risky learnings against current repo files before using them for implementation decisions.

Goal:

Create `services/enrich-worker/geocode.py` (Nominatim geocoder) and `services/enrich-worker/photo.py` (LiteLLM vision photo classifier), then extend `services/enrich-worker/enrich.py` to call both after the existing enrichment step and persist results to `LeadRow`.

Out of scope:

- ATTOM AVM integration (requires paid API key)
- Real S3 photo fetching changes (use existing `fetch_from_s3` helper)
- Admin UI or dashboard changes
- Changes to DB schema (geom and photo_s3_keys columns already exist)

Milestone-safe examples:

- Geocoder user agent string: `"stormlead-enrich/1.0 (newbieone56@gmail.com)"`
- LiteLLM vision model name: `"claude-vision"` (not `"claude-3-opus"` directly)
- Damage prompt JSON schema: `{"damage_tier": 1-4, "damage_type": str, "confidence": 0.0-1.0, "notes": str}`

Non-negotiable milestone outcome:

At the end of the session, a reviewer must be able to verify from code, docs, admin UI, command output, and evidence that StormLead can:

- Import geocode module: `uv run python -c "from enrich_worker.geocode import geocode_address; print('ok')"`
- Import photo module: `uv run python -c "from enrich_worker.photo import classify_photo; print('ok')"`
- Call `geocode_address("", "", "", "")` and receive `None` without raising
- Call `classify_photo(b"")` and receive `None` without raising (bad input gracefully handled)
- Show that `enrich.py` calls both and persists results to DB

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

- All geocoding and photo classification must be best-effort (catch all exceptions, return None)
- Never use `asyncio.run()` inside an async function — use `await` or `run_in_executor` for sync calls
- LiteLLM call must use `LITELLM_PROXY_URL` env var, not hardcoded URL
- Photo classifier must return `None` if `confidence < 0.7` so low-confidence results are not persisted
- Only classify first 3 photos per lead to cap LiteLLM cost

## Parallel Subagent Protocol

After initial inspection, launch these subagents concurrently only if the current agent host supports safe read-only subagents.

Required workstreams:

1. Read `services/enrich-worker/enrich.py` — understand current enrichment flow, `enrich_lead()` function signature, session usage
2. Read `libs/stormlead_db/tables.py` — confirm `LeadRow.geom`, `LeadRow.photo_s3_keys`, `LeadRow.damage_tier` column names and types
3. Read any existing tests in `services/enrich-worker/tests/` to understand test patterns
4. Check `services/enrich-worker/pyproject.toml` for existing dependencies (httpx should already be there)
5. Read `.env.example` for existing LiteLLM env var names

## Suggested Implementation Order

Build these in order after discovery:

1. Create `services/enrich-worker/geocode.py` with `GeoPoint` dataclass and `geocode_address()` async function
2. Create `services/enrich-worker/photo.py` with `classify_photo()` async function
3. Extend `services/enrich-worker/enrich.py` `enrich_lead()` to call geocoder and photo classifier, persist results
4. Run import smoke tests for both new modules
5. Run existing enrich-worker tests: `uv run pytest services/enrich-worker/tests/ -v`
6. Docs/runbooks/readiness checklist.
7. Full validation and final report.

## Acceptance Criteria

Technical implementation is complete only when all of these are true:

1. `services/enrich-worker/geocode.py` exists with `geocode_address(address_line1, city, state, zip_) -> GeoPoint | None`
2. `services/enrich-worker/photo.py` exists with `classify_photo(image_bytes: bytes) -> dict | None`
3. `enrich.py` calls `geocode_address()` and persists result to `LeadRow.geom` if geo point returned
4. `enrich.py` calls `classify_photo()` for up to 3 photos and persists `damage_tier` if confidence >= 0.7
5. Import smoke tests for both modules exit 0
6. Relevant docs explain geocoding and photo classification behavior.
7. No secrets or `.env` files are staged.
8. Required validation passes or a real blocker is documented with fallback proof.

## Start By Inspecting

- `git status --short --branch`
- `git diff`
- `AGENTS.md`
- `docs/execution-prompts/master-agent-execution-prompt.md`
- `services/enrich-worker/enrich.py`
- `libs/stormlead_db/tables.py`
- `services/enrich-worker/pyproject.toml`
- `.env.example`
- `services/enrich-worker/tests/` (check if it exists)

## Likely Changed Files

- `services/enrich-worker/geocode.py` (NEW)
- `services/enrich-worker/photo.py` (NEW)
- `services/enrich-worker/enrich.py` (extend `enrich_lead()`)

## Validation Suite

Required validation:

- `uv run python -c "from enrich_worker.geocode import geocode_address; print('ok')"`
- `uv run python -c "from enrich_worker.photo import classify_photo; print('ok')"`
- `uv run ruff check services/enrich-worker/`
- `uv run pytest services/enrich-worker/tests/ -v`
- `git diff --check`
