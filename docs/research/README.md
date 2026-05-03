# research

claude research artifacts that informed the scaffold's choices. the two `2026-05-*-audit.md` / `*-forkable-*.md` docs are preserved verbatim — what was true at audit time. `2026-05-stack-improvements.md` layers on verification + architectural critique and supersedes the older docs where they conflict.

## docs

- **`2026-05-stack-audit.md`** — *what tech to use and why we pinned what we pinned.* security/integration audit across ~28 candidate repos. drives: litellm sha-pin (post mar-2026 supply-chain incident), postgres-mcp-pro over the archived anthropic reference, hatchet for durable execution, coraza+caddy for the waf, langfuse v3 stack.

- **`2026-05-forkable-stack.md`** — *what to fork per layer and the agpl/license traps.* opinionated repo recommendations: tropycal/nws/fema for storm ingestion, formbricks for forms, twenty for crm, jambonz for telephony, pseo-next for landing, suna for the agent runtime, florence-2/detectron2 for vision (avoid ultralytics — agpl). flags agpl exposure on twenty + formbricks + ultralytics.

- **`2026-05-stack-improvements.md`** — *what changed since those docs were written, and what they don't address.* verification of time-sensitive claims (litellm cve, hatchet v1 rewrite, fcc one-to-one rule death) and a register of business-mechanics gaps neither prior doc covers (lead dedup, fraud scoring, buyer disputes, dnc scrub, billing). includes a sequenced action list.

- **`2026-05-architectural-fit.md`** — *is the chosen architecture the best fit for this business?* open research comparing 9 alternatives + an empirical hunt for what production lead-marketplace operators actually run. verdict: bones right, dressing over-engineered for v1. records the tier-1 cuts (drop nats, seaweedfs, openbao) and the hetzner-us-region decision, plus tier-2 spikes (dbos transact vs hatchet v1) deferred until agent-runtime work begins.

- **`2026-05-agent-auth-patterns.md`** — *can agents use `CLAUDE_CODE_OAUTH_TOKEN` instead of an api key?* counterexample-driven correction of an earlier "officially no" answer. coleam00's linear-coding-agent-harness is the canonical reference. verdict: oauth is viable for single-operator low-volume opus work (hermes self-evolution, complex qualification); api+litellm stays for high-volume / latency-sensitive paths. hybrid is the recommended shape when agent-runtime is built.

## superseded claims (read `stack-improvements.md` and `architectural-fit.md` for current truth)

- **litellm pin v1.83.4-stable** → **v1.83.7-stable** (cve-2026-42208).
- **hatchet v0.50.0 healthy** → legacy branch; v1 rewrite shipped mar 2025.
- **fcc one-to-one consent rule = primary tcpa threat** → rule is dead (vacated jan 2025, fcc abandoned aug/sep 2025); pre-2023 pewc standard restored.
- **`crystaldba/postgres-mcp:latest` ok** → pin a specific tag.
- **tropycal actively maintained** → snyk classifies "inactive" since early 2025.
- **nats event bus alongside hatchet** → cut for v1; hatchet handles durable workflows on postgres; cross-service events use hatchet triggers or postgres listen/notify.
- **seaweedfs as self-hosted s3** → cut for v1; use hetzner object storage (~$5/mo, s3-compat). seaweedfs/minio re-enter when there's a concrete reason.
- **openbao for secrets in v1** → deferred until 2nd operator. `.env` + sops-encrypted `.env.prod` is enough until then.
- **hetzner falkenstein/helsinki ok for the auction endpoint** → deploy to ashburn (us-east) or hillsboro (us-west). eu→us rtt eats the auction budget.
- **agents need an api key; oauth not allowed** → over-conservative reading of the policy. for single-operator personal automation, `CLAUDE_CODE_OAUTH_TOKEN` (via `claude setup-token` + claude code cli) is viable. the prohibition is on offering claude.ai login *to end users*. see `agent-auth-patterns.md` for the hybrid recommendation.

## scaffold divergences from `forkable-stack.md` (deliberate)

- **no suna fork.** agent-runtime is direct on claude agent sdk + litellm (~200 loc target), no supabase. see top-level README.
- **ping-post is python (fastapi + hatchet), not rust/go.** rewrite the hot path later if/when we cross ~500 leads/sec sustained.
- **no coolify.** prod runs docker compose under systemd on hetzner.

## latent risks called out in `forkable-stack.md` (still active)

- **twenty crm = agpl-3.0.** if buyers ever hit a modified twenty ui, source-disclosure triggers. mitigate: keep buyers on api/webhooks, or buy commercial license.
- **formbricks v3+ moved sso/oidc to paid ee.** fine solo; flag if a team forms.
- **hetzner blocks port 25 outbound by default.** matters when email send lands.
- **ultralytics yolov8/v11 = agpl-3.0.** if vision is added, use florence-2 / detectron2 / llava — not ultralytics.

