# research

Research artifacts that informed the scaffold's choices. Older audit and forkable-stack notes are preserved as dated background files; use this index for current technical direction.

## docs

- **`2026-05-stack-audit.md`** - dated security and integration audit across candidate repos. Drives the LiteLLM image pin, Postgres MCP choice, Hatchet, Caddy/Coraza, and Langfuse stack.
- **`2026-05-forkable-stack.md`** - dated repo recommendations by layer: storm ingestion, forms, CRM, telephony, landing pages, agent runtime, and vision options.
- **`2026-05-stack-improvements.md`** - verification of time-sensitive claims and technical gaps found after the older research.
- **`2026-05-architectural-fit.md`** - architecture fit review. Current V1 keeps Postgres, Hatchet, FastAPI, and a US-region deployment target while deferring NATS, SeaweedFS, and OpenBao.
- **`2026-05-agent-auth-patterns.md`** - historical agent auth research. Runtime services now use LiteLLM only.
- **`2026-05-04-visual-agentic-workflow-execution-prompt.md`** - dated execution prompt for the admin workflow milestone.
- **`2026-05-04-v1-execution-prompt.md`** - dated execution prompt for the V1 technical-readiness milestone.
- **`visual-agentic-workflow-runbook.md`** - admin workflow timeline, review actions, KPI semantics, and Cowork evidence manifests.
- **`v1-paid-pilot-runbook.md`** - local technical V1 controls, scoped readiness, and evidence commands.

## superseded technical claims

- **litellm pin v1.83.4-stable** -> **v1.83.7-stable**.
- **hatchet v0.50.0 healthy** -> legacy branch; v1 rewrite shipped mar 2025.
- **`crystaldba/postgres-mcp:latest` ok** -> pin a specific tag.
- **tropycal actively maintained** -> inactive since early 2025 in the dated dependency review.
- **nats event bus alongside hatchet** -> cut for V1; Hatchet handles durable workflows on Postgres.
- **seaweedfs as self-hosted s3** -> cut for V1; use a hosted object bucket until storage needs justify more infra.
- **openbao for secrets in v1** -> deferred until a second operator or stronger rotation workflow exists.
- **hetzner falkenstein/helsinki ok for the auction endpoint** -> deploy to Ashburn or Hillsboro to keep buyer round trips low.
- **hybrid oauth/litellm runtime** -> superseded by LiteLLM-only runtime services.

## scaffold divergences from `forkable-stack.md`

- **no suna fork.** Agent-runtime uses a small LiteLLM HTTP client, no Supabase.
- **ping-post is Python.** Rewrite the hot path later only if sustained load proves Python misses the auction budget.
- **no coolify.** Production runs Docker Compose under systemd.

## implementation guide

This guide turns the research and operating model into the next build sequence. Use it as the source of truth when choosing what to implement next.

### product outcome

StormLead should become a self-hosted, buyer-funded lead marketplace:

1. contractors prepay wallets.
2. funded buyer territories decide where homeowner campaigns can run.
3. homeowner forms, calls, and mailer responses create leads.
4. leads are classified as class a, b, c, or d.
5. only class a and class b leads route automatically.
6. successful delivery debits the buyer wallet.
7. operator-reviewed adjustments update the wallet ledger.
8. daily buyer reports drive wallet refills.

### current implemented base

- `services/form-receiver`: captures form leads, writes intake audit rows, persists attribution, and serves local intake pages.
- `services/storm-watcher`: imports storm events from public sources.
- `services/ping-post`: routes leads to buyers, posts winners, debits wallets, and records billing events.
- `services/agent-runtime`: foundation for qualification and agent workflows.
- `libs/stormlead_db`: Postgres schema for storms, buyers, leads, ping attempts, post results, billing events, review requests, intake audit rows, and workflow transitions.
- `infra/compose/dev`: local development stack.

### next build sequence

Build these in order. Do not build the buyer portal, full AI voice, or automated ad buying before this foundation is in place.

