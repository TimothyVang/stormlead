# Validated Roadmap: StormLead Local Synthetic to Production Autonomous Funnel

Generated: 2026-05-10

## Verdict

StormLead is locally proven for synthetic ingestion, routing, buyer webhook simulation, returns, admin review, and browser evidence. It is not yet proven as a fully autonomous production lead-generation system. The safe path is a staged launch: keep the core lead-sale path in StormLead code, add external traffic and payments behind explicit approval gates, and use self-hosted tools only where they do not become an unreviewed source of truth for money, consent, or buyer delivery.

Confidence:

- Local synthetic lead ingestion into local DB: high, about 95% based on the completed Autopilot verification evidence.
- Production autonomous paid acquisition and sale: low-to-medium, about 35% until real ad APIs, public ingress, production DB, consent/compliance, buyer delivery, and payments are proven with budget caps and kill switches.

## Primary Evidence Used

- Google Ads API is the programmatic interface for managing Google Ads accounts/campaigns and supports automated account management, custom reporting, ad management, and Smart Bidding strategy management: https://developers.google.com/google-ads/api/docs/start
- Google Ads official client libraries exist for Java, .NET, PHP, Python, Ruby, and Perl; Google recommends starting with one for new API users: https://developers.google.com/google-ads/api/docs/client-libs
- Google Ads offline/enhanced conversions for leads require setup, customer data terms, normalized/hash user-provided data, `ClickConversion`, and upload through `ConversionUploadService`; the page warns new offline conversion workflows should prefer Data Manager API: https://developers.google.com/google-ads/api/docs/conversions/upload-clicks
- Google Ads test accounts do not serve ads, do not bill, cannot interact with production accounts, and cannot test some features including conversion uploads and billing: https://developers.google.com/google-ads/api/docs/best-practices/test-accounts
- Microsoft Advertising API requires OAuth user access tokens plus a developer token; Microsoft documents SDK starts for C#, Java, PHP, and Python and notes separate sandbox/production credentials: https://learn.microsoft.com/en-us/advertising/guides/get-started?view=bingads-13
- Meta developer documentation was not fetchable in this environment, but official Meta Business SDK repositories document the Business SDK, Marketing API app setup, app-secret proof, access tokens, and `ads_management` permissions: https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/README.md and https://raw.githubusercontent.com/facebook/facebook-nodejs-business-sdk/main/README.md
- Formbricks supports self-hosting, requires HTTPS, and documents minimum setup of 1 vCPU, 2 GB RAM, and 8 GB SSD: https://formbricks.com/docs/self-hosting/overview
- n8n documents self-hosted hosting and built-in nodes for webhooks, Postgres, Google Ads, Facebook Graph API, Mautic, Stripe, Supabase, and other integrations: https://docs.n8n.io/hosting/
- PostHog self-hosting is possible through Docker Compose, but PostHog warns self-hosters assume infrastructure/scaling/data-loss risk and paid-plan features are cloud-only: https://posthog.com/docs/self-host
- Mautic installation requires a database, admin account, and email server configuration; it can be installed with a production package, command line, GitHub clone, or Composer: https://docs.mautic.org/en/5.x/getting_started/how_to_install_mautic.html
- Stripe Checkout supports one-time and subscription payments through the Checkout Sessions API: https://docs.stripe.com/payments/checkout
- Stripe webhooks require HTTPS in live mode, signature verification, quick `2xx` response before complex work, duplicate handling, async processing, and do not guarantee event ordering: https://docs.stripe.com/webhooks
- Stripe provides official server-side SDKs including Python, Node, Ruby, Go, Java, PHP, and .NET: https://docs.stripe.com/sdks
- Stripe secret keys must stay server-side, should not be in source code, should use secrets management/environment variables, and should be rotated/audited: https://docs.stripe.com/keys-best-practices
- Stripe testing uses sandboxes/test keys/test cards and explicitly says not to use real card details for testing: https://docs.stripe.com/testing
- FTC Telemarketing Sales Rule guidance covers disclosures, misrepresentations, calling restrictions, caller ID, abandoned calls, unauthorized billing, Do Not Call, and recordkeeping: https://www.ftc.gov/business-guidance/resources/complying-telemarketing-sales-rule
- FTC CAN-SPAM guidance requires accurate headers, non-deceptive subject lines, ad identification, physical postal address, opt-out mechanism, prompt opt-out honoring, and responsibility for vendors: https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business
- FCC consumer guidance states prerecorded telemarketing calls need prior written consent and commercial texts require written consent; FCC rules also cover opt-out and Do Not Call: https://www.fcc.gov/general/telemarketing-and-robocalls
- 47 CFR 64.1200 is the FCC delivery-restrictions rule for autodialed/prerecorded/artificial voice calls, telemarketing, opt-out, Do Not Call, and consent handling: https://www.ecfr.gov/current/title-47/chapter-I/subchapter-B/part-64/subpart-L/section-64.1200
- OpenTelemetry is a vendor-neutral framework/toolkit for traces, metrics, and logs; it is not itself an observability backend: https://opentelemetry.io/docs/what-is-opentelemetry/
- Prometheus is an open-source systems monitoring and alerting toolkit for time-series metrics and alerting: https://prometheus.io/docs/introduction/overview/