## defensive breach-intel workflow

Purpose: maintain a defensive-only exposure monitoring workflow for company-owned or explicitly authorized domains, customers, vendors, and infrastructure. this workflow must not be used for lead generation, contact enrichment, ad targeting, profiling, or marketing outreach.

### scope

- monitor only owned company assets or client/customer assets with written authorization.
- track exposed company domains, employee emails, app names, api key patterns, github orgs, cloud assets, and vendor references.
- do not download, redistribute, or process leaked third-party personal data beyond what is strictly necessary to confirm and report exposure.

### safe sources

- have i been pwned domain search.
- github, gitlab, and bitbucket public code search.
- public cloud bucket exposure checks.
- shodan/censys for owned or authorized infrastructure.
- state attorney general breach notification portals.
- sec cyber incident disclosures.
- vendor security advisories and trust pages.
- `security.txt` contacts at `/.well-known/security.txt`.

### workflow

1. define the authorized search scope.
2. search for indicators, not full leaked datasets.
3. record source url, timestamp, affected domain/system, and redacted evidence.
4. avoid downloading full dumps or opening unrelated personal records.
5. classify severity: p1 exposed active secret, credential, database, or live system; p2 customer pii exposure; p3 employee credential exposure; p4 historical or stale exposure mention.
6. notify the owner through `security@domain.com`, `security.txt`, vendor portal, or cloud provider abuse channel.
7. if stormlead customers are affected, involve counsel/compliance before notification.
8. store only sanitized findings unless legal/security review approves retaining raw evidence.
9. rotate secrets, force password resets, and review access logs where applicable.
10. document remediation and retention/deletion decisions.

### guardrails

- no use of leaked data for sales, marketing, lead generation, phone/email append, or ad audiences.
- no credential testing or login attempts.
- no downloading full breach dumps unless counsel approves and there is a specific defensive need.
- no sharing raw pii through slack, email, cloud drives, or ai tools.
- keep an audit trail of who accessed datasets and why.

## automated storm mailers

Purpose: turn a storm event into a compliant direct-mail campaign that drives homeowners to a tracked call number or qr landing page. direct mail is the safer outbound channel for cold homeowner targeting; phone, sms, and email follow-up should come after opt-in or another legally valid basis.

### trigger

1. storm-watcher detects a qualifying hail, hurricane, wind, or tree-damage event.
2. affected zips/counties are scored by severity, property density, and expected service demand.
3. campaign owner approves target geography and budget before any mail is sent.

### data inputs

- noaa/nws/spc storm event data for date, coordinates, wind/hail severity, and affected area.
- county assessor or gis parcel exports for property address, mailing address, owner name where public, property type, year built, and owner-occupied signal.
- permit data where available to suppress properties with recent roof/tree/storm repair work.
- crm suppression lists for do-not-mail, prior disputes, customers already contacted, and buyers' excluded territories.

### targeting rules

- include residential properties inside the storm impact polygon or selected zips.
- prioritize owner-occupied single-family homes, older homes, high tree canopy areas, and higher storm severity bands.
- exclude renters where the owner mailing address is known and different from the property address unless the campaign is owner-mail only.
- exclude duplicates by normalized mailing address and parcel id.
- exclude any address on suppression lists.

### mailer workflow

1. create a campaign record with storm id, target zips, budget, vendor, creative version, and approval status.
2. generate a recipient batch from parcel/assessor data.
3. assign each recipient a unique tracking code.
4. render the mailer with city, storm date, service type, qr code, call tracking number, and compliance footer.
5. send the batch to a print/mail vendor such as lob, postgrid, click2mail, postalytics, or a local mail house.
6. store vendor job id, recipient count, estimated delivery date, and per-piece status when available.
7. route qr visits, form fills, and calls back to campaign/source tracking in the lead table.

### creative requirements

- do say: "your area was affected by severe weather on [date]" when supported by storm data.
- do say: "schedule a free storm/tree damage assessment" if the buyer can service it.
- do not claim a specific house is damaged unless there was a permissioned inspection.
- do not imply government, insurance-carrier, or emergency-service affiliation.
- include business identity, contact info, opt-out or mail suppression instructions, and service-area disclaimers.

### kpis

- mail pieces sent.
- delivered or accepted-by-vendor count.
- qr scans.
- inbound calls.
- form fills.
- cost per call.
- cost per qualified call.
- booked inspections.
- sold jobs or sold leads.
- return/dispute rate from buyers.

### v1 implementation hook

- add a campaign table only when the first vendor integration is built; until then, campaign id can be stored in lead source metadata or page url parameters.
- use one unique qr url per campaign and zip first; move to per-recipient tracking after baseline response rate is proven.
- start with vendor csv upload/manual approval before automating api sends.
- after one successful manual batch, automate vendor api submission from the storm-watcher event flow.