1. buyer CRM fields: sales stage, notes, next follow-up, services, target zips, exclusive zips, and low-balance threshold.
2. buyer update, list, wallet, and summary endpoints.
3. territory/service matching inside ping-post eligibility.
4. daily cap and monthly budget enforcement before buyer selection.
5. lead classification fields: class a, b, c, d plus qualification reason.
6. campaign/source attribution fields on leads.
7. admin KPI endpoint for prepaid cash, active buyers, lead revenue, buyer adjustments, and campaign margin.
8. buyer daily report endpoint.
9. buyer review workflow and status model.
10. mailer CSV export for manual vendor upload.
11. low-wallet refill recommendation workflow.
12. call tracking webhook ingestion.
13. voice-bridge skeleton for qualified follow-up workflows.
14. payment/refill links after manual deposits prove buyer refill behavior.

### first technical launch gate

Do not launch homeowner acquisition until all of these are true:

- three funded buyers exist in one market.
- each active buyer has accepted service zips, services, caps, and lead prices.
- available wallet balance covers the planned campaign spend risk.
- landing page and source capture are tested.
- call tracking works for the campaign.
- ping-post can route a test lead to a funded buyer.
- buyer review flow works.
- admin can see buyer wallets, sold leads, reviewed leads, and campaign source.
- campaign budget cap and stop-loss rules are set.

### edge-case matrix

Handle these before the first launch. Each one can create lost cash, buyer disputes, bad routing, or bad attribution if ignored.

Buyer and wallet edge cases:

- wallet balance changes between ping and post: re-check balance in the same transaction that writes `post_results` and `billing_events`.
- two leads debit the same buyer at the same time: lock the buyer row or use an atomic conditional update so the wallet cannot go negative.
- buyer becomes paused after ping but before post: re-check status before delivery.
- buyer webhook accepts ping but fails post: do not debit wallet; mark lead unsold or retry another eligible buyer.
- buyer webhook times out after receiving the delivery payload: store delivery attempt and do not double-post without an idempotency key.
- buyer has enough balance for one lead but not the agreed minimum territory coverage: allow routing but block new campaign spend.
- buyer disputes too many accepted leads: pause buyer or require manual review before more routing.

Lead and routing edge cases:

- same homeowner submits multiple forms from different pages: dedupe by normalized phone, address, storm id, and time window, not page hash alone.
- same household has two decision-makers: keep one sellable household lead unless the service request is materially different.
- lead is in a zip with no funded buyer: classify and hold, but do not spend more or auto-route.
- lead matches multiple exclusive buyers in the same zip: territory conflict must block activation or force manual routing.
- life-safety or downed power-line lead: route through a human-controlled process.
- photos contain unrelated interiors or unrelated people: store privately and limit buyer exposure to needed evidence.

Campaign and attribution edge cases:

- one call comes from a mailer but converts through a Google landing page: preserve first-touch and last-touch attribution.
- QR code is shared between neighbors: track campaign/zip-level attribution first; do not assume per-household identity unless per-recipient tracking exists.
- storm alert false positive or wrong polygon: hold campaign in approval mode until storm severity and target zips are confirmed.
- campaign creates leads faster than buyers can answer: throttle spend and route based on response-speed ranking.
- cost per qualified lead spikes mid-day: pause or cap campaigns automatically when guardrails fail.

Operations edge cases:

- Postgres backup restore fails: no launch until restore has been tested.
- Hatchet workflow retries after partial success: workflow steps must be idempotent by lead id, post result id, and webhook id.
- object storage upload fails for photos/transcripts: keep lead routing dependent only on required fields.
- Caddy routes to unimplemented services in prod: remove or disable those routes before public deployment.
- vendor outage for phone, mail, or payment: queue retries where valid and block spend where conversion tracking is broken.

### self-hosted architecture target

Keep these systems self-hosted because they are the business record:

- buyer CRM.
- buyer wallets.
- lead records.
- lead classification and routing decisions.
- campaign attribution.
- buyer review decisions.
- buyer reports and KPIs.

Use vendors only for unavoidable network edges:

- phone carrier access.
- call delivery.
- payment rails.
- Google/Meta ad delivery.
- physical mail print/postage.
- email relay.

### documentation sections to read before coding

- `self-hosted framework review`: self-hosted boundary and production-readiness gaps.
- `40 percent irr operating model`: business model, unit economics, guardrails, rollout, and KPIs.

## self-hosted framework review

This section is the design review for the current self-hosted framework. It defines what must stay self-hosted, what can use vendors, and what is not yet implementation-ready.

