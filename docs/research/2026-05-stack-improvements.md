# stack improvements — verification + architectural critique

synthesis of (a) web verification of the time-sensitive claims in `2026-05-stack-audit.md` and `2026-05-forkable-stack.md`, and (b) gaps in those docs' coverage of business mechanics. produced during the build-review pass; intended as a living "next moves" register, not a verbatim research artifact.

## TL;DR

- **two security/legal items genuinely changed since the prior docs**: a fresh litellm cve, and the death of the fcc one-to-one consent rule.
- **the prior docs cover the tools layer well; they're silent on the lead-flow business mechanics layer** — dedup, fraud scoring, buyer disputes, dnc scrub, buyer onboarding, billing. these are where ping-post businesses actually fail.
- **single-host hetzner + postgres-doing-everything is a near-term cliff.** plan the split before scaling.

---

## Part 1 — verified shifts since the prior docs

| claim in prior docs | current state (2026-05) | action |
|---|---|---|
| pin litellm `v1.83.4-stable` | **CVE-2026-42208** sql-injection hits v1.81.16 → v1.83.6; fixed in **v1.83.7-stable**. cosign-signed images from v1.83.0 forward. | bump pin; enforce cosign-verify on deploy. |
| hatchet `v0.50.0` is healthy | **hatchet v1 rewrite shipped mar 2025**. v0.50 is on the legacy branch. current ~v0.83.x on the v1 architecture; schema/api differs. | fine for hobby load. plan migration before scaling past ~hundreds-of-leads/day. |
| langfuse v3 self-host current | server v3 still current, mit, no v4-server announcement. **python/js sdks rewrote to v4 on otel in mar 2026**. | server pin fine. client code may need updates when sdks bump. |
| postgres-mcp = `crystaldba/postgres-mcp:latest` | confirmed the right alternative (anthropic ref still archived). v0.3.0 latest. | pin a specific tag, not `:latest`. |
| twenty crm = agpl-3.0 | confirmed; no license flip. api-only integration via `TWENTY_API_URL` keeps you safely outside agpl combined-work boundary. | safe as wired. do not vendor twenty source. |
| formbricks = agpl-3.0 + paid ee | confirmed. enterprise gates sso/saml/oidc + advanced rbac. | per-file license check on `packages/js` widget before embedding in any closed-source product. |
| ultralytics yolov8/v11 = agpl-3.0 | confirmed; no softening. | use florence-2 / detectron2 / rf-detr for any closed-source vision. |
| tropycal actively maintained | **snyk classifies "inactive"** — minimal pr/issue activity in early 2025. functional. | plan a fork or fallback (raw hurdat2 / ibtracs) before relying on it operationally. |
| nws cap, openfema apis free | confirmed, both still keyless/free. | — |
| hetzner blocks port 25 outbound | confirmed; unblock only after first paid invoice. | use postmark/ses/resend as transactional esp; don't fight ip reputation. |
| **fcc one-to-one consent rule is the threat model** | **rule is dead.** 11th circuit (insurance marketing coalition v. fcc) vacated jan 24 2025; fcc formally abandoned via final rule aug/sep 2025. pre-2023 pewc standard restored (writing + signature + clear disclosures, no per-seller specificity). | **architectural simplification**: don't need separate consent records per buyer. one solid pewc audit per lead is sufficient. |
| state laws: fl, tx, nc flagged | **florida sb 290 signed mar 2026** (no-solicitation enforcement + subcontractor-payment penalties). **texas hb 3344 in motion** (tdlr licensing for roofers, explicitly anti-storm-chaser). nc no recent update surfaced. | if operating in fl or tx, buyer-licensing verification becomes mandatory before bid. |

## Part 2 — what the prior docs don't address

these are the layers between "the tools work" and "the business runs." every one of them is a real failure mode for ping-post businesses; none are in the scaffold or the prior research docs.

### A. lead-flow mechanics