## 40 percent irr operating model

Purpose: run stormlead as a capital-efficient, prepaid lead marketplace. the goal is not raw lead volume; the goal is to recycle contractor wallet cash into qualified guaranteed leads with strict contribution-margin and payback controls.

### business thesis

Contractors prepay for guaranteed qualified storm/tree leads. stormlead uses prepaid wallet cash to fund demand generation, routes only valid exclusive opportunities, debits wallets on delivery, credits invalid leads, and drives refills through proof reports.

The operating loop is:

1. storm event creates local homeowner demand.
2. contractor wallets are sold before major campaign spend.
3. funded buyer territories define where campaigns can run.
4. google ads, mailers, landing pages, and field activity generate calls/forms.
5. leads are qualified against explicit valid-lead rules.
6. eligible leads route to funded buyers.
7. delivered leads debit buyer wallets.
8. invalid leads are credited through defined return reasons.
9. daily reports prove value and trigger wallet refills.

### qualified guaranteed lead definition

A lead is valid only when it meets all of these criteria:

- homeowner or decision-maker.
- valid reachable phone number.
- inside the buyer's service area.
- requested tree removal, hurricane cleanup, storm cleanup, or another buyer-approved service.
- not a duplicate within the agreed lookback window.
- not spam or a solicitor.
- not already completed before delivery.
- consent record exists for contact and routing.
- exclusive to the buyer unless a different sales agreement says otherwise.

Premium booked opportunities should also include:

- damage tier confirmed.
- urgency confirmed.
- photos collected when possible.
- callback or inspection window booked.
- high-value signal such as tree on structure, driveway blocked, vehicle damage, crane likelihood, or active storm emergency.

Credited return reasons are limited to:

- wrong number.
- duplicate.
- outside service area.
- renter or no decision authority.
- spam.
- job already completed.

### contractor offer ladder

Use prepaid wallets before selling high-priced single leads.

- starter wallet: $500 to $1,000 prepaid.
- valid exclusive lead: $100 to $250.
- qualified inbound call: $150 to $400.
- booked inspection: $300 to $750.
- booked emergency opportunity: $750 to $1,500.
- signed-job referral: 5% to 15% rev share only when legally and operationally supported.

Default v1 offer:

- $1,000 prepaid wallet.
- $150 to $250 per valid exclusive lead.
- invalid leads credited by rule.
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
- return and credit rate.
- buyer refill rate.
- campaign payback period.
- cash conversion cycle.

To support a 40% irr target, v1 operating targets are:

- fixed infra and tool cost under $500 to $1,000 per month.
- campaign payback under 30 days.
- gross margin on sold leads above 40%.
- buyer refill rate above 50%.
- lead return rate under 15% to 20%.
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

Keep production fixed cost low and deploy in a us region close to contractors.

Minimum production stack:

- hetzner cloud in ashburn or hillsboro.
- docker compose under systemd.
- caddy with tls and waf rules.
- postgres with postgis/timescale/pgvector.
- hatchet workers for durable workflows.
- form-receiver for consented homeowner lead capture.
- storm-watcher for nws/fema storm detection.
- ping-post for buyer routing, wallet debit, and billing events.
- agent-runtime for qualification and reporting automation.
- object storage for photos, evidence, exports, and audit artifacts.
- call tracking vendor for inbound calls.
- mailer vendor or local mail house for direct mail.
- manual stripe/ach/zelle deposit recording first; automated stripe webhooks later.

Avoid v1 complexity:

- kubernetes.
- full buyer portal before refill behavior is proven.
- automated ad buying without guardrails.
- custom payment processor logic.
- complex ml scoring before deterministic rules work.
- multi-region deployment.

### domain structure

Recommended domains:

- `stormlead.com` for the contractor-facing brand.
- `go.stormlead.com` for homeowner landing pages.
- `api.stormlead.com` for form, call, and vendor webhooks.
- `track.stormlead.com` for qr and source redirects.
- `buyers.stormlead.com` for the later buyer portal.
- `admin.stormlead.com` for internal admin behind vpn or strict access controls.

### marketing structure

There are two funnels.

Contractor acquisition funnel:

- target local tree, storm cleanup, roofing, and restoration contractors.
- sell prepaid wallets before major campaign spend.
- protect zip priority while wallets are funded.
- report daily value and trigger refills.

Homeowner demand funnel:

- storm-triggered google search ads.
- city and zip landing pages.
- direct mail with qr and call tracking.
- door hangers and boots-on-ground partners.
- meta/local ads where compliant.
- retargeting only where cookie/consent policy supports it.

### spend guardrails

The system should not spend blindly. enforce these rules before launching or continuing paid campaigns:

- no funded buyer coverage means no paid campaign.
- buyer wallet must cover the expected minimum lead volume.
- campaign daily budget must be capped.
- cost per qualified lead must stay below target.
- return rate must stay below threshold.
- buyer response time must stay below threshold.
- pause campaign when no buyer can afford the next lead.
- pause buyer when return rate exceeds 25% or response time exceeds 10 minutes.
- pause zip when campaign spend exceeds wallet-backed revenue potential.

### set-and-forget automation path

Phase 1: manual-controlled mvp.

- buyer crm.
- prepaid wallet ledger.
- territory rules.
- lead routing.
- return credits.
- admin kpis.
- manual campaign launch.
- manual mailer csv.
- daily buyer report.

Phase 2: assisted automation.

- storm-to-zip scoring.
- funded buyer coverage checks.
- campaign recommendations.
- low-wallet alerts.
- refill messages.
- campaign roi tracking.
- daily report automation.

Phase 3: guardrailed autopilot.

- auto-launch campaigns only when buyer coverage and budget rules pass.
- auto-pause losing campaigns.
- auto-generate mailer batches under spend caps.
- auto-prioritize buyers by wallet, response speed, and return rate.
- auto-send refill links and pause territories when wallets are empty.

### required product modules

Build in this order:

1. buyer crm stages, notes, follow-ups, services, and territories.
2. buyer wallet/refill tracking and low-balance alerts.
3. territory zip and service matching in routing.
4. admin kpi endpoint for prepaid cash, active buyers, returns, and lead revenue.
5. campaign tracking fields for source, medium, campaign id, zip, storm id, cost, qr, and call number.
6. daily buyer report endpoint.
7. storm campaign recommendation endpoint.
8. mailer csv export.
9. payment/refill link integration.
10. buyer portal only after buyers refill consistently.

### go/no-go launch checklist

Before launching paid homeowner campaigns:

- at least three funded buyers in the target metro.
- at least $1,500 to $5,000 total wallet cash collected.
- buyer service zips and lead prices recorded.
- valid lead and credit rules accepted by buyers.
- landing page and consent capture tested.
- call tracking number active.
- buyer delivery webhook or manual delivery channel tested.
- return process tested.
- daily report format ready.
- campaign budget cap set.
- stop-loss rules defined.

### failure thresholds

Pause and review when any of these are true:

- cost per qualified lead exceeds target for 24 hours.
- return rate exceeds 25%.
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
- return rate by buyer and source.
- next storm markets to activate.

### deployment checklist

Production should be boring, cheap, and recoverable. deploy the first revenue system as a single us-region docker compose host before considering multi-host or kubernetes.

Required infrastructure:

- hetzner cloud server in ashburn or hillsboro.
- ubuntu lts with unattended security updates.
- docker and docker compose plugin.
- systemd unit for the production compose stack.
- caddy public edge with letsencrypt.
- firewall allowing only ssh, http, and https publicly.
- postgres data volume with daily encrypted backups.
- object storage bucket for lead photos, consent evidence exports, mailer exports, and audit snapshots.
- `.env.prod` encrypted with sops or equivalent.
- no public postgres, rabbitmq, hatchet, langfuse, or admin ports.

Production environment groups:

- database: `DATABASE_URL`, `DATABASE_URL_RO`, postgres credentials, backup credentials.
- workflows: hatchet token, host, tls strategy.
- forms: form webhook secret and landing page domain.
- calls: call tracking provider credentials and webhook secret.
- mailers: mail vendor api key, sender identity, suppression-list path.
- billing: stripe or manual deposit reference fields.
- llm: litellm keys and upstream model keys only if agent qualification is active.
- observability: log level, langfuse keys, alert webhook.

Deployment acceptance criteria:

- `/healthz` returns ok for public services.
- `/readyz` verifies database connectivity.
- a synthetic form submission creates a lead.
- the lead emits a workflow event.
- ping-post routes a test lead to a test buyer.
- buyer wallet debits only after successful delivery.
- a returned lead credits the buyer wallet.
- a database backup can be restored into a clean test database.
- caddy terminates tls and blocks direct access to internal admin services.

### contractor sales workflow

The contractor sales process funds the marketplace. do not launch paid homeowner acquisition until funded buyer coverage exists.

Daily contractor acquisition workflow:

1. select one storm market and one service category.
2. build a prospect list of local tree/storm contractors.
3. call owners or operations managers first; email only as follow-up.
4. qualify service area, crew capacity, license/insurance, response speed, and storm availability.
5. offer a prepaid wallet with protected zip priority.
6. record buyer stage, target zips, lead price, daily cap, and follow-up date.
7. collect payment before activating campaigns.
8. activate buyer only after wallet, delivery channel, and valid-lead rules are confirmed.

Contractor pitch:

```text
We generate exclusive storm/tree removal opportunities from homeowners in your service area. You do not pay for clicks or ads. You only pay for valid leads that match your ZIPs and service rules.

The starter wallet is $1,000. Each valid exclusive lead is deducted from that balance at the agreed rate. If it is a wrong number, duplicate, outside your area, spam, or already completed, I credit it back.

I only protect ZIP priority for funded buyers. What ZIPs do you want covered first?
```