### current verdict

The framework is directionally sound for a single-operator storm/tree lead marketplace because it keeps the important business state under StormLead control:

- homeowner leads in Postgres.
- buyer wallets and billing events in Postgres.
- buyer review decisions in the StormLead ledger.
- lead routing decisions in ping-post.
- storm detection in storm-watcher.
- qualification workflows under Hatchet.

Phone carriers, payment rails, ad platforms, and physical mail delivery are external networks by nature. StormLead should self-host the decisioning, audit trail, routing, and reporting layers while using vendors only for unavoidable network edges.

### self-hosted boundary

Must be self-hosted:

- buyer CRM and wallet state.
- lead capture records.
- campaign attribution records.
- lead qualification class and scoring.
- ping-post routing and buyer selection.
- billing ledger and buyer review decisions.
- agent transcript summaries and decision outputs.
- admin KPIs and buyer reports.

Can use vendors:

- phone numbers, calling, and carrier connectivity.
- card/ACH payment processing.
- Google/Meta ad delivery.
- direct-mail print and postage.
- email relay.
- object storage if configured as private and controlled by StormLead.

Should not be vendor-owned:

- source of truth for wallet balances.
- source of truth for lead status or buyer review status.
- source of truth for buyer territories and routing eligibility.
- only copy of call transcripts or lead evidence.

### system-of-record map

- Postgres: primary system of record for buyers, leads, wallets, billing events, buyer reviews, campaigns, and KPIs.
- object storage: evidence store for photos, mailer exports, call artifacts, transcripts, and audit snapshots.
- Hatchet: workflow scheduler and retry layer, not the permanent business record.
- Caddy: edge routing, TLS, WAF, and public/private boundary.
- ping-post: lead auction, wallet affordability check, delivery, debit, and post-result write path.
- form-receiver: homeowner capture and intake audit write path.
- storm-watcher: storm event ingestion and campaign trigger candidate source.
- agent-runtime: qualification, summaries, and operator-assist logic.

### production-readiness gaps

The current code and docs are not yet a deployable revenue system until these gaps are closed:

- prod compose and deploy script still need to be built.
- Caddy references `landing`, `buyer-portal`, and `voice-bridge`, but those services are not implemented or included in compose.
- buyer CRM fields and territory/service matching are not yet implemented.
- lead classification fields for class a/b/c/d are not yet implemented.
- campaign/source attribution fields are not yet implemented.
- buyer review workflow is documented but still maturing.
- AI voice is documented but `voice-bridge` is not implemented.
- call tracking ingestion is not implemented.
- mailer CSV export and campaign records are not implemented.
- admin KPI and buyer report endpoints are not implemented.
- low-wallet alerts and refill workflows are not implemented.

### design risks to keep explicit

- **monolithic docs risk**: this README contains strategy, product requirements, and rollout planning. Keep it as the single source until first launch, then split into dedicated docs when the sections stabilize.
- **cash-flow risk**: ordinary buyer adjustments should preserve campaign working capital where possible.
- **buyer-trust risk**: review rules must be enforced consistently or contractors will stop refilling.
- **campaign-spend risk**: paid homeowner acquisition must be blocked when funded buyer coverage is missing.
- **ops-surface risk**: fully self-hosted telephony should be deferred; use a carrier vendor until lead economics are proven.

### implementation readiness gate

The framework is ready for first launch only when all of these are true:

- at least three funded buyers exist in one target market.
- active buyers have territories, services, caps, wallet balances, and accepted prices.
- lead capture records campaign source, address, and phone.
- only class a and class b leads can route automatically.
- ping-post checks wallet, territory, service, status, and caps before delivery.
- admin can see wallet-backed revenue, active buyers, sold leads, buyer adjustments, and campaign margin.
- Caddy routes only implemented public services.
- prod compose runs the implemented service set with no public database/admin ports.

## 40 percent irr operating model

Purpose: run StormLead as a capital-efficient, prepaid lead marketplace. The goal is not raw lead volume; the goal is to recycle contractor wallet cash into qualified opportunities with strict contribution-margin and payback controls.

### business thesis