## Required SDKs and Docs

Core application:

- Keep the StormLead lead ingestion, matching, sale, return, audit, and admin workflows in the existing Python services and database, not in a no-code workflow tool.
- Add OpenTelemetry SDK/instrumentation for services and worker jobs.
- Keep Playwright for deterministic browser proof and synthetic user journeys.

Traffic and ad platforms:

- Google Ads: official Google Ads API Python client (`google-ads`) plus OAuth credentials, developer token, manager/customer IDs, test manager account, Google Ads test accounts, and conversion-upload/Data Manager API docs.
- Microsoft Advertising: Microsoft Advertising/Bing Ads API Python SDK or SOAP/REST client path; requires OAuth user tokens, developer token, account/customer IDs, and sandbox credentials.
- Meta: official `facebook_business` Python SDK or Node SDK if the frontend/backend stack chooses Node for ad automation. Before implementation, manually verify current Meta Marketing API, Lead Ads retrieval, Webhooks, and Conversions API docs because direct developer-doc fetches failed here.

Payments and buyer billing:

- Stripe Python SDK, Checkout Sessions, webhooks, sandbox/test keys, restricted keys, key rotation, and webhook signature verification.
- If StormLead later acts as a marketplace or handles split payouts, research Stripe Connect separately before code changes.

Self-hosted funnel/supporting systems:

- Formbricks: optional self-hosted form/survey builder when marketing wants editable forms. Do not let it bypass StormLead consent logging and validation.
- n8n: optional self-hosted orchestration for backoffice alerts, CRM sync, enrichment queues, and internal ops. Do not use n8n as the authoritative ledger for lead sales or payments.
- PostHog: optional self-hosted analytics, but only if the team accepts infra/data-loss risk. Otherwise use minimal first-party event tables plus Prometheus/OTel.
- Mautic: optional self-hosted email automation for opted-in nurture only; requires an email provider, unsubscribe handling, and CAN-SPAM controls.

Compliance and safety:

- FTC TSR, FCC TCPA/47 CFR 64.1200, National Do Not Call, CAN-SPAM, state privacy/telemarketing laws, ad-platform policies, privacy policy/terms, consent disclosure versioning, and legal review.
- This is not legal advice. Production launch should be reviewed by counsel before phone/SMS/email outreach or paid traffic at scale.

## Production Architecture

Minimum production path:

- Public landing pages capture consented homeowner leads through StormLead-owned forms or embedded Formbricks forms that post into StormLead.
- Ingestion API validates source, UTM/GCLID/MSCLKID/FBCLID, IP, user agent, disclosure version, consent checkbox state, phone/email opt-in, jurisdiction, service type, and dedupe keys.
- Lead scoring/routing worker evaluates synthetic/real marker, service/geography, buyer budgets, caps, exclusivity, consent constraints, and fraud checks.
- Buyer sale engine sends signed idempotent webhooks, tracks delivery attempts, retries with backoff, records ACK/NACK, and prevents duplicate billing.
- Buyer wallet/billing engine uses Stripe Checkout for top-ups or subscriptions, Stripe webhooks for payment state, and an internal ledger for credits/debits/refunds/returns.
- Admin review stays available for returns, disputes, unusual lead velocity, low confidence scoring, and buyer complaints.
- Observability emits traces, metrics, logs, and business events for ingestion, routing, webhook delivery, buyer wallet, return state, ad spend, and conversion feedback.

