# Louisiana One-Buyer Paid Canary Runbook

Status: code-completable canary path; live DNS, Stripe live mode, buyer endpoint calls, and Google Ads spend remain explicit approval actions.

## Scope

- Market: Louisiana.
- First metro: Greater New Orleans / Southeast Louisiana.
- Backup metro: Baton Rouge.
- Buyer count: one approved buyer for the canary only.
- Service: `tree_removal`.
- Ad platform: Google Search only.
- Budget: `$100/month`, defaulting to `333` cents/day and `10000` cents/month.
- Payment proof: Stripe sandbox before any live payment action.

This runbook does not replace the full three-buyer paid-pilot gate at `GET /v1/admin/launch-readiness`.
Use `GET /v1/admin/canary-readiness` for the narrower one-buyer Louisiana canary.

## Deployment Choice

Preferred first host: Hetzner Cloud Ashburn.

Fallback: AWS Lightsail Linux instance if AWS billing/support simplicity matters more than lowest cost.

Avoid Vercel for the backend canary because StormLead needs long-running Python services, Postgres, RabbitMQ/Hatchet, and Caddy. Vercel can host a static landing page later, but not the full canary backend without a redesign.

Lean public canary stack:

- Ubuntu LTS.
- Docker and Docker Compose plugin.
- Caddy edge with TLS when DNS is available.
- Postgres.
- RabbitMQ and Hatchet.
- `form-receiver`.
- `ping-post`.
- `landing`.
- `agent-runtime` only when AI qualification is enabled.

Keep these out of the first canary unless needed: Kubernetes, multi-region, full Langfuse/ClickHouse, automated Google Ads mutation, SMS/email/voice provider sends.

## Required Environment

Use an ignored `.env.prod` or secret store. Never commit real values.

Canary-safe payment setup:

```text
STORMLEAD_APPROVE_PAYMENTS_SANDBOX=true
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STORMLEAD_APPROVE_PAYMENTS_LIVE=false
STORMLEAD_PAUSE_PAYMENTS=false
```

Operator and buyer safety:

```text
STORMLEAD_REQUIRE_OPERATOR_TOKEN=true
STORMLEAD_OPERATOR_TOKEN=<secret>
STORMLEAD_REQUIRE_BUYER_API_KEY=true
STORMLEAD_PAUSE_ADS=false
STORMLEAD_PAUSE_BUYER_DELIVERY=false
```

Public ingress headers:

```text
# Leave blank for local/self-hosted placeholder Formbricks assets.
# Set only the exact external origins needed for a hosted Formbricks embed/API.
FORMBRICKS_CSP_SCRIPT_SRC=
FORMBRICKS_CSP_CONNECT_SRC=
```

Caddy should keep `Permissions-Policy` at `geolocation=(self), camera=(), microphone=()` so the landing GPS proof can work on the same origin without enabling camera or microphone access. The ingress validator checks these header snippets.

Live actions remain parked until explicitly approved:

```text
STORMLEAD_APPROVE_PAYMENTS_LIVE=false
STORMLEAD_APPROVE_ADS_LIVE=false
STORMLEAD_APPROVE_BUYER_DELIVERY_LIVE=false
```

## Readiness Endpoints

One-buyer Louisiana canary:

```powershell
$headers = @{ Authorization = "Bearer $env:STORMLEAD_OPERATOR_TOKEN" }
Invoke-RestMethod "http://localhost:8003/v1/admin/canary-readiness?market_state=LA&service=tree_removal&monthly_budget_cents=10000&daily_budget_cents=333&require_sold_evidence=true" -Headers $headers
```

Full paid-pilot marketplace gate, still requiring three funded buyers:

```powershell
$headers = @{ Authorization = "Bearer $env:STORMLEAD_OPERATOR_TOKEN" }
Invoke-RestMethod "http://localhost:8003/v1/admin/launch-readiness?market_state=LA&service=tree_removal&campaign_budget_cents=10000" -Headers $headers
```

