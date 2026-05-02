# architectural fit — is this the best framework?

open research on whether the scaffold's architecture is the right shape for a single-operator b2b saas doing storm-chase tree-removal lead-gen. dispatched two parallel research agents — one comparing 9 architectural alternatives ranked for *this* business profile, one hunting for what production lead-marketplace operators actually run. they converged on the same headline.

## TL;DR

- **the bones are right; the dressing is over-engineered for v1.** postgres-everything + hatchet for durable workflows + fastapi for the http auction surface is genuinely aligned with the 2024–2026 industry trend. but three sidecar pieces add real ops surface without earning their cost at indie scale: **nats, seaweedfs, and openbao**. cutting them halves the ops surface with zero v1 capability loss.
- **deploy the hetzner box to a us region** (ashburn or hillsboro). tree-removal contractors are us-based; eu-us rtt of 150–200ms eats most of the auction's <5s budget on every ping/post round-trip. hetzner has us locations now.
- **dbos transact deserves a 1-day spike** as a hatchet replacement (postgres-only durable execution as a python *library*, no separate orchestrator). deferred until agent-runtime work begins.
- **python+fastapi for the auction core is off the paved road but not damning.** no public ping-post operator runs it (leadconduit = node, prebid server = go+java, big operators = opaque). there is no reference codebase to copy.

## convergent findings (both agents)

1. **hatchet + nats is redundant.** hatchet itself provides durable workflows on postgres; cross-service events become hatchet event triggers or postgres `LISTEN/NOTIFY`. hatchet's own blog argues against running it alongside a separate bus for typical workloads. cut nats for v1; revisit only if a concrete cross-service eventing need appears.

2. **postgres-as-everything is the 2024–2026 industry trend.** river, hatchet, inngest, solid queue, dbos, trigger.dev all lean on it. seaweedfs/minio remain useful but for a solo operator on hetzner, hetzner object storage (~$5/mo, s3-compatible) is the boring choice.

