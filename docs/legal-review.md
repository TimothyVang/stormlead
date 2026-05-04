# legal review tracker

Centralized legal, compliance, privacy, licensing, and commercial-terms wording for lawyer review.

Review fields:

- owner: legal counsel.
- status: `not reviewed`, `approved`, `revise`, or `blocked`.
- notes: counsel comments and required changes.

## review queue

| topic | status | notes |
| --- | --- | --- |
| project licensing and redistribution | not reviewed |  |
| open-source license exposure | not reviewed |  |
| model-provider/auth policy | not reviewed |  |
| commercial pilot readiness gates | not reviewed |  |
| homeowner consent, privacy, opt-out, and data retention | not reviewed |  |
| DNC/TCPA-style review | not reviewed |  |
| buyer data-use restrictions | not reviewed |  |
| lead-quality guarantee and contractor terms | not reviewed |  |
| wallet credits, cash refunds, returns, and chargebacks | not reviewed |  |
| direct mail, ads, and marketing claims | not reviewed |  |
| AI voice, SMS, calls, recording, and nurture | not reviewed |  |
| defensive breach-intel acceptable use | not reviewed |  |
| production secrets and evidence handling | not reviewed |  |

## project licensing and redistribution

Current internal wording:

```text
internal. not for redistribution. (no LICENSE file yet — decide before any external sharing.)
```

## open-source license and vendor exposure

Open-source and vendor risks requiring legal review:

- `twenty crm = agpl-3.0.` if buyers ever hit a modified Twenty UI, source-disclosure triggers. Mitigation proposed in research: keep buyers on API/webhooks, or buy a commercial license.
- `ultralytics yolov8/v11 = agpl-3.0.` if vision is added, use Florence-2, Detectron2, or LLaVA instead of Ultralytics unless counsel approves the license posture.
- Formbricks v3+ moved SSO/OIDC to paid enterprise editions; flag if a team forms or SSO becomes buyer/operator-facing.
- Older stack research flagged license traps in n8n, Dify, Netbird, Formbricks, Twenty, and Ultralytics.
- Production code should avoid AGPL-triggering exposure to buyers unless source-disclosure, commercial licensing, or isolation strategy is approved.

## model-provider and auth policy

Model/runtime policy wording requiring review:

- Runtime model calls use the LiteLLM OpenAI-compatible proxy only.
- Direct provider SDKs are not allowed in runtime services; static tests reject direct Anthropic/OpenAI SDK imports.
- Historical research concluded that `CLAUDE_CODE_OAUTH_TOKEN` can be viable for single-operator personal automation, but Claude.ai login must not be offered to end users.
- If buyers become principals or receive agent access, switch to API-key/provider-account flows approved for that product shape.
- Lead text, buyer payloads, call transcripts, webhook bodies, browser content, and documents are untrusted data, not instructions.
- Model output may explain or classify, but money movement, routing, spend launch, return approval, and buyer activation require deterministic code checks plus persisted audit rows.

## commercial pilot readiness gates

Do not claim or run commercial pilot readiness until counsel/user-owned launch blockers are resolved:

- Do not perform real-world actions unless explicitly approved in-session: no buyer/homeowner/vendor contact, live ad spend, live payments, public internet exposure, public webhook registration, or production traffic.
- Do not use placeholder buyer names, prices, payment references, campaign budgets, signed commitments, or compliance approvals to claim commercial pilot readiness.
- `technical V1 ready` means code/local-validation readiness only.
- `commercial pilot ready` additionally requires real buyer commitments, approved payment terms, explicit launch approval, and compliance readiness.
- Compliance readiness is a hard gate for real homeowner lead handling: consent, opt-out/suppression, privacy/terms disclosure, DNC/TCPA-style review, data retention/deletion, buyer-use restrictions, and audit evidence must be implemented or explicitly marked blocked before launch.
- Production/public routing checks are config/local validation unless the user approves actual internet exposure.
- Do not contact real buyers, homeowners, vendors, forums, ad platforms, payment providers, or external partners unless the user explicitly asks in the current session.
- Do not run ads, activate paid campaigns, trigger real payments, create live payment links, expose public services, register public webhooks, or send production traffic without explicit user approval.
- Do not invent real buyer names, pricing commitments, payment references, signed agreements, campaign budgets, or pilot outcomes.
- Do not claim commercial paid-pilot readiness based on placeholder commitments, unreviewed compliance, or unapproved public exposure.
- Use `blocked pending real buyer commitments` when real buyer names, prices, signed/paid commitments, delivery terms, or wallet/refill approvals are missing.
- Use `blocked pending compliance review` when consent language, privacy/terms, opt-out/DNC suppression, retention/deletion, buyer-use restrictions, or legal/compliance owner approval is missing.