## Stripe Sandbox Proof

1. Create a refill intent with `provider=stripe`.
2. Complete the returned Stripe Checkout Session with a Stripe test card.
3. Configure Stripe to send `checkout.session.completed` to `/v1/payments/stripe/refill-webhook`.
4. Verify the signed webhook credits the buyer wallet exactly once.
5. Replay the webhook and verify idempotency.
6. Send a failed/non-creditable event and verify no wallet credit.
7. Send or replay a signed `livemode=true` event and verify the sandbox endpoint rejects it.

The generic local endpoint `POST /v1/payments/refill-events` still rejects non-local provider events. Stripe credits must arrive through the signed Stripe webhook endpoint.

Payment/refill failures return a stable JSON detail envelope:

```json
{
  "detail": {
    "message": "payment provider action is not approved",
    "error_code": "payment_provider_not_approved",
    "provider_gate": {},
    "approval_packet": {}
  }
}
```

Operators should key automation and dashboards off `detail.error_code`; use `detail.message` for human-readable review.

## Landing And Attribution

Use the Louisiana landing path:

```text
/louisiana-storm-tree-removal?utm_source=google_ads&utm_medium=paid_search&utm_campaign=la-canary&gclid=<gclid>
```

The landing page forwards these fields into the Formbricks-style hidden fields:

- `utm_source`.
- `utm_medium`.
- `utm_campaign`.
- `gclid`.
- `consent_version`.

The local synthetic form defaults to New Orleans, LA, zip `70112`.

Buyer portal browser proof should use a real rotated buyer API key for wallet access. Cross-buyer key reuse must be rejected without setting `buyer_id` or `buyer_api_key` cookies; synthetic funding remains operator-gated.

## Google Ads Canary

Start manual only. Do not automate Google Ads campaign creation for the first canary.

Campaign settings:

- Network: Search only.
- Location: buyer-covered Louisiana zips only.
- Budget: `$3.33/day`.
- Monthly cap: `$100`.
- Match types: exact and phrase.
- Display and Performance Max: off.

Keywords:

- `"emergency tree removal new orleans"`.
- `"storm tree removal"`.
- `"fallen tree removal"`.
- `"tree on house removal"`.
- `"hurricane tree cleanup"`.
- `[emergency tree service near me]`.

Negative keywords:

- `jobs`.
- `salary`.
- `free`.
- `diy`.
- `firewood`.
- `city pickup`.
- `permit`.
- `chainsaw`.
- `trim`.
- `pruning`.

## Verification Commands

Run focused proof after code changes:

```powershell
uv run pytest -q services/ping-post/tests/test_integration.py apps/landing/tests/test_local_demo_gate.py
npm run validate:compose
npm run validate:ingress
node --check scripts/validate_ingress_targets.mjs
git diff --check
```

Run the larger release gate before real traffic:

```powershell
uv run ruff check services libs scripts/smoke_e2e.py scripts/replay_lead.py scripts/simulate_v1_leads.py
uv run pytest -q services libs
uv run mypy services libs
uv run python scripts/smoke_e2e.py
uv run python scripts/simulate_v1_leads.py
npm run test:playwright -- --project=chromium --reporter=line
git diff --check
```

## Go/No-Go

Go when all are true:

- `/v1/admin/canary-readiness` returns `technical_canary_ready=true`.
- One Louisiana buyer has covered zips, price, caps, wallet, and delivery path.
- Stripe sandbox wallet refill credits exactly once from a signed webhook.
- Landing capture preserves Google Ads attribution.
- Offline conversion export dry-run works.
- Ads, payments, and buyer delivery kill switches are visible and unpaused for the approved scope.

Still not go until explicitly approved:

- DNS/public traffic.
- Stripe live mode.
- Buyer endpoint contact with PII.
- Google Ads spend.