3. **no public consensus stack for ping-post exists.** boberdoo, phonexa, leadspedia, lead wrench, adrack, xzazu ship zero engineering blogs. ActiveProspect/leadconduit publishes node.js modules on github (https://github.com/activeprospect/leadconduit-integration). prebid server (closest public reference for parallel real-time auctions) maintains parallel go and java codebases. **the "we replatformed a 7-figure ping-post operator" essay does not exist publicly** — that absence is the most important meta-finding.

## what the alternatives actually offer (top contenders)

ranked for *this* profile (single-operator python eng, hetzner $80–200/mo, tcpa-defensible audit trail, auction <5s sla, 4–8 week mvp):

| candidate | time-to-mvp | ops hr/wk | why pick it | why not |
|---|---|---|---|---|
| **status quo, collapsed** (cut nats/seaweedfs/openbao; keep python+fastapi+hatchet+postgres+caddy) | 4-6 wk | 1-2 | best fit for a python-first operator; postgres-as-everything aligned; minimal moving parts after cuts | hatchet v0.50 → v1 migration looms; no reference codebase for python ping-post |
| **dbos transact replaces hatchet** | 5-7 wk | 0.5-1 | eliminates 3 hatchet containers; durable workflows as a python *library*; audit trail comes free from postgres | dbos is young (2024-2025); fewer prod stories than hatchet |
| **phoenix/elixir + oban + broadway** | 10-14 wk | 1-2 | technically correct for 500 leads/sec + voice ai; otp supervision is the right substrate for telephony | requires committing to elixir; off the python-first path; py reuse zero |

## rejected alternatives (with reasons)

- **rails 8 monolith (solid queue/cache/cable)**: solid queue caps at ~5–10k jobs/min before postgres write pressure becomes meaningful. fine for v1 but hits the wall at the *aspirational* 500 leads/sec scale.
- **encore.dev (ts)**: declarative infra-as-code is appealing but the operator's strongest language is python; ecosystem mismatch is a multi-month tax.
- **modal labs / cloudflare workers**: serverless-native but cost ceiling is hard to predict and the audit-trail story (court-defensible logs you control) gets harder when state lives in someone else's platform.
- **supabase + vercel + n8n**: lowest-code path but tcpa litigation up ~95% yoy in 2025 (q1 2025 = 507 class actions, avg settlement >$6.6m). argues against a managed durable-execution platform owning your state. own your audit trail.
- **convex**: cloud-first; oss self-host is real but feature priority follows revenue.
- **trigger.dev v3 self-host**: harder than v2; requires criu checkpointing + multi-container orchestration. footgun for solo operator.
- **inngest self-host**: similar to trigger.dev; cloud is fine but locks billing.
- **leadexec / boberdoo as the ping-post engine** (buy not build): leadexec free tier (250 leads/mo, 10k pings/mo) compresses ping-post ttm from weeks to days. real option *if you give up the moat-code narrative* — the readme explicitly identifies ping-post as "the wedge." keep this option warm; revisit only if mvp slips beyond 8 weeks.

## what production operators actually run (the empirical hunt)

| operator | stack signal | confidence |
|---|---|---|
| boberdoo | datadog-monitored saas, "tens of millions req/day"; language not disclosed; founded 2000 (likely php/mysql roots) | low |
| activeprospect / leadconduit | **node.js** (public github: leadconduit-integration, leadconduit-types) | high |
| phonexa, leadspedia, lead wrench, adrack, xzazu, leadbyte | no public engineering disclosure | opaque |
| everquote | eks + aws lambda (nextjs via sst/opennext) + cloudfront + elasticache redis | high |
| prebid server | **two parallel codebases: go (original) + java (rubicon port)**, kept feature-equivalent | high |
| xandr/appnexus | openrtb 2.6, ~100ms total auction budget, ~18ms inter-dc latency cited; language not disclosed | medium |

**takeaways**:
- node.js, go, and java dominate among the operators who publish anything. **no public operator runs python+fastapi for the auction core** — not damning, but you're off the paved road.
- everquote replatformed onto aws lambda + sst + cloudfront — opposite of hetzner-bare-metal philosophy. useful as evidence that successful operators run very differently; not transferable to a $80–200/mo budget.
- xandr/appnexus 18ms inter-dc latency budget is 100× tighter than a lead-auction needs, but the principle — *synchronous auction endpoints must live close to bidders* — applies. eu→us rtt is real cliff.

## tcpa engineering (defensibility argues against managed platforms)

tcpa litigation up ~95% yoy in 2025; q1 2025 saw 507 class actions; avg settlement >$6.6m. fcc one-to-one consent rule died (vacated jan 2025; abandoned aug/sep 2025) — *good news* for ping-post architecture; pewc (writing + signature + clear disclosures) is the standard.

engineering implications:
- **own your audit trail.** keep consent records in *your* postgres with worm archive (timescale hypertable + hetzner object storage hash-chain export, ~$3/mo).
- **append-only event log keyed by lead uuid; dispute = log replay.** no specialized oss exists; `pgaudit` or logical replication is sufficient.
- **trustedform / jornaya remain courtroom-tested.** integrate the cert-url capture but don't bet defensibility on a vendor — verisk/jornaya + activeprospect/trustedform consolidated under infutordata in 2025; vendor concentration risk is real.

## decisions

### confirmed by user (2026-05-02)

- **scope**: research doc + tier-1 cuts in one session (this doc + compose cuts + readme update).
- **hetzner region**: deploy to a us region (ashburn or hillsboro). doc-only change in this session; actual redeploy happens before first paying buyer.
- **dbos spike**: deferred until agent-runtime work begins.

### tier-1 cuts (executed in this session)

1. **cut nats from compose** — hatchet handles durable workflows; cross-service events become hatchet triggers or postgres listen/notify. saves ~256mb ram + one cve feed. removed from `infra/compose/dev/docker-compose.yml`; `NATS_URL` and `NATS_STREAM_*` removed from `.env.example`.
2. **cut seaweedfs from compose** — hetzner object storage (~$5/mo, s3-compat) is the boring choice. removed service block + `infra/seaweedfs/s3.json`. `S3_ENDPOINT` in `.env.example` updated to point at hetzner object storage by default with a comment for local-dev minio fallback.
3. **defer openbao** — secret rotation is a 2-operator problem. `.env` + `sops`-encrypted `.env.prod` is enough until a second operator. removed service block; `infra/openbao/` retained as a forward-looking placeholder with a `README.md` deferred-note pointing here.
4. **document hetzner us region** — added a known-trap to top-level `README.md` calling out ashburn/hillsboro, eu→us rtt cost.

### tier-2 (not blocking; future spikes)

- **dbos transact vs hatchet v1**: 1-day spike when next touching the workflow layer (agent-runtime / voice-bridge). if dbos covers auction + storm-watcher cron + agent-runtime workflows, replaces hatchet (3 containers → 0). if it struggles on any, migrate hatchet v0.50 → v1 instead.
- **storm-event detector watermark durability**: regardless of orchestrator, the storm poller needs to persist `last-seen alert id` so a restart doesn't re-process backlog. trivial in either hatchet or dbos.
- **cloudflare in front of pseo**: when `apps/landing` returns, host as static export on cloudflare pages or vercel free tier — not on hetzner. reinforced by the latency findings.

### tier-3 (defer until first paying buyer)

- phoenix/elixir or go/rust ping-post rewrite. premature.
- buying leadexec / boberdoo as the ping-post engine. keep warm; revisit only if mvp slips beyond 8 weeks.
- multi-region (us pop for the synchronous auction endpoint, eu origin for everything else). premature.

## sources

- dbos transact python: https://github.com/dbos-inc/dbos-transact-py
- hatchet v1 announcement: https://github.com/hatchet-dev/hatchet/discussions/1348
- trigger.dev v3 self-host caveats: https://trigger.dev/docs/v3/open-source-self-hosting
- armin ronacher — "absurd workflows" (nov 2025): https://lucumr.pocoo.org/2025/11/3/absurd-workflows/
- activeprospect / leadconduit node modules: https://github.com/activeprospect/leadconduit-integration
- everquote serverless replatform: https://aws.amazon.com/blogs/mt/how-everquote-underwent-a-serverless-transformation-using-aws/
- prebid server (go + java parallel codebases): https://docs.prebid.org/prebid-server/versions/pbs-versions-overview.html
- xandr openrtb latency reference: https://learn.microsoft.com/en-us/xandr/supply-partners/openrtb-specs
- rails 8 solid stack vs redis+sidekiq: https://rubylearning.com/blog/2026/03/19/rails-8-solid-stack-vs-redis-sidekiq-production/
- river (postgres job queue, go): https://github.com/riverqueue/river
- postgres-as-queue trend (hn discussion): https://news.ycombinator.com/item?id=38349716
- hatchet's "don't run hatchet + a separate bus" position: https://docs.hatchet.run/blog/background-tasks-fastapi-hatchet
- hetzner object storage: https://www.hetzner.com/storage/object-storage
- hetzner us data centers: https://www.hetzner.com/cloud
- parker poe — tcpa tightrope 2025: https://www.parkerpoe.com/news/2025/10/the-tcpa-tightrope-why-2025-is-a-turning
- standard information — 7 best ping post 2025: https://standardinformation.com/company/resources/7-best-ping-post-software-platforms-for-2025
