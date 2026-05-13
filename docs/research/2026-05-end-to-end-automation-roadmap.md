# End-to-End Automation Roadmap (May 2026)

This roadmap is the prioritized engineering plan to move StormLead from local synthetic proof to **practically end-to-end automated** real-traffic operation: leads in → qualified → sold → delivered → paid → learned-from, all without manual ops intervention in normal flows.

It supersedes earlier ad-hoc gap lists. It is explicitly **not** a compliance/legal audit (the existing code-level controls remain in force) and **not** a stack-migration plan (we stay on Python; the prior TS/Node pivot decision is reversed — see §5 decision 1).

## 1. North star

A real-traffic system that runs without an operator in the loop for normal cases:

1. Lead enters via public ingress (Formbricks webhook, landing page form, call tracking).
2. Enriched and qualified by AI through the existing LiteLLM proxy.
3. Auctioned to eligible buyers via the existing ping-post engine.
4. Delivered to a real (not mock) buyer with signed PII to the winner only.
5. Wallet debited via the existing `BillingEvent` ledger; buyer top-ups via Stripe.
6. Unsold or rejected leads nurtured via real SMS, voice, and email providers.
7. Returns processed via deterministic rules with audit trail.
8. Ad spend ingested daily from Google/Meta/Microsoft; auto-pause on losses; budget increases approval-gated.
9. The existing `hermes-self-evolution` weekly cron emits structured learning proposals that canary-deploy and auto-roll-back on regression.

## 2. Verified current state

Reality-check from code review. File:line citations are anchored to current `main`-derived state.

- **Auction works.** `services/ping-post/src/ping_post/auction.py:421-481` preserves completed bids on timeout via `asyncio.wait(..., return_when=ALL_COMPLETED)` with explicit pending-task cancel + record. Wallet debit at lines 336-356.
- **Form receiver: webhook signed, idempotent.** `services/form-receiver/src/form_receiver/api.py`. Call tracking webhook already enforces HMAC-SHA256 + 5-minute replay window + idempotent UPSERT on `call_id` at `services/form-receiver/src/form_receiver/call_tracking.py:31-67`.
- **Hard duplicate suppression exists locally.** `services/form-receiver/src/form_receiver/storage.py` raises `DuplicateLeadError` for recent same phone/address/storm captures before insert, backed by normalized-address resale fields and tested in `services/form-receiver/tests/test_storage.py`.
- **TrustedForm hostname allowlist already enforced.** `services/form-receiver/src/form_receiver/compliance.py:16-30` rejects non-allowlisted hosts, IPs, and userinfo before any Authorization header is sent.
- **Nurture state and local suppression gate correct.** `services/agent-runtime/src/agent_runtime/nurture.py` only marks NURTURED if the outreach call returns `sent=True`. Missing `NURTURE_WEBHOOK_URL` returns a local outbox pending result (no silent success). Active `channel_suppressions` now mark SMS/email/voice entries as suppressed, expose no dispatchable `outbox_channels`, and skip generic webhook side effects. The current optional "send" remains a local-safe generic webhook POST, not a real provider — Twilio/SendGrid provider sends remain P1.2/P1.3 work behind explicit approval.
- **Hatchet workflows registered.** `services/agent-runtime/src/agent_runtime/worker.py:51-67` registers `qualify-lead`, `nurture-lead`, and the weekly `hermes-self-evolution` cron (Mon 09:00 UTC).
- **Wallet ledger and local refill audit exist.** `BillingEvent` is append-only and includes first-class `external_event_id` payment idempotency. Local refill events now write redacted `payment_webhook_events` receipts with processed/ignored/failed states, payment-event advisory locks, and buyer-row credit locking before ledger credit. Live Stripe checkout/session/webhook handling is still absent and approval-gated.
- **Outreach schema groundwork exists.** `outreach_attempts` and `channel_suppressions` provide provider-neutral audit, idempotency, and opt-out persistence for future SMS/email/voice work; no Twilio/SendGrid client or provider send worker is present.
- **Buyer sandbox certification contract exists locally.** `GET /v1/buyers/{buyer_id}/sandbox-certification` returns a dry-run ping/post schema, HMAC auth contract, timeout/retry policy, and missing requirements without contacting buyer webhooks. Real buyer endpoint certification remains P0.3 and approval-gated.
- **Exception queue and provider kill-switch status exist locally.** The admin API exposes unresolved autopilot exceptions without lead PII, `exception_queue` provides durable owner/SLA schema groundwork, `POST /v1/admin/autopilot/exceptions/sync` materializes computed exceptions idempotently with owner/SLA metadata, `GET /v1/admin/autopilot/exception-queue/summary` groups active durable exceptions by owner/status/severity/kind/SLA/operations area without PII, the local admin dashboard surfaces those aggregates above the exception table, and `GET /v1/admin/provider-kill-switches` reports SMS/email/voice/buyer-delivery/payments/ads/storage pause flags without contacting providers.
- **AI calls are correct for production.** `services/agent-runtime/src/agent_runtime/execution.py:138-160` posts to `${LITELLM_PROXY_URL}/v1/chat/completions` via `httpx`. Direct provider SDK ban enforced by AST test at `services/agent-runtime/tests/test_litellm_policy.py:54-68`. Keep this pattern; do not introduce direct `openai`/`anthropic` imports in runtime services.
- **Apps exist.** `apps/landing` (port 8005), `apps/buyer-portal` (port 8004), and local-preview `services/voice-bridge` (Compose profile `voice`, port 8006).
- **Voice-bridge is local-preview only.** `services/voice-bridge/` exposes health/readiness and follow-up preview contracts that explicitly do not contact phone providers; provider-backed calls, transcripts, and status callbacks remain P1.1 work behind explicit approval.
- **Storm-watcher local proof exists.** NWS, FEMA, and NHC/Tropycal pollers normalize events and the worker registers Hatchet cron tasks. Local synthetic worker tests prove poll -> normalize -> upsert orchestration without external HTTP or DB writes; production polling service execution remains deploy/config-gated.
- **Stripe / Twilio / SendGrid not present.** Zero imports across all `pyproject.toml` files.