1. **deduplication** — `(phone_e164, address_hash, 24h_window)` check before the auction. without it: same homeowner submits across pseo variants → buyers ping'd twice → buyers refuse to pay second.
2. **fraud / quality scoring** — bots, competitor-submitted poison leads, tire-kickers. inputs: ip reputation, phone validation (twilio lookup / numverify), address validity, altcha pow proof. output: a quality score the auction uses to set floor prices and routing decisions.
3. **buyer dispute flow** — return-window policy, signed delivery receipts, structured dispute path. without it, buyers refuse payment on bad leads and you eat the loss. the `PostResult` table captures delivery; nothing handles disputes.
4. **buyer pacing + slas** — "max 50/day, no weekends, houston-metro only, must accept within 30s." the cel filter handles geographic; quotas/throttles need a separate layer. buyer scorecards (response-time, accept-rate, dispute-rate) feed back into routing.
5. **idempotency on POST-to-winner** — `services/ping-post/src/ping_post/auction.py:351` POSTs with no idempotency key. network blip on retry → double-delivery → double-charge dispute. one-line fix.
6. **webhook retry on buyer-POST failure** — if the winner is briefly down, the lead is lost. need a `webhook_deliveries` queue with retry+backoff. river-style; hatchet can do it but isn't wired.

### B. compliance not addressed

7. **dnc scrub** before voice-bridge dials. federal. budget time when voice-bridge stops being a stub.
8. **consent audit immutability** — rrweb + playwright screenshot + s3, content-addressed. courtroom artifact when a tcpa suit lands. form-receiver is empty; build this before first dial.
9. **state-licensing verification on buyers** — fl, tx (post-hb-3344), nc. block bids from unlicensed contractors per geo.
10. **pii redaction in logs** — `auction.py` and `api.py` log full lead objects via structlog. ccpa/gdpr exposure. add a structlog processor that scrubs phone/email/address by default.

### C. money flow

11. **buyer onboarding** — kyb, signed lead-purchase agreement, w-9, payment-on-file (stripe customer + ach debit auth). no flow exists today.
12. **invoicing + ar** — `BillingEvent` table exists; no stripe integration, no invoice generation, no aging report.

### D. reliability

13. **single hetzner host = spof**. minimum: nightly pgbackrest to storage box, hot-standby postgres, status page.
14. **apm not wired** — `.env.example:75` has `SENTRY_DSN_GLITCHTIP=` empty. langfuse traces llm calls, not python exceptions in the auction engine. glitchtip in compose + sentry-sdk in `stormlead_core` + dsn in services = ~30 min.
15. **no alerting** — healthchecks present in compose; no alert routing (opsgenie / pagerduty / ntfy).

### E. cost + scaling cliffs

16. **claude api spend uncapped** — agent-runtime can rip through budget. per-tenant spend limits + auto-downgrade-to-haiku via litellm budgets.
17. **postgres doing too much** — hatchet queue + langfuse oltp + pgvector + business data on one box. connection-limit cliff at hundreds of concurrent agents. plan to split (move hatchet or langfuse to sibling) before 1k leads/day.
18. **no cdn on pseo** — 50k landing pages from one hetzner box, served globally. cloudflare cache is free; do it day one.

---

## Recommended sequence

### this week (must-fix; blocks anything real)
1. bump litellm pin to **v1.83.7-stable**; remove every `:latest` tag in compose; add `cosign verify` to deploy.
2. update internal compliance posture: one-to-one consent rule is dead; one solid pewc audit per lead suffices.
3. pin `crystaldba/postgres-mcp` and `langfuse/langfuse:3` to exact tags.
4. wire idempotency-key header on the buyer POST in `auction.py`.
5. wire glitchtip into compose; add `sentry-sdk` to `stormlead_core` with a pii scrubber.

### before first paying buyer (legal + money gates)
6. consent-audit pipeline (rrweb + playwright + s3) in form-receiver.
7. buyer onboarding flow (kyb + signed agreement + payment-on-file).
8. state-licensing verification (fl, tx) at buyer-create.
9. dnc scrub layer (subscription-based; not free).
10. stripe integration + invoicing.

### before scaling past hobby load (~100 leads/day)
11. hatchet v0.50 → v1 migration.
12. lead dedup + fraud-scoring layer.
13. buyer dispute flow + scorecards.
14. webhook delivery retry queue.
15. postgres workload split (hatchet or langfuse to a sibling instance).
16. hot-standby postgres + offsite backups + status page.
17. cloudflare in front of pseo landing pages.

### deferred / "after first 3 buyers"
18. fork or replace tropycal (snyk: inactive).
19. langfuse python sdk v3 → v4 migration.
20. multi-region read replica for landing-page postgres.
21. retention story (lapsed-buyer reactivation; repeat homeowner; referral).
