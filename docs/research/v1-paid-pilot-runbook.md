# V1 Local Technical Runbook

Date: 2026-05-04

Status: local technical readiness.

## Local-Only Mode

- Keep this runbook scoped to local commands and local service checks.
- Do not expose services publicly or register public webhooks from this runbook.
- Do not create fake revenue, fake buyer commitments, or fake campaign evidence outside explicit local smoke/test paths.

## System Of Record

- `lead_state_transitions` records capture, enrichment, qualification, auction, sale, admin review, and buyer-review events.
- `post_results.delivery_idempotency_key` prevents duplicate paid delivery rows for the same lead, buyer, and bid.
- Buyer review rows store evidence keys, review status, operator notes, and approved wallet adjustments.
- `billing_events` remains the append-only wallet ledger for reserves, deposits, failed-delivery adjustments, and approved buyer-review adjustments.

## Local Setup

```powershell
cp .env.example .env
docker compose --env-file .env -f infra/compose/dev/docker-compose.yml up -d
$env:DATABASE_URL="postgresql+psycopg://stormlead:change-me-in-openbao@localhost:5433/stormlead"
uv run python scripts/init_db.py
Push-Location libs/stormlead_db; uv run alembic upgrade head; Pop-Location
uv run python scripts/seed_dev.py
```

Use `just up`, `just migrate`, and `just seed` only when `just` is installed.

## Capture And Attribution

- Formbricks webhooks post to `POST /webhooks/formbricks` on `form-receiver`.
- The receiver rejects oversized bodies using `FORM_RECEIVER_MAX_WEBHOOK_BODY_BYTES` before parsing.
- Hidden fields can provide `requested_service`, `campaign_id`, `campaign_source`, `first_touch_source`, and `last_touch_source`.

## Buyer Controls

- A buyer must be active, funded, inside daily cap, inside monthly budget, and match both service and zip rules before routing.
- Exclusive zip conflicts block buyer create/update.
- Buyer daily reports are available at `GET /v1/buyers/{buyer_id}/daily-report`.
- The report includes delivered leads, gross spend, reviewed adjustments, pending buyer reviews, cap remaining, low-balance status, and refill recommendation.

## Buyer Review Workflow

1. Buyer submits the review endpoint with a reason, optional notes, optional evidence, and reviewer identity.
2. StormLead stores a buyer-review row with `pending_review` and records a timeline event.
3. Operator reviews through the admin review API with action `approve`, `hold`, or `reject`.
4. Only `approve` writes a wallet adjustment and records the review outcome.
5. One active buyer review is allowed per `post_result`.

## Readiness Endpoint

Call scoped readiness locally:

```powershell
Invoke-RestMethod "http://localhost:8003/v1/admin/launch-readiness?market_zip=78701&service=tree_removal&campaign_budget_cents=100000"
```

The endpoint returns:

- `technical_local_ready`: true only when scoped technical evidence exists.
- `ready_for_paid_launch`: true only when technical gates pass and the local launch flag is intentionally set.
- `readiness_label`: `not_ready`, `technical_local_ready`, or `commercial_paid_launch_ready`.

## Evidence Commands

```powershell
uv run ruff check services libs scripts/smoke_e2e.py scripts/replay_lead.py
uv run ruff format --check services libs scripts/smoke_e2e.py scripts/replay_lead.py
uv run pytest -q services libs
uv run mypy services libs
uv run python scripts/smoke_e2e.py
npm run test:playwright -- --project=chromium --reporter=line
npm run cowork:admin:record
```

If Docker cannot reach the host buyer listener during smoke testing, set `SMOKE_LISTENER_HOST=0.0.0.0` locally and rerun. Keep generated browser and smoke artifacts under ignored `testing/` paths.

If the smoke script returns `503 event emission failed; will retry`, check `HATCHET_CLIENT_HOST_PORT` and `HATCHET_CLIENT_TOKEN`. In-container services should use `hatchet-engine:7070`; an invalid token blocks Hatchet event emission and worker registration.

## Edge Routing

- Dev compose binds exposed ports to `127.0.0.1` by default.
- Caddy proxies only implemented form-receiver and internal ping-post routes.
- Landing, voice, and buyer-portal routes fail closed with `404` until those services are implemented.