## 3. Gap list (priority-ordered)

Sizing legend: **S** = days, **M** = 1–2 weeks, **L** = 2–4 weeks, **XL** = 4+ weeks.

### P0 — required for any real end-to-end traffic

#### P0.1 Hard duplicate suppression — **S** — local implementation exists

- **Files**: `services/form-receiver/src/form_receiver/storage.py`, `libs/stormlead_core/src/stormlead_core/dedup.py`, `libs/stormlead_db/migrations/versions/0010_lead_resale_dedup.py`, and `services/form-receiver/tests/test_storage.py`.
- **Current**: recent same phone/address/storm captures are hard-rejected before insert with `DuplicateLeadError`; normalized-address resale fields and a sellable-lead unique index protect the database layer.
- **Remaining**: keep migration-backed local smoke/simulation proof current before real traffic; do not reintroduce page-hash-only uniqueness as the sellability guard.
- **Accept**: same phone/address within the 72h duplicate window is rejected without creating a sellable lead, regardless of `page_html_hash`.

#### P0.2 Production deployment to Hetzner us-east or us-west — **M**

- **Files**: `infra/compose/prod/` (placeholder), `.github/workflows/` (placeholder), new systemd unit, Caddy configuration.
- **What**: real prod docker-compose derived from the dev compose, systemd unit per CLAUDE.md, Caddy edge with TLS, secrets via SOPS-encrypted `.env.prod` per architectural-fit doc. **Hetzner Ashburn (us-east) or Hillsboro (us-west) only** — Falkenstein/Helsinki adds 150–200ms RTT and breaks the `<5s` auction budget.
- **Accept**: public `https://` domain serves admin login, smoke test passes against prod URL, lead capture from `apps/landing` reaches Postgres in prod.

#### P0.3 At least one real buyer integration certified — **M**