Contractors prepay for storm/tree opportunities. StormLead uses prepaid wallet cash to fund demand generation, routes exclusive opportunities, debits wallets on delivery, adjusts the ledger after operator review, and drives refills through proof reports.

The operating loop is:

1. storm event creates local homeowner demand.
2. contractor wallets are sold before major campaign spend.
3. funded buyer territories define where campaigns can run.
4. Google ads, mailers, landing pages, and field activity generate calls/forms.
5. leads are qualified against explicit routing rules.
6. eligible leads route to funded buyers.
7. delivered leads debit buyer wallets.
8. operator-reviewed outcomes update the ledger.
9. daily reports prove value and trigger wallet refills.

### contractor offer ladder

Use prepaid wallets before selling high-priced single leads.

- starter wallet: $500 to $1,000 prepaid.
- exclusive lead: $100 to $250.
- qualified inbound call: $150 to $400.
- booked inspection: $300 to $750.
- booked emergency opportunity: $750 to $1,500.
- signed-job referral: deferred until supported by operations.

Default V1 offer:

- $1,000 prepaid wallet.
- $150 to $250 per exclusive lead.
- buyer adjustments handled by rule.
- zip priority while the wallet is funded.
- daily cap controlled by buyer.
- daily report sent automatically.

### irr driver tree

The business should optimize for these financial drivers:

- prepaid wallet cash collected.
- available buyer wallet balance.
- campaign spend committed.
- cost per inbound call.
- cost per qualified lead.
- average sold lead price.
- gross margin per sold lead.
- buyer adjustment rate.
- buyer refill rate.
- campaign payback period.
- cash conversion cycle.

To support a 40% irr target, V1 operating targets are:

- fixed infra and tool cost under $500 to $1,000 per month.
- campaign payback under 30 days.
- gross margin on sold leads above 40%.
- buyer refill rate above 50%.
- buyer adjustment rate under 15% to 20%.
- contractor wallet cash collected before at least 70% of paid campaign spend.
- no paid campaign in a zip without funded buyer coverage.

### campaign unit economics

Baseline campaign model for a 50-call storm push:

1. 50 inbound calls.
2. 35 qualified calls at a 70% qualified rate.
3. 25 sold opportunities at a 70% saleable rate.
4. $200 average sold lead price.
5. $5,000 gross lead revenue.

Target spend guardrail:

- cost per call under $40 to $60.
- cost per qualified lead under $85 to $125.
- total campaign spend under $2,000 to $3,000 for this baseline.

Premium mix model:

1. 20 regular qualified leads at $150 = $3,000.
2. 5 booked emergency opportunities at $750 = $3,750.
3. total gross revenue = $6,750.

This mix is preferred because booked emergency opportunities improve margin, contractor trust, and refill probability.

### deployment structure

Keep production fixed cost low and deploy in a US region close to contractors.

Minimum production stack:

- Hetzner Cloud in Ashburn or Hillsboro.
- Docker Compose under systemd.
- Caddy with TLS and WAF rules.
- Postgres with PostGIS/Timescale/pgvector.
- Hatchet workers for durable workflows.
- form-receiver for homeowner lead capture.
- storm-watcher for NWS/FEMA storm detection.
- ping-post for buyer routing, wallet debit, and billing events.
- agent-runtime for qualification and reporting automation.
- object storage for photos, evidence, exports, and audit artifacts.
- call tracking vendor for inbound calls.
- mailer vendor or local mail house for direct mail.
- manual Stripe/ACH/Zelle deposit entry first; automated Stripe webhooks later.

Avoid V1 complexity:

- Kubernetes.
- full buyer portal before refill behavior is proven.
- automated ad buying without guardrails.
- custom payment processor logic.
- complex ML scoring before deterministic rules work.
- multi-region deployment.

### domain structure

Recommended domains:

- `stormlead.com` for the contractor-facing brand.
- `go.stormlead.com` for homeowner landing pages.
- `api.stormlead.com` for form, call, and vendor webhooks.
- `track.stormlead.com` for QR and source redirects.
- `buyers.stormlead.com` for the later buyer portal.
- `admin.stormlead.com` for internal admin behind VPN or strict access controls.

### marketing structure

There are two funnels.

Contractor acquisition funnel:

- target local tree, storm cleanup, roofing, and restoration contractors.
- sell prepaid wallets before major campaign spend.
- protect zip priority while wallets are funded.
- report daily value and trigger refills.

Homeowner demand funnel:

- storm-triggered Google search ads.
- city and zip landing pages.
- direct mail with QR and call tracking.
- door hangers and boots-on-ground partners.
- Meta/local ads where allowed by the launch plan.

### spend guardrails

The system should not spend blindly. Enforce these rules before launching or continuing paid campaigns:

- no funded buyer coverage means no paid campaign.
- buyer wallet must cover the expected minimum lead volume.
- campaign daily budget must be capped.
- cost per qualified lead must stay below target.
- buyer adjustment rate must stay below threshold.
- buyer response time must stay below threshold.
- pause campaign when no buyer can afford the next lead.
- pause buyer when adjustment rate exceeds 25% or response time exceeds 10 minutes.
- pause zip when campaign spend exceeds wallet-backed revenue potential.

### set-and-forget automation path

Phase 1: manual-controlled MVP.

- buyer CRM.
- prepaid wallet ledger.
- territory rules.
- lead routing.
- buyer adjustments.
- admin KPIs.
- manual campaign launch.
- manual mailer CSV.
- daily buyer report.

Phase 2: assisted automation.

- storm-to-zip scoring.
- funded buyer coverage checks.
- campaign recommendations.
- low-wallet alerts.
- refill messages.
- campaign ROI tracking.
- daily report automation.

Phase 3: guardrailed autopilot.

- auto-launch campaigns only when buyer coverage and budget rules pass.
- auto-pause losing campaigns.
- auto-generate mailer batches under spend caps.
- auto-prioritize buyers by wallet, response speed, and buyer adjustment rate.
- auto-send refill links and pause territories when wallets are empty.

### required product modules

Build in this order:

1. buyer CRM stages, notes, follow-ups, services, and territories.
2. buyer wallet/refill tracking and low-balance alerts.
3. territory zip and service matching in routing.
4. admin KPI endpoint for prepaid cash, active buyers, buyer adjustments, and lead revenue.
5. campaign tracking fields for source, medium, campaign id, zip, storm id, cost, QR, and call number.
6. daily buyer report endpoint.
7. storm campaign recommendation endpoint.
8. mailer CSV export.
9. payment/refill link integration.
10. buyer portal only after buyers refill consistently.

### go/no-go launch checklist

Before launching paid homeowner campaigns:

- at least three funded buyers in the target metro.
- at least $1,500 to $5,000 total wallet cash collected.
- buyer service zips and lead prices recorded.
- landing page and source capture tested.
- call tracking number active.
- buyer delivery webhook or manual delivery channel tested.
- buyer review process tested.
- daily report format ready.
- campaign budget cap set.
- stop-loss rules defined.

### failure thresholds

Pause and review when any of these are true:

- cost per qualified lead exceeds target for 24 hours.
- buyer adjustment rate exceeds 25%.
- buyer response time exceeds 10 minutes.
- more than 20% of calls are spam or wrong service.
- no buyer has enough wallet for the next lead.
- campaign spend exceeds 60% of available wallet-backed revenue without enough sold leads.
- fewer than two buyers are active in the target market.

### weekly operator review

Review these every week:

- total prepaid cash collected.
- new buyer wallets sold.
- buyer refill rate.
- active buyer count.
- low-balance buyers.
- calls by source.
- qualified leads by source.
- sold leads by buyer.
- gross margin by campaign.
- buyer adjustment rate by buyer and source.
- next storm markets to activate.

### deployment checklist

Production should be boring, cheap, and recoverable. Deploy the first revenue system as a single US-region Docker Compose host before considering multi-host or Kubernetes.

Required infrastructure:

- Hetzner Cloud server in Ashburn or Hillsboro.
- Ubuntu LTS with unattended security updates.
- Docker and Docker Compose plugin.
- systemd unit for the production compose stack.
- Caddy public edge with LetsEncrypt.
- firewall allowing only SSH, HTTP, and HTTPS publicly.
- Postgres data volume with daily encrypted backups.
- object storage bucket for lead photos, mailer exports, and audit snapshots.
- `.env.prod` encrypted with SOPS or equivalent.
- no public Postgres, RabbitMQ, Hatchet, Langfuse, or admin ports.