First paid-launch gate wording:

- Three funded buyers exist in one market.
- Each active buyer has accepted service zips, services, caps, lead prices, and return rules.
- Available wallet balance covers planned campaign spend risk.
- Landing page and consent capture are tested.
- Call tracking works for the campaign.
- Ping-post can route a test lead to a funded buyer.
- Invalid lead credit flow works.
- Admin can see buyer wallets, sold leads, returned leads, and campaign source.
- Campaign budget cap and stop-loss rules are set.

## homeowner consent, privacy, opt-out, and data retention

Homeowner data and privacy wording requiring review:

- Capture a consented homeowner lead with campaign/source attribution and a durable consent/compliance audit trail.
- Show opt-out/suppression, privacy/terms disclosure, retention/deletion, and buyer-use restriction readiness for real homeowner lead handling.
- Store exact consent text and audit data, but do not expose it casually in UI.
- Store exact consent text and page hash/version for each lead when consent text changes between landing page versions.
- Provide a real opt-out/suppression path or documented manual suppression process before real homeowner leads are used.
- Document DNC/TCPA-style review status, including what is implemented, what is manual, who owns approval, and what blocks commercial launch.
- Document data retention/deletion expectations for homeowner PII, consent audit records, buyer reports, generated artifacts, and local evidence.
- Homeowner opts out after lead is sold: store suppression immediately and notify the buyer if contract requires downstream suppression.
- Homeowner asks who received their data: keep a disclosure log of buyer, timestamp, and delivery channel.
- Photos containing sensitive people, license plates, or unrelated interiors should be stored privately and limited to needed evidence.
- Life-safety or downed power-line leads should show emergency guidance and route only after safety warning; AI must not imply emergency services.

## PII, admin UI, and evidence handling

Privacy/security wording requiring review:

- Keep PII redacted at API/UI/artifact boundaries by default.
- Redact PII at API/UI boundaries by default; only show raw PII where the existing admin UI already does and the operator needs it.
- Treat lead PII as production-sensitive even in dev.
- Do not put raw lead PII into Playwright artifact metadata manifests.
- Never render full phone numbers, raw addresses, email addresses, webhook secrets, API keys, auth tokens, or full model prompts in timeline payload summaries.
- Do not expose webhook secrets, buyer webhook URLs with embedded tokens, LiteLLM keys, Hatchet tokens, Langfuse secrets, or `.env` contents in timeline UI.
- Do not add screenshots/videos/traces to git.
- Do not make admin endpoints public-facing or unauthenticated beyond current local/dev assumptions without documenting the risk.
- Payload summaries should redact sensitive keys such as email, phone, consent, secrets, tokens, raw payloads, prompts, and webhook secrets; URLs should be query-stripped.
- Generated evidence artifacts should stay ignored unless manually curated and redacted.

## buyer data-use restrictions

Buyer-use wording requiring review:

- Buyer-facing docs/reports restrict use of homeowner lead data to the approved pilot purpose and prohibit resale, spam, or unauthorized sharing.
- Lead data may be used only for the approved pilot service/market.
- Lead data must not be resold, spammed, shared outside the buyer's operating team, or used after return/invalid status unless the policy explicitly permits it.
- Do not expose raw PII in UI/artifacts beyond operator need.
- Do not sell class C leads automatically unless manual override records that the lead was sold below the guarantee class.

## lead-quality guarantee and contractor terms

Positioning:

```text
StormLead matches homeowners requesting storm/tree services with qualified local contractors. Contractor payment is for valid lead delivery or booked opportunity matching, not guaranteed job closure.
```

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

Valid lead criteria:

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

Premium booked opportunities should also include:

- damage tier confirmed.
- urgency confirmed.
- photos collected when possible.
- callback or inspection window booked.
- high-value signal such as tree on structure, driveway blocked, vehicle damage, crane likelihood, or active storm emergency.

## wallet credits, cash refunds, returns, and chargebacks

Policy wording:

- Use wallet credits first and cash refunds second.
- Wallet credit applies when a delivered lead is invalid under the allowed return reasons. The credit restores the original lead debit to the buyer wallet.
- Cash refund applies only when money should leave StormLead and return to the buyer payment method.
- Cash refunds are not the default remedy for ordinary bad leads. Approved invalid leads should become wallet credits.

Cash refunds are allowed for:

- unused wallet balance after buyer cancellation and dispute review.
- duplicate deposit.
- accidental overpayment.
- billing error.
- StormLead cannot serve the buyer's approved territory after taking payment.

Cancellation policy:

- buyer can cancel anytime.
- delivered valid leads are non-refundable.
- pending lead disputes must be resolved before final cash refund calculation.
- approved invalid leads are credited before final refund calculation.
- final cash refund equals unused wallet balance minus outstanding valid lead charges and any agreed non-refundable setup fee.

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