- **Files**: `services/ping-post/src/ping_post/auction.py` post path (~lines 336-356), new buyer config in seed/production data.
- **Current**: local dry-run certification endpoint standardizes the buyer ping/post schema, response codes, HMAC auth method, timeout/retry policy, and pre-activation missing-requirement report without contacting a buyer endpoint.
- **Remaining**: validate a synthetic lead against an approved buyer sandbox endpoint, then onboard one real buyer with signed payload verification.
- **Accept**: real buyer accepts sandbox lead; real lead delivered with signed PII to winner only; debit recorded in `BillingEvent`; return workflow exercised end-to-end.

### P1 — required for full nurture / payment / acquisition loop

#### P1.1 Voice bridge with Twilio — **L**

- **Files**: extend existing local-preview `services/voice-bridge/` (FastAPI + future Twilio Programmable Voice + LiteLLM proxy for AI conversation).
- **What**: outbound dial unsold leads, inbound from tracked numbers, AI agent via LiteLLM. Twilio Media Streams for real-time transcription. Recording + transcript stored in Postgres. Status callbacks signed and idempotent (reuse the pattern from `call_tracking.py:31-67`). Voicemail policy explicit (allowed templates only, max attempts, no PII-heavy content). **Use Twilio not jambonz** — jambonz needs real Linux per CLAUDE.md; Twilio works in Docker anywhere. The current dev Compose profile remains local-preview only until an explicit provider-integration approval.
- **Accept**: voice-bridge places a real test call, AI converses via LiteLLM, opt-out phrase detected and honored, transcript stored, status callback recorded idempotently.

#### P1.2 SMS provider integration (Twilio Programmable Messaging) — **M**

- **Files**: extend `services/agent-runtime/src/agent_runtime/nurture.py` from local-safe outbox/suppression decisions to an approval-gated Twilio client. Reuse existing `outreach_attempts` and `channel_suppressions` schema in `libs/stormlead_db/src/stormlead_db/tables.py`.
- **What**: STOP/START/HELP handling, delivery receipts, opt-out suppression mirrored from provider state. Replace generic `NURTURE_WEBHOOK_URL` POST with provider-backed send only after explicit provider-integration approval.
- **Accept**: STOP from a phone number blocks all future SMS to that number; HELP returns the approved response; delivery callback updates `outreach_attempts` state.

#### P1.3 Email provider integration (SendGrid) — **M**

- **Files**: same `nurture.py` plus a new email sender module; reuse existing `outreach_attempts` and `channel_suppressions` schema.
- **What**: SendGrid client, List-Unsubscribe header + body unsubscribe link, bounce/unsubscribe/spam-report event webhook (signed and idempotent). Domain auth + sender reputation tracking deferred to post-launch.
- **Accept**: bounce or unsubscribe blocks future non-transactional email to that address; event webhook idempotent on provider event ID.

#### P1.4 Stripe wallet top-up + auto-refill — **L**

- **Files**: existing schema/logic groundwork includes `payment_customers`, `wallet_autorefill_rules`, `payment_webhook_events`, `BillingEvent.external_event_id`, and the local `/v1/payments/refill-events` audit/idempotency path in `services/ping-post/src/ping_post/api.py`. Remaining work is the signed Stripe webhook handler module (in `services/form-receiver/` or a new `services/payments/`) and checkout/session orchestration.
- **What**: hosted Stripe Checkout for buyer top-ups; webhook handler with signature verification, idempotency on `event.id`; auto-refill rule (threshold, refill amount, daily/monthly cap, failure handling). Preserve the local audit ordering: receive redacted payment event receipt, serialize provider event/payment intent/idempotency keys, then credit the wallet only for verified successful events. Wallet balance computed from ledger, not from reports. Sandbox first; live mode requires finance sign-off (see §5 decision 4).
- **Accept**: sandbox top-up creates a signed provider receipt plus `deposit_available` ledger event; duplicate webhook is idempotent and audit-visible; conflicting/failed webhook never credits wallet; auto-refill triggers below threshold and respects caps.

#### P1.5 Storm-watcher production polling — **M**