Objection handling:

- if they do not prepay: offer a smaller $500 wallet, not post-pay.
- if they say leads are cheaper elsewhere: compare cost per booked job, not cost per lead.
- if they worry about quality: point to the credit rules and daily report.
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
- valid-lead definition accepted.
- return reasons accepted.
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
7. google ads and/or mailer campaign launches.
8. leads are tagged with campaign source, medium, zip, storm id, and tracking code.
9. qualified leads route to funded buyers.
10. campaign pauses automatically or manually when guardrails fail.

Homeowner landing-page requirements:

- storm/date/area claim must be supported by source data.
- service offer must be specific: tree removal, hurricane cleanup, storm cleanup, or inspection.
- phone number must be trackable by campaign.
- form must collect consent before contact/routing.
- form must collect address and zip.
- form should collect damage type, urgency, and photos when possible.
- page must avoid insurance, government, or guaranteed-coverage claims.

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
- consent captured.
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
- no consent.
- already completed.

Only class a and class b should auto-route. class c requires manual review. class d should not be sold.

### buyer reporting templates

Daily buyer report:

```text
StormLead daily report for [buyer]

Wallet balance: $[balance]
Leads delivered today: [count]
Valid leads: [count]
Credited leads: [count]
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
Consent captured: yes
Credit policy: wrong number, duplicate, outside service area, spam, or already completed.
```

Low-wallet refill message:

```text
Your StormLead wallet has $[balance] remaining, enough for about [count] more leads. Severe weather activity is active in your ZIPs. Refill $[amount] to keep ZIP priority active and avoid lead routing pauses.
```

### kpi definitions

Use consistent definitions so reports do not drift.

- inbound call: a call received on a campaign tracking number.
- qualified call: an inbound call that matches service, geography, and homeowner-intent rules.
- captured lead: a stored homeowner record with consent/source metadata.
- sold lead: a delivered lead that successfully debited a buyer wallet.
- returned lead: a sold lead credited back under allowed return reasons.
- available wallet balance: sum of active buyer balances available for future debits.
- wallet-backed revenue potential: available buyer wallet balance in a target campaign territory.
- cost per call: campaign spend divided by inbound calls.
- cost per qualified lead: campaign spend divided by qualified leads.
- gross lead revenue: sum of successful lead debits before returns.
- net lead revenue: gross lead revenue minus credited returns.
- contribution margin: net lead revenue minus campaign spend and variable vendor costs.
- refill rate: buyers who add wallet funds again after initial purchase divided by buyers who bought a first wallet.
- return rate: returned leads divided by sold leads.

### first 30-day rollout

Week 1: market and buyer setup.

- select one metro and one service category.
- build contractor prospect list.
- sell three to five prepaid wallets.
- define target zips and lead prices.
- test buyer delivery and return flow.

Week 2: campaign setup.

- publish or configure landing pages.
- activate call tracking numbers.
- create google ads campaign drafts.
- prepare first mailer csv.
- verify source tracking on form and call leads.

Week 3: controlled launch.

- launch paid traffic only in funded territories.
- run limited mailer batch.
- manually review class c leads.
- send daily buyer reports.
- process returns within one business day.

Week 4: refill and scale decision.

- calculate cost per qualified lead.
- calculate return rate by buyer and source.
- ask low-balance buyers to refill.
- pause weak zips and weak buyers.
- scale only campaigns with positive contribution margin and funded wallet coverage.

30-day success criteria:

- at least $1,500 to $5,000 prepaid wallet cash collected.
- at least 50 inbound calls or a clear path to that volume.
- at least 35 qualified calls if 50 calls are reached.
- return rate under 20%.
- at least two buyers refill or commit to refill.
- contribution margin positive on at least one source/zip combination.

### implementation acceptance criteria

The business system is ready for first paid launch when these are true:

- buyers can be created and assigned service areas.
- wallet deposits can be recorded.
- lead delivery debits wallets.
- invalid leads can be credited.
- buyer summary reports can be produced.
- admin can see active buyers, wallet balances, sold leads, returns, and revenue.
- leads carry campaign/source attribution.
- campaign spend can be compared to lead revenue.
- mailer recipients can be exported or submitted to a vendor.
- no paid campaign can run without funded buyer coverage.

### next engineering sequence

Build the next code changes in this order:

1. buyer crm fields: sales stage, notes, next follow-up, services, target zips, low-balance threshold.
2. buyer update/list/summary endpoints.
3. territory and service matching inside ping-post buyer eligibility.
4. daily and monthly cap enforcement.
5. admin kpi endpoint.
6. campaign/source fields on leads.
7. buyer daily report endpoint.
8. mailer csv export endpoint.
9. low-wallet alert/refill recommendation logic.
10. payment webhook integration after manual deposits prove refill behavior.