Return windows:

- standard lead: 72 hours from delivery.
- booked emergency opportunity: 24 hours from delivery.
- duplicate, no consent record, or system delivery error: 7 days from delivery.
- unused wallet refund: after cancellation and all pending dispute review.

Expired return requests should be denied unless the issue is a system/billing error.

Contractor proof requirements:

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

Return review workflow:

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

Return request states:

- `requested`.
- `needs_evidence`.
- `approved`.
- `denied`.
- `expired`.
- `credited`.
- `cash_refunded`.

Return request data model fields:

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

Refund abuse signals:

- buyer return rate over 25%.
- buyer returns many valid leads as unreachable.
- buyer repeatedly calls after the response-speed window.
- buyer disputes leads in approved territories.
- buyer returns emergency opportunities after missing appointments.
- buyer has low close rate but high dispute rate.

Abuse controls:

- require additional evidence.
- shorten return window for that buyer.
- move buyer to overflow.
- pause buyer.
- require higher wallet balance or signed terms before reactivation.

Refund and return edge cases:

- buyer requests cash refund while lead disputes are open: freeze refund calculation until disputes resolve.
- buyer chargeback occurs after leads were delivered: pause buyer, freeze routing, and reconcile wallet manually.
- approved return after buyer already received final refund: create payable credit or manual adjustment; do not silently change historical ledger.
- denied return with strong buyer objection: escalate to manual review and record final decision notes.
- duplicate return request for same `post_result`: enforce one active return request per post result.

## contractor sales and buyer onboarding wording

Default V1 offer:

- `$1,000` prepaid wallet.
- `$150` to `$250` per valid exclusive lead.
- invalid leads credited by rule.
- zip priority while the wallet is funded.
- daily cap controlled by buyer.
- daily report sent automatically.

Contractor pitch:

```text
We generate exclusive storm/tree removal opportunities from homeowners in your service area. You do not pay for clicks or ads. You only pay for valid leads that match your ZIPs and service rules.

The starter wallet is $1,000. Each valid exclusive lead is deducted from that balance at the agreed rate. If it is a wrong number, duplicate, outside your area, spam, or already completed, I credit it back.

I only protect ZIP priority for funded buyers. What ZIPs do you want covered first?
```

Buyer onboarding terms requiring acknowledgement:

- lead price accepted.
- daily cap accepted.
- valid-lead definition accepted.
- return reasons accepted.
- wallet deposit recorded.
- response expectation accepted.
- low-balance refill rule accepted.

First buyer onboarding should include buyer profile, service area, target zips, caps, price, wallet deposit/refill reference, delivery endpoint or manual delivery path, test lead, return policy acknowledgement, and daily report recipient.

## direct mail, ads, and marketing claims

Direct mail positioning:

```text
Turn a storm event into a compliant direct-mail campaign that drives homeowners to a tracked call number or QR landing page. Direct mail is the safer outbound channel for cold homeowner targeting; phone, SMS, and email follow-up should come after opt-in or another legally valid basis.
```

Mailer targeting and suppression wording:

- Use county assessor or GIS parcel exports for property address, mailing address, owner name where public, property type, year built, and owner-occupied signal.
- Use permit data where available to suppress properties with recent roof/tree/storm repair work.
- Use CRM suppression lists for do-not-mail, prior disputes, customers already contacted, and buyers' excluded territories.
- Exclude renters where the owner mailing address is known and different from the property address unless the campaign is owner-mail only.
- Exclude any address on suppression lists.

Creative requirements:

- Do say: `your area was affected by severe weather on [date]` when supported by storm data.
- Do say: `schedule a free storm/tree damage assessment` if the buyer can service it.
- Do not claim a specific house is damaged unless there was a permissioned inspection.
- Do not imply government, insurance-carrier, or emergency-service affiliation.
- Include business identity, contact info, opt-out or mail suppression instructions, and service-area disclaimers.

Homeowner landing-page requirements:

- storm/date/area claim must be supported by source data.
- service offer must be specific: tree removal, hurricane cleanup, storm cleanup, or inspection.
- phone number must be trackable by campaign.
- form must collect consent before contact/routing.
- form must collect address and zip.
- form should collect damage type, urgency, and photos when possible.
- page must avoid insurance, government, or guaranteed-coverage claims.

Prohibited AI/marketing script claims:

- we guarantee insurance will cover this.
- your house is damaged.
- we are with your insurer.
- we are with the government.
- you must act now or lose coverage.

## AI voice, SMS, calls, recording, and nurture

AI voice nurture exists to increase lead quality before routing. It should convert incomplete or low-confidence leads into qualified leads or booked opportunities, not blast cold lists.