- **Files**: `services/storm-watcher/`. Hatchet cron registration follows the `worker.py:51-67` pattern.
- **Current**: Tropycal/NWS/FEMA pollers and Hatchet cron registration exist, with local synthetic tests covering poll orchestration and outside-season NHC skip behavior without external HTTP. Local persistence proof now preserves synthetic `impacted_zips` in `storms.raw` and exposes a normalized query helper that returns landing-page-consumable ZIP lists from persisted storm rows.
- **Remaining**: run the storm-watcher service in a local disposable stack against Postgres/PostGIS, then deploy the production polling service only after environment and infrastructure approval.
- **Accept**: storm event in NWS feed reaches Postgres within 1 hour; impacted-zip query produces a list landing-page geo-targeting can consume.

### P2 — required for self-running optimization

#### P2.1 Ad spend ingestion + campaign registry — **L**

- **Files**: new tables `campaigns`, `campaign_spend_snapshots`, `tracking_links` in `libs/stormlead_db/`. New service or worker for daily ingestion.
- **Current**: local schema groundwork declares `campaigns`, `campaign_spend_snapshots`, and `tracking_links` with idempotent platform campaign/date uniqueness and UTM/click-id mapping tests; no ad platform APIs are contacted.
- **What**: Google Ads API (`google-ads` Python), Meta Business SDK (`facebook-business`), Microsoft Ads (`msads`); store daily spend snapshots; map UTM/click-IDs at lead capture; reconcile to platform UI within tolerance daily.
- **Remaining**: add an approval-gated ingestion worker/client for the first selected ad platform and reconcile local snapshots to provider UI exports.
- **Accept**: at least one platform's daily spend total in StormLead matches the platform UI within accepted variance; every paid lead has source/campaign/click identifiers.

#### P2.2 Budget pacing rules (asymmetric) — **M**

- **Files**: new module in `services/agent-runtime/` or new `services/spend-ops/`. New `budget_action_logs` table.
- **What**: deterministic auto-pause on CPL/ROAS loss thresholds + minimum sample size + cooldown; budget **increases** require admin approval (not auto). Per-platform kill switches.
- **Accept**: a campaign exceeding the loss threshold auto-pauses with a logged action; an increase proposal appears in the admin UI for approval; cap breach blocked.

#### P2.3 Learning proposal store + canary deploy — **L**

- **Files**: extend `hermes-self-evolution` cron at `services/agent-runtime/src/agent_runtime/worker.py:51-67`. New `learning_proposals` table.
- **What**: hermes already runs weekly; today its output is observed but not propagated to live policy. Add: structured proposals (scoring threshold, cadence change, prompt update), replay tests on historical leads, canary deploy (apply to N% of traffic), automatic rollback if guardrail metrics regress.
- **Accept**: a hermes proposal canary-deploys to 5% of traffic; if conversion rate drops more than the configured threshold, automatic rollback fires; admin promotes to 100% only on manual approval.

#### P2.4 Exception queue + SLO dashboards + kill switches — **M**

- **Files**: `libs/stormlead_db/src/stormlead_db/tables.py`, `services/ping-post/src/ping_post/api.py`, future admin UI extensions in `services/ping-post/src/ping_post/admin/`.
- **Current**: admin APIs compute unresolved exception items from local audit rows, `POST /v1/admin/autopilot/exceptions/sync` writes them into the durable `exception_queue` idempotently with owner/SLA metadata, `GET /v1/admin/autopilot/exception-queue/summary` gives dashboard-ready active counts by owner/status/severity/kind/SLA/operations area, the local admin page renders that read-only aggregate strip, provider kill-switch status is exposed from pause environment flags without provider contact or credentials, and `POST /v1/admin/provider-kill-switches/change-plan` returns approval-required config and rollback steps for pause/resume changes without mutating runtime state.
- **Remaining**: wire the approved config-management system that applies kill-switch changes after explicit operator approval.
- **Accept**: a buyer-timeout cluster generates an exception with owner + SLA; flipping the SMS kill switch stops outbound SMS within 60 seconds.

## 4. Sequencing and timeline

Realistic small-team estimate (1–2 engineers):