Production environment groups:

- database: `DATABASE_URL`, `DATABASE_URL_RO`, Postgres credentials, backup credentials.
- workflows: Hatchet token, host, TLS strategy.
- forms: form webhook secret and landing page domain.
- calls: call tracking provider credentials and webhook secret.
- mailers: mail vendor API key, sender identity, and exclude-list path.
- billing: Stripe or manual deposit reference fields.
- LLM: LiteLLM keys and upstream model keys only if agent qualification is active.
- observability: log level, Langfuse keys, alert webhook.

Deployment acceptance criteria:

- `/healthz` returns ok for public services.
- `/readyz` verifies database connectivity.
- a synthetic form submission creates a lead.
- the lead emits a workflow event.
- ping-post routes a test lead to a test buyer.
- buyer wallet debits only after successful delivery.
- a buyer-reviewed lead updates the buyer wallet when appropriate.
- a database backup can be restored into a clean test database.
- Caddy terminates TLS and blocks direct access to internal admin services.

### contractor sales workflow

The contractor sales process funds the marketplace. Do not launch paid homeowner acquisition until funded buyer coverage exists.

Daily contractor acquisition workflow:

1. select one storm market and one service category.
2. build a prospect list of local tree/storm contractors.
3. call owners or operations managers first; email only as follow-up.
4. qualify service area, crew capacity, response speed, and storm availability.
5. offer a prepaid wallet with protected zip priority.
6. record buyer stage, target zips, lead price, daily cap, and follow-up date.
7. collect payment before activating campaigns.
8. activate buyer only after wallet, delivery channel, and lead-routing rules are confirmed.

Objection handling:

- if they do not prepay: offer a smaller $500 wallet, not post-pay.
- if they say leads are cheaper elsewhere: compare cost per booked job, not cost per lead.
- if they worry about quality: point to the daily report and review process.
- if they want exclusivity: require wallet funding and a minimum refill cadence.
- if they cannot answer quickly: keep them as overflow, not primary buyer.

### buyer onboarding checklist

Do not mark a buyer active until these are complete:

- company name and primary contact recorded.
- phone and email verified.
- service zips/counties recorded.
- service categories recorded.
- lead price accepted.
- daily cap accepted.
- wallet deposit recorded.
- delivery channel tested.
- response expectation accepted.
- low-balance refill rule accepted.

Buyer activation rule:

- `prospect`, `contacted`, `interested`, and `qualified` buyers cannot receive paid leads.
- `wallet_sold` buyers can receive test delivery only.
- `active` buyers can receive paid leads.
- `low_balance` buyers can receive leads only while wallet covers the next debit.
- `paused`, `suspended`, or `churned` buyers cannot receive leads.

### homeowner acquisition workflow

Homeowner acquisition should run only where buyer wallets already exist.

Storm campaign launch flow:

1. storm-watcher detects or imports an event.
2. operator selects target zips.
3. system checks funded buyer coverage by zip and service.
4. system estimates available wallet-backed revenue.
5. operator sets campaign budget below stop-loss threshold.
6. landing page and call tracking are assigned.
7. Google ads and/or mailer campaign launches.
8. leads are tagged with campaign source, medium, zip, storm id, and tracking code.
9. qualified leads route to funded buyers.
10. campaign pauses automatically or manually when guardrails fail.

### lead qualification workflow

Every lead should be classified before sale.

Lead classes:

- class a: verified emergency booked opportunity.
- class b: qualified exclusive lead.
- class c: needs manual verification.
- class d: invalid or do not sell.

Class a requirements:

- decision-maker confirmed.
- phone reachable.
- address verified.
- buyer service area matched.
- urgency confirmed.
- appointment or callback window booked.
- high-value damage signal present.

Class b requirements:

- decision-maker likely or confirmed.
- phone present and normalized.
- address and zip present.
- service request matches buyer category.
- duplicate check passed.

Class c examples:

- unclear authority.
- vague damage description.
- missing address detail.
- low confidence service match.
- possible duplicate.

Class d examples:

- wrong service.
- invalid phone.
- spam.
- outside all active buyer territories.
- already completed.

Only class a and class b should auto-route. Class c requires manual review. Class d should not be sold.