## lead quality guarantee, credits, refunds, and ai voice nurture

Purpose: protect contractor trust while preserving working capital. stormlead should operate as a qualified lead matching service: contractors prepay wallets, valid leads debit wallets, invalid leads are credited by rule, and ai voice nurture improves lead quality before routing.

### matching service positioning

StormLead matches homeowners requesting storm/tree services with qualified local contractors. contractor payment is for valid lead delivery or booked opportunity matching, not guaranteed job closure.

Use this positioning:

- qualified lead matching.
- exclusive contractor matching.
- valid opportunity delivery.
- wallet credit for invalid leads.

Avoid these claims:

- guaranteed customer.
- guaranteed job.
- guaranteed contractor revenue.
- guaranteed insurance approval.
- government, utility, or insurance-carrier affiliation.

Contractor terms summary:

```text
StormLead provides qualified lead matching. A valid lead is a homeowner or decision-maker requesting an approved service in the buyer's accepted territory with reachable contact information and captured consent.

Contractors may request credit for invalid leads within the return window. Approved invalid leads are credited back to the buyer wallet. Cash refunds are limited to unused wallet balances, duplicate payments, overpayments, billing errors, or cancellation after all pending lead disputes are resolved.

StormLead does not guarantee that a valid lead will become a paying job.
```

### valid lead guarantee

A valid lead must meet all of these criteria:

- homeowner or decision-maker.
- valid reachable phone number.
- inside buyer-approved service area.
- requested an approved service type.
- not duplicate within the agreed lookback window.
- not spam or a solicitor.
- not already completed before delivery.
- consent record exists for contact and routing.
- exclusive to the buyer unless a different agreement says otherwise.

A valid lead does not guarantee:

- homeowner hires the contractor.
- homeowner answers every call.
- job is profitable.
- insurance approves a claim.
- contractor wins the estimate.
- homeowner does not price-shop.

### wallet credits versus cash refunds

Use wallet credits first and cash refunds second.

Wallet credit applies when a delivered lead is invalid under the allowed return reasons. the credit restores the original lead debit to the buyer wallet.

Cash refund applies only when money should leave stormlead and return to the buyer payment method.

Cash refunds are allowed for:

- unused wallet balance after buyer cancellation and dispute review.
- duplicate deposit.
- accidental overpayment.
- billing error.
- stormlead cannot serve the buyer's approved territory after taking payment.

Cash refunds are not the default remedy for ordinary bad leads. approved invalid leads should become wallet credits.

Cancellation policy:

- buyer can cancel anytime.
- delivered valid leads are non-refundable.
- pending lead disputes must be resolved before final cash refund calculation.
- approved invalid leads are credited before final refund calculation.
- final cash refund equals unused wallet balance minus outstanding valid lead charges and any agreed non-refundable setup fee.

### credit-eligible return reasons

Allowed return reasons:

- `wrong_number`.
- `duplicate`.
- `outside_service_area`.
- `renter_no_authority`.
- `spam`.
- `job_already_completed`.
- `no_consent_record`.
- `system_delivery_error`.

Not credit eligible:

- homeowner chose another contractor after valid delivery.
- contractor called too late.
- contractor missed an inbound transfer, call, or appointment.
- homeowner price-shopped.
- homeowner changed mind.
- job was smaller than expected.
- contractor decided not to service a zip they previously approved.
- contractor already had too many jobs.
- contractor failed to update paused status or daily cap.
- buyer's sales team failed to follow up.

### return windows

Use strict windows to prevent abuse and keep buyer trust high.

- standard lead: 72 hours from delivery.
- booked emergency opportunity: 24 hours from delivery.
- duplicate, no consent record, or system delivery error: 7 days from delivery.
- unused wallet refund: after cancellation and all pending dispute review.

Expired return requests should be denied unless the issue is a system/billing error.

### contractor proof requirements

The contractor must prove the lead is invalid. every return request must include:

- lead id.
- buyer id.
- return reason.
- contractor notes.
- call attempt timestamp.
- call outcome.
- evidence url or call recording id when available.
- explanation tying the evidence to an allowed return reason.

Proof by return reason:

- wrong number: call log, disconnected result, wrong-person note, or recording reference.
- duplicate: prior lead id, phone number, and date received.
- outside service area: lead zip/address and buyer's approved territory list.
- renter or no authority: homeowner statement or contractor note from call.
- spam: fake name/address/phone evidence, call outcome, recording, or notes.
- job already completed: homeowner statement that work was completed before lead delivery.
- no consent record: missing consent audit, missing form consent, or missing permitted contact basis.
- system delivery error: delivery log showing wrong buyer, wrong territory, duplicate post, or webhook failure.

### return review workflow