AI voice should upgrade leads:

- class C to class B: incomplete lead becomes qualified exclusive lead.
- class C to class A: incomplete lead becomes booked emergency opportunity.
- class C to class D: invalid lead is suppressed and not sold.

Trigger AI voice when:

- homeowner submitted a form but lead is class C.
- form is incomplete.
- photos are missing.
- urgency is unclear.
- homeowner missed the first call.
- lead is unsold and needs more detail.
- contractor returned lead as unreachable and evidence needs review.
- lead appears high value but needs booking.

Do not trigger AI voice when:

- consent is missing.
- homeowner opted out.
- outside quiet hours.
- lead already sold and contractor owns follow-up.
- lead marked invalid.
- emergency requires human/911/utility guidance.

Opening script:

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

AI voice compliance guardrails:

- clear consent checkbox for calls and texts.
- business identity disclosure at call start.
- opt-out detection and suppression.
- quiet hours.
- frequency caps.
- do-not-call suppression where applicable.
- call recording disclosure where required.
- no cold calling scraped or leaked data.
- no AI calls to homeowners without consent or another valid contact basis.
- no homeowner nurture after lead is sold unless the buyer contract permits StormLead follow-up.

Opt-out rule:

- if homeowner says stop, unsubscribe, do not call, remove me, or equivalent, set suppression immediately and stop non-transactional messages/calls.

Call recording:

- if a call recording state requires all-party consent, play recording disclosure before recording or disable recording in those states.

## defensive breach-intel acceptable use

Purpose:

```text
Maintain a defensive-only exposure monitoring workflow for company-owned or explicitly authorized domains, customers, vendors, and infrastructure. This workflow must not be used for lead generation, contact enrichment, ad targeting, profiling, or marketing outreach.
```

Scope:

- monitor only owned company assets or client/customer assets with written authorization.
- track exposed company domains, employee emails, app names, API key patterns, GitHub orgs, cloud assets, and vendor references.
- do not download, redistribute, or process leaked third-party personal data beyond what is strictly necessary to confirm and report exposure.

Safe sources:

- Have I Been Pwned domain search.
- GitHub, GitLab, and Bitbucket public code search.
- public cloud bucket exposure checks.
- Shodan/Censys for owned or authorized infrastructure.
- state attorney general breach notification portals.
- SEC cyber incident disclosures.
- vendor security advisories and trust pages.
- `security.txt` contacts at `/.well-known/security.txt`.

Workflow:

1. define the authorized search scope.
2. search for indicators, not full leaked datasets.
3. record source URL, timestamp, affected domain/system, and redacted evidence.
4. avoid downloading full dumps or opening unrelated personal records.
5. classify severity: P1 exposed active secret, credential, database, or live system; P2 customer PII exposure; P3 employee credential exposure; P4 historical or stale exposure mention.
6. notify the owner through `security@domain.com`, `security.txt`, vendor portal, or cloud provider abuse channel.
7. if StormLead customers are affected, involve counsel/compliance before notification.
8. store only sanitized findings unless legal/security review approves retaining raw evidence.
9. rotate secrets, force password resets, and review access logs where applicable.
10. document remediation and retention/deletion decisions.

Guardrails:

- no use of leaked data for sales, marketing, lead generation, phone/email append, or ad audiences.
- no credential testing or login attempts.
- no downloading full breach dumps unless counsel approves and there is a specific defensive need.
- no sharing raw PII through Slack, email, cloud drives, or AI tools.
- keep an audit trail of who accessed datasets and why.

## production secrets and evidence handling

Secrets policy wording:

- No production secret should be committed to git, copied into compose files, passed through Docker build args, pasted into test artifacts, or stored in shell history.
- Production secrets should come from environment files with restricted file permissions or a dedicated secret manager.
- Rotating production secrets should require an audit trail and, once there is more than one operator, dual approval.
- Rotate immediately after suspected exposure; otherwise rotate API/provider secrets at least quarterly and database/admin credentials after operator changes or production incident response.
- Generated screenshots, videos, traces, manifests, and local absolute artifact paths should not be staged.

## regulatory research items to confirm

Items from prior research that require lawyer confirmation before launch:

- FCC one-to-one consent rule status and the restored pre-2023 PEWC standard.
- DNC/TCPA-style review for calls, texts, and AI voice.
- State-specific buyer licensing checks for Florida/Texas or other target markets.
- Call recording state-by-state consent requirements.
- Privacy/terms disclosure requirements for homeowner lead capture.
- Data retention/deletion requirements for homeowner PII, consent audit records, buyer reports, generated artifacts, call recordings, and transcripts.
- Buyer contract requirements for downstream suppression, data use, returns, wallet credits, cash refunds, non-refundable setup fees, chargebacks, and cancellation.