Self-hosted support stack:

- Reverse proxy/TLS: Caddy/Traefik/nginx with valid certificates.
- App/data: existing StormLead services, Postgres, Redis/queue, object storage for evidence/log bundles if needed.
- Workflow: n8n for non-critical sync/alerts only.
- Marketing CRM: Mautic for opted-in email nurture only.
- Form/survey: Formbricks when non-engineers need form iteration.
- Analytics: first-party events plus optional PostHog.
- Monitoring: OpenTelemetry collector, Prometheus, Grafana/Alertmanager or equivalent.

## Validation Gates

Gate 0: Current local proof

- Status: passed for local synthetic operation.
- Keep: `uv run pytest -q services libs`, `uv run mypy services libs`, `npm run test:playwright -- --project=api --reporter=line`, local smoke, self-learning/TARS evidence, and `git diff --check`.

Gate 1: Public-ingress staging, synthetic only

- Public HTTPS endpoint receives only signed synthetic test submissions.
- No real ad spend, no real homeowner outreach, no live payment capture.
- Required proof: consent fields persisted, dedupe works, no PII in logs beyond allowed redacted views, buyer webhook replay is idempotent, Stripe sandbox webhook signatures verified.

Gate 2: Ad-platform sandbox/test integration

- Google test accounts for campaign/account API calls; note Google test accounts cannot validate serving metrics, billing, or conversion uploads.
- Microsoft Advertising sandbox credentials for account/campaign API calls.
- Meta app/test mode after manual docs verification.
- Required proof: no production account IDs accepted by staging, all credentials from secret store, all mutations dry-run or sandbox-scoped.

Gate 3: Paid canary with manual approval

- Small budget, one geography, one service, one or two friendly buyers.
- Human approval required before creating live campaigns, increasing budget, contacting leads, sending SMS/email/phone, or billing buyers.
- Required proof: cost per valid lead, sale rate, return rate, buyer ACK latency, webhook failure rate, refund exposure, and false-positive/fraud review.

Gate 4: Semi-autonomous capped production

- System may optimize bids/budgets within fixed daily and campaign caps.
- Hard kill switches for each traffic source, buyer, service, geography, and communication channel.
- Required proof: 30-day stable return/dispute rate, budget guardrails never exceeded, conversion feedback loop matches ledger, all opt-outs honored, DNC/privacy checks audited.

Gate 5: Autonomous operation

- Only after counsel-approved compliance posture, real conversion feedback, buyer contracts/SLAs, incident response, secrets rotation, monitoring/alerting, and rollback drills.
- Autonomy should mean controlled optimization within approved policies, not unrestricted campaign creation, outreach, or spending.

## Open Gaps

- Meta Marketing API, Lead Ads retrieval, Webhooks, and Conversions API docs could not be fetched from developers.facebook.com in this environment. Use official SDK repos only as partial evidence and manually verify current docs before implementation.
- Microsoft conversion/offline conversion documentation still needs a successful fetch or manual review before implementing conversion feedback for Microsoft Ads.
- State-by-state lead-gen, telemarketing, contractor/home-services, and privacy requirements need counsel review.
- Real buyer contracts, refund policy, return policy, and service-level rules are business/legal artifacts, not just code.
- Real ad spend, public webhooks, production payment capture, SMS/email/phone, and real homeowner contact remain approval-gated.

## Recommended Next Implementation Order

1. Add a production-readiness checklist and environment gate that refuses live traffic without explicit `STORMLEAD_ENV=production`, approved domain, secrets store, and kill-switch config.
2. Add consent/provenance schema fields for source, campaign IDs, click IDs, disclosure version, consent text hash, opt-in channel, IP/user-agent, and opt-out state.
3. Add signed/idempotent buyer webhook delivery with replay tooling and delivery metrics if not already production-grade.
4. Add Stripe sandbox buyer-wallet top-up flow with webhook signature verification and ledger reconciliation.
5. Add Google Ads test-account integration for read/report/dry-run campaign operations and conversion-feedback model, keeping live mutations disabled.
6. Add Microsoft and Meta integrations only after docs and sandbox/test mode are verified.
7. Add compliance dashboards: DNC/opt-out state, consent audit, buyer returns, lead source ROI, webhook failures, budget caps, and incident kill switches.