Return request states:

- `requested`.
- `needs_evidence`.
- `approved`.
- `denied`.
- `expired`.
- `credited`.
- `cash_refunded`.

Review process:

1. contractor submits return request.
2. system validates return window.
3. system validates allowed reason.
4. system checks lead delivery record.
5. system checks consent audit.
6. system checks duplicate history.
7. system checks buyer territory and service rules.
8. reviewer approves, denies, expires, or requests evidence.
9. approved return credits buyer wallet.
10. denial records decision reason.
11. buyer report shows credit or denial.

Approved return behavior:

- credit amount equals original lead debit amount.
- buyer wallet increases by credit amount.
- `billing_events.event_type = lead.returned`.
- `post_results.returned = true`.
- `post_results.return_reason = reason`.

Denied return behavior:

- no wallet change.
- decision notes explain why the lead was valid or evidence was insufficient.
- optional billing event: `lead.return_denied`.

### return request data model

Future table: `lead_return_requests`.

Fields:

- `id`.
- `lead_id`.
- `buyer_id`.
- `post_result_id`.
- `reason`.
- `status`.
- `contractor_notes`.
- `evidence_urls`.
- `call_recording_id`.
- `call_attempted_at`.
- `requested_at`.
- `reviewed_at`.
- `reviewed_by`.
- `decision_notes`.
- `credit_amount_cents`.
- `cash_refund_amount_cents`.
- `metadata_json`.

### refund abuse controls

Track and act on abuse signals:

- buyer return rate over 25%.
- buyer returns many valid leads as unreachable.
- buyer repeatedly calls after the response-speed window.
- buyer disputes leads in approved territories.
- buyer returns emergency opportunities after missing appointments.
- buyer has low close rate but high dispute rate.

Actions:

- require additional evidence.
- shorten return window for that buyer.
- move buyer to overflow.
- pause buyer.
- require higher wallet balance or signed terms before reactivation.

### ai voice nurture goal

AI voice nurture exists to increase lead quality before routing. it should convert incomplete or low-confidence leads into qualified leads or booked opportunities, not blast cold lists.

Primary jobs:

- confirm homeowner or decision-maker status.
- verify address and zip.
- confirm service needed.
- classify damage severity.
- confirm urgency.
- ask for photos by sms link.
- book callback or inspection window.
- handle missed-call follow-up.
- mark invalid leads before they reach buyers.
- route qualified leads to funded buyers.

AI voice should upgrade leads:

- class c to class b: incomplete lead becomes qualified exclusive lead.
- class c to class a: incomplete lead becomes booked emergency opportunity.
- class c to class d: invalid lead is suppressed and not sold.

### ai voice nurture triggers

Trigger ai voice when:

- homeowner submitted a form but lead is class c.
- form is incomplete.
- photos are missing.
- urgency is unclear.
- homeowner missed the first call.
- lead is unsold and needs more detail.
- contractor returned lead as unreachable and evidence needs review.
- lead appears high value but needs booking.

Do not trigger ai voice when:

- consent is missing.
- homeowner opted out.
- outside quiet hours.
- lead already sold and contractor owns follow-up.
- lead marked invalid.
- emergency requires human/911/utility guidance.

### ai voice conversation script

Opening:

```text
Hi, this is StormLead calling about your storm or tree removal request. I'm calling to confirm the details so we can match you with an available local crew.
```

Qualification questions:

```text
Are you the homeowner or the person authorized to request service?
What happened at the property?
Is the tree or damage on a house, garage, vehicle, driveway, or power line?
Is anyone in immediate danger?
What is the property address?
Do you need help today, tomorrow, or sometime this week?
Have you already hired someone for this job?
Can we send you a link to upload photos of the damage?
What is the best time for a local crew to call you back?
```

Safety branch:

```text
If anyone is in immediate danger or there are downed power lines, please contact emergency services or your utility provider first. I can still help note the request for a storm cleanup crew.
```

Photo branch:

```text
I can send you a link to upload photos so the local crew understands the damage before calling. Is this number okay for that link?
```

Booking branch:

```text
Would you prefer a callback as soon as possible, this afternoon, or tomorrow morning?
```

Do not say:

- we guarantee insurance will cover this.
- your house is damaged.
- we are with your insurer.
- we are with the government.
- you must act now or lose coverage.

### homeowner nurture sequences

Incomplete form sequence:

1. zero minutes: sms/email confirmation after consent.
2. five minutes: ask for photos.
3. thirty minutes: ask to confirm urgency.
4. two hours: offer same-day callback.
5. twenty-four hours: final follow-up.

Missed-call sequence:

1. zero minutes: missed-call sms.
2. fifteen minutes: second call attempt.
3. one hour: email with booking link.
4. twenty-four hours: final sms/email.

Emergency tier sequence:

1. immediate ai or human call.
2. immediate sms with safety note and callback expectation.
3. route to highest-response buyer.
4. if buyer does not answer within five minutes, route to next eligible buyer.

Unsold lead sequence:

1. try alternate funded buyer.
2. ask homeowner for more details/photos.
3. re-score lead.
4. route again if class a or b.
5. suppress if class d.

### contractor nurture sequences

New contractor prospect:

1. day zero: call plus intro email.
2. day one: roi and guarantee message.
3. day three: zip availability message.
4. day seven: smaller wallet test offer.

Low wallet:

1. wallet below two lead prices: refill warning.
2. wallet below one lead price: zip priority pause warning.
3. storm active in buyer zips: urgent refill message.

Post-delivery:

1. after each lead: delivery receipt.
2. daily: summary report.
3. weekly: roi/refill report.

Low-wallet message:

```text
Your StormLead wallet has $[balance], enough for about [count] more leads. Severe weather is active in your ZIPs. Refill $[amount] to keep ZIP priority active.
```

### ai voice architecture

Use self-hosted state and workflow control with a phone vendor for the telephone network.

Recommended v1:

- postgres for state, consent, lead class, transcripts, and audit records.
- hatchet for timed nurture workflows.
- `voice-bridge` service for call orchestration.
- twilio, telnyx, or vonage for phone calls.
- deepgram, whisper, or provider stt for speech-to-text.
- elevenlabs, cartesia, openai, or piper for text-to-speech.
- litellm-backed llm for dialogue, classification, and summaries.
- object storage for recordings/transcripts where legally allowed.
- ping-post for final buyer routing.

More self-hosted later:

- jambonz, freeswitch, or asterisk for telephony.
- faster-whisper or whisper.cpp for stt.
- piper or coqui for tts.

Do not start with fully self-hosted telephony unless vendor calls are impossible. telephony ops will slow the lead marketplace launch.

### ai voice call data model

Future table: `lead_voice_calls`.

Fields:

- `id`.
- `lead_id`.
- `provider`.
- `provider_call_id`.
- `direction`.
- `status`.
- `started_at`.
- `ended_at`.
- `duration_seconds`.
- `recording_object_key`.
- `transcript_object_key`.
- `summary`.
- `classification_before`.
- `classification_after`.
- `consent_basis`.
- `opt_out_detected`.
- `next_action`.
- `metadata_json`.

Future table: `nurture_events`.

Fields:

- `id`.
- `lead_id`.
- `buyer_id`.
- `sequence_name`.
- `channel`.
- `template_key`.
- `status`.
- `scheduled_at`.
- `sent_at`.
- `responded_at`.
- `error_reason`.
- `metadata_json`.

### ai voice compliance guardrails

Before enabling ai calls, enforce:

- clear consent checkbox for calls and texts.
- business identity disclosure at call start.
- opt-out detection and suppression.
- quiet hours.
- frequency caps.
- do-not-call suppression where applicable.
- call recording disclosure where required.
- no cold calling scraped or leaked data.
- no ai calls to homeowners without consent or another valid contact basis.
- no homeowner nurture after lead is sold unless the buyer contract permits stormlead follow-up.

Opt-out rule:

- if homeowner says stop, unsubscribe, do not call, remove me, or equivalent, set suppression immediately and stop non-transactional messages/calls.

### ai voice kpis

Track:

- ai call answer rate.
- conversation completion rate.
- class c to class b conversion rate.
- class c to class a conversion rate.
- photo upload rate.
- appointment booked rate.
- invalid lead detection rate.
- cost per qualified lead after ai nurture.
- average time to qualification.
- buyer return rate after ai qualification.

Most important ai nurture kpi:

- buyer return rate after ai-qualified calls.

If ai qualification lowers returns and increases booked opportunities, contractors will trust the guarantee and refill wallets.

### ai voice implementation sequence

Build in this order:

1. lead class field: class a, b, c, d.
2. opt-out and suppression fields.
3. nurture event table.
4. message template registry.
5. voice call metadata table.
6. voice-bridge service skeleton.
7. outbound call workflow for class c leads.
8. ai qualification prompt and deterministic extraction schema.
9. transcript summary and lead update.
10. route only class a and class b leads to ping-post.
11. buyer return-rate reporting by lead class.
12. low-wallet contractor nurture workflow.

### combined refund and nurture acceptance criteria

This system is ready when:

- contractor return reasons are documented and enforced.
- invalid leads credit wallet, not automatic cash refund.
- cash refunds are limited to unused wallet balance and billing errors.
- return request requires evidence.
- return windows are enforced.
- buyer return rate is tracked.
- leads have qualification class before routing.
- ai voice only calls consented leads.
- opt-out suppressions stop future nurture.
- ai transcripts produce structured summaries.
- class c leads can become class a/b or be suppressed as class d.
- buyer reports show delivered, credited, and ai-qualified leads separately.