| Phase | Items | Calendar weeks |
|---|---|---|
| Phase 1 (P0) | P0.1, P0.2, P0.3 | 4–6 |
| Phase 2 (P1 channels + payments) | P1.1, P1.2, P1.3, P1.4 | 6–10 (parallelizable) |
| Phase 3 (P1 storm + P2 spend) | P1.5, P2.1, P2.2 | 4–6 |
| Phase 4 (P2 learning + ops) | P2.3, P2.4 | 4–6 |

**Total: 18–28 weeks to "practically end-to-end automated."**

Aggressive parallelism (2–3 engineers) compresses to 12–18 weeks. Single engineer extends to 30–40+ weeks.

## 5. Decision points

These belong to the user/business, not engineering. They must be resolved before or during execution to avoid stalling work.

1. **Confirm Python-stack-stays.** This roadmap reverses the earlier TS/Node pivot decision because the Python stack already has ~70% of the system built and rewriting adds 8–12 weeks of zero functional progress. If TS/Node migration is still required, sequence it after launch.
2. **Pick the first real buyer for P0.3.** Business decision: which contractor or roster account onboards first.
3. **Twilio account + 10DLC SMS registration.** Owner and timeline; 10DLC registration takes 1–4 weeks calendar time, so start early.
4. **Stripe live-mode activation timing.** Owner and finance sign-off; sandbox work in P1.4 can begin before live activation is decided.
5. **Which ad platform first for P2.1.** Google Ads typically has highest signal density; Meta if storm-event geographic targeting is more important than search intent.

## 6. Out of scope

- **TS/Node migration.** Deferred until post-launch; revisit if the Python stack hits a concrete bottleneck.
- **Compliance posture changes** beyond what current code already enforces.
- **Multi-region deployment.** Single Hetzner US region per architectural-fit doc; multi-region is a v1.1+ concern.
- **Jambonz / SIP / RTP voice.** Use Twilio.
- **Direct mail (Lob, PostGrid), call tracking platform (CallRail), address verification (USPS).** Defer to post-launch as P3.
- **Buyer self-service portal feature expansion** beyond delivery, wallet, and returns.

## 7. Existing assets to reuse

Do not rewrite these — extend or reference them:

- `services/ping-post/src/ping_post/auction.py:421-481` — auction timeout handling. Keep as-is.
- `services/form-receiver/src/form_receiver/call_tracking.py:31-67` — HMAC + replay + idempotent UPSERT pattern. Port to Stripe webhooks (P1.4) and Twilio status callbacks (P1.1, P1.2).
- `services/form-receiver/src/form_receiver/compliance.py:16-30` — TrustedForm allowlist pattern. Reuse for any outbound URL-validating egress (Stripe webhook host validation, etc.).
- `services/agent-runtime/src/agent_runtime/execution.py:138-160` — LiteLLM call pattern with `cost_cap_usd`. Reuse for the voice-bridge AI conversation in P1.1.
- `services/agent-runtime/src/agent_runtime/worker.py:51-67` — Hatchet workflow registration pattern. Reuse for storm-watcher cron (P1.5), spend ingestion cron (P2.1), and learning canary (P2.3).
- `libs/stormlead_db/src/stormlead_db/tables.py:283-298` — `BillingEvent` table. Extend with `external_event_id` for P1.4 idempotency rather than adding a parallel table.
- `infra/litellm/config.yaml` — model routing tiers (`agent-default`, `bulk-offline`). Voice-bridge uses these without changes.

## 8. Cross-references

- `docs/research/2026-05-architectural-fit.md` — stack constraints (Hetzner regions, deferred Temporal/NATS/SeaweedFS/OpenBao).
- `docs/research/2026-05-stack-improvements.md` — LiteLLM pin updates and Hatchet v1 migration notes.
- `docs/research/v1-paid-pilot-runbook.md` — local technical V1 controls; this roadmap is the production extension.
- `tools/TOOLS.md` — runtime LLM call routing; the LiteLLM-only policy stays in force.
- `CLAUDE.md` — operating constraints (Hetzner regions, no direct provider SDKs, no Rust, no jambonz in WSL2).