### buyer reporting templates

Daily buyer report:

```text
StormLead daily report for [buyer]

Wallet balance: $[balance]
Leads delivered today: [count]
Accepted leads: [count]
Reviewed adjustments: [count]
Average lead price: $[amount]
Remaining estimated lead capacity: [count]

Recommended refill: $[amount]
Reason: [active storm / low balance / strong campaign performance]
```

Lead delivery receipt:

```text
New exclusive storm/tree lead

Lead type: [qualified lead / booked emergency opportunity]
Price: $[amount]
ZIP: [zip]
Damage: [summary]
Urgency: [same day / next day / flexible]
Contact: [name, phone]
Address: [address]
```

Low-wallet refill message:

```text
Your StormLead wallet has $[balance] remaining, enough for about [count] more leads. Severe weather activity is active in your ZIPs. Refill $[amount] to keep ZIP priority active and avoid lead routing pauses.
```

### kpi definitions

Use consistent definitions so reports do not drift.

- inbound call: a call received on a campaign tracking number.
- qualified call: an inbound call that matches service, geography, and homeowner-intent rules.
- captured lead: a stored homeowner record with source metadata.
- sold lead: a delivered lead that successfully debited a buyer wallet.
- reviewed lead: a sold lead reviewed after buyer feedback.
- available wallet balance: sum of active buyer balances available for future debits.
- wallet-backed revenue potential: available buyer wallet balance in a target campaign territory.
- cost per call: campaign spend divided by inbound calls.
- cost per qualified lead: campaign spend divided by qualified leads.
- gross lead revenue: sum of successful lead debits before buyer adjustments.
- net lead revenue: gross lead revenue minus buyer adjustments.
- contribution margin: net lead revenue minus campaign spend and variable vendor costs.
- refill rate: buyers who add wallet funds again after initial purchase divided by buyers who bought a first wallet.
- buyer adjustment rate: reviewed leads with wallet impact divided by sold leads.

### first 30-day rollout

Week 1: market and buyer setup.

- select one metro and one service category.
- build contractor prospect list.
- sell three to five prepaid wallets.
- define target zips and lead prices.
- test buyer delivery and review flow.

Week 2: campaign setup.

- publish or configure landing pages.
- activate call tracking numbers.
- create Google ads campaign drafts.
- prepare first mailer CSV.
- verify source tracking on form and call leads.

Week 3: controlled launch.

- launch paid traffic only in funded territories.
- run limited mailer batch.
- manually review class c leads.
- send daily buyer reports.
- process buyer reviews within one business day.

Week 4: refill and scale decision.

- calculate cost per qualified lead.
- calculate buyer adjustment rate by buyer and source.
- ask low-balance buyers to refill.
- pause weak zips and weak buyers.
- scale only campaigns with positive contribution margin and funded wallet coverage.

30-day success criteria:

- at least $1,500 to $5,000 prepaid wallet cash collected.
- at least 50 inbound calls or a clear path to that volume.
- at least 35 qualified calls if 50 calls are reached.
- buyer adjustment rate under 20%.
- at least two buyers refill or commit to refill.
- contribution margin positive on at least one source/zip combination.

### implementation acceptance criteria

The business system is ready for first launch when these are true:

- buyers can be created and assigned service areas.
- wallet deposits can be recorded.
- lead delivery debits wallets.
- buyer-reviewed adjustments update wallets.
- buyer summary reports can be produced.
- admin can see active buyers, wallet balances, sold leads, buyer adjustments, and revenue.
- leads carry campaign/source attribution.
- campaign spend can be compared to lead revenue.
- mailer recipients can be exported or submitted to a vendor.
- no paid campaign can run without funded buyer coverage.

### next engineering sequence

Build the next code changes in this order:

1. buyer CRM fields: sales stage, notes, next follow-up, services, target zips, low-balance threshold.
2. buyer update/list/summary endpoints.
3. territory and service matching inside ping-post buyer eligibility.
4. daily and monthly cap enforcement.
5. admin KPI endpoint.
6. campaign/source fields on leads.
7. buyer daily report endpoint.
8. mailer CSV export endpoint.
9. low-wallet alert/refill recommendation logic.
10. payment webhook integration after manual deposits prove refill behavior.
