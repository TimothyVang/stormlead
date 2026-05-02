# forkable open-source stack for an agentic storm-chase tree-removal lead-gen business

## TL;DR
- **the wedge**: there is no open-source boberdoo/leadconduit clone worth forking — that's the one piece you have to build yourself. everything else (storm ingestion, pseo pages, forms, voice, crm, agents, infra) has a strong forkable repo. start by forking **kortix-ai/suna** (apache-2.0) as your agent backbone, **twentyhq/twenty** (agpl) as your buyer crm, **jambonz** (mit) for telephony, and **agamm/pseo-next** (mit) for landing pages — then write a thin ping-post engine in rust/go on top of postgres yourself.
- **license danger zone**: twenty (agpl-3.0), formbricks (agpl-3.0 + paid EE), listmonk (agpl-3.0), plausible (agpl-3.0), mautic (gpl), and ultralytics yolov8 (agpl-3.0) are all strong copyleft. for a private/internal saas they're fine — agpl only triggers source-disclosure obligations if you let *outside* users (your buyers) interact with a *modified* version over the network. if you ever resell the platform multi-tenant, swap to mit-licensed alternatives or buy an EE license. n8n is "fair-code" (sustainable use license) — not OSI open source; flag for any reseller play.
- **wsl2/proxmox reality**: every recommendation here runs in docker compose. wsl2 dev works for all of them except hetzner-bare-metal pieces (sip/rtp media for jambonz/freeswitch need real udp + low latency — dev voice in wsl2 is painful, just ssh into hetzner for that loop). on proxmox, run one lxc per stack (crm, agents, telephony, sites) instead of one mega-vm so you can snapshot/restore independently.

---

## Key Findings

### what's actually forkable per layer

| layer | best fork target | stars | license | gotcha |
|---|---|---|---|---|
| agent os | `kortix-ai/suna` | ~20k+ | apache-2.0 | docker-in-docker sandbox; needs real linux |
| self-improving prompts | `NousResearch/hermes-agent-self-evolution` | 2.3k | mit | dspy+gepa, $2-10/run, no gpu needed |
| crm | `twentyhq/twenty` | ~44k | agpl-3.0 (+EE files) | agpl — keep your fork private |
| telephony/cpaas | `jambonz/jambonz-api-server` (org) | varies | mit | sip/rtp does not work right in wsl2 |
| voice ai pipeline | `pipecat-ai/pipecat` | ~10k | bsd-2 | python, async-heavy |
| pseo landing pages | `agamm/pseo-next` | small but clean | mit | next 13 isr pattern is the value |
| forms+consent | `formbricks/formbricks` | ~12k | agpl-3.0 + EE | sso/rbac gated to paid EE since v3.0 |
| browser scraping | `browser-use/browser-use` | ~75k | mit | needs chrome; heavy ram |
| llm-ready scraper | `unclecode/crawl4ai` | ~50k+ | apache-2.0 | docker image w/ playground+monitor |
| paas (hetzner) | `coollabsio/coolify` | ~50k | apache-2.0 | one-line install, manages multiple servers via ssh |
| newsletter/email | `knadh/listmonk` | ~17k | agpl-3.0 | single go binary + postgres |
| mail server | `mailcow/mailcow-dockerized` | ~12k | mostly mit/varied | needs proper rdns + ip reputation |
| analytics | `umami-software/umami` | ~25k | mit | mit > plausible (agpl) for your case |
| nws cap alerts | `zebpalmer/WeatherAlerts` | 33 | mit | stale (2017) — fork & port to py3.12 |
| nhc/hurdat2 | `tropycal/tropycal` | 1k+ | mit | actively maintained, real-time + best-track |
| atcf decks | `palewire/atcf-data-parser` | small | mit | clean cli wrapper around nhc ftp |
| fema disasters | `FEMA/openfema-samples` | official | public domain | use the api directly, fork samples for patterns |
| power outages | `simonw/pge-outages` + `GateHouseMedia/power-outages` | small | mit/apache | git-scraping pattern is the gold here |
| computer vision | `ultralytics/ultralytics` (yolo11/v8) | ~35k | **agpl-3.0** ⚠️ | agpl is a real problem — see below |
| agent memory | `letta-ai/letta` | ~20k | apache-2.0 | postgres-backed, mcp-friendly |
| mcp servers | `modelcontextprotocol/servers` | ~60k | mit | reference impls + pointers to community lists |
| ping-post engine | **none worth forking** | — | — | build it yourself in rust/go |

### the ping-post problem
i looked hard. there is no credible open-source equivalent of boberdoo, leadconduit, leadspedia, phonexa, or pingtreesystems on github. every "lead distribution platform" that comes up is either:
- closed-source SaaS with a marketing site (boberdoo, leadhandle, phonexa, leadbyte, xzazu, lead wrench)
- a generic n8n/zapier workflow people *call* "ping post"
- `eracle/OpenOutreach` which is a linkedin scraping outreach tool, not real ping-post
- ad-tech adjacent (prebid.js for header bidding) which has the *bidding pattern* you need but wrong domain

**your real path**: build a small fastapi-or-axum service with:
- postgres + a `leads`, `buyers`, `bids`, `posts`, `webhook_deliveries` schema
- redis for the parallel-ping fan-out + bid window timer
- per-buyer filter dsl (jsonlogic or cel-go)
- signed webhook posts with retries (use river queue in go or arq in python)
- borrow the bid-auction fan-out semantics from prebid.js/openrtb
this is ~2-3 weeks of focused work for someone with your background and is the actual moat of the business. don't waste cycles looking for a fork that doesn't exist.

### the agpl/copyleft cluster
this matters because you're a senior eng who will inevitably modify these. agpl-3.0 obligations only trigger when you *distribute* OR run a *modified* version that outside users (buyers logging into a portal counts!) interact with over the network. mitigation:
- **twenty crm**: if your buyers log into your fork's UI to claim leads → agpl triggers → you must offer them your modified source. solutions: (a) keep modifications minimal and use plugins/apps (twenty's app sdk is designed for this), (b) only let buyers receive webhooks/api calls (no UI access), or (c) buy commercial license from twenty.
- **formbricks**: the public form widgets/sdks (`packages/js`) are mit. the dashboard is agpl. you'll embed the mit widget on landing pages — fine. dashboard is internal-only — fine.
- **listmonk, plausible, mautic**: internal-only use, no agpl trigger.
- **ultralytics yolov8/v11**: this is the worst one. agpl applies to the *model weights and inference code* if you serve predictions over the network. for storm-damage classification, fork to **`facebookresearch/detectron2`** (apache-2.0), **`open-mmlab/mmdetection`** (apache-2.0), or use **`microsoft/Florence-2`** (mit) / **`hustvl/yolop`** family with permissive licenses. or train on yolov5 (still gpl-3.0 with an exception), or pay for an ultralytics commercial license (~$1k/yr/seat).

---

## Details — recommended forks per layer

### 1. storm / disaster ingestion
**primary**: `https://github.com/tropycal/tropycal` — 1k+ stars, mit, actively maintained python lib that reads nhc best-track, hurdat2, ibtracs, and live operational forecasts (cone, advisories, discussions) into a unified format. has wind-swath plotting hooks you'll use to clip against zips/parcels with geopandas.

**augment with**:
- `https://github.com/zebpalmer/WeatherAlerts` (33 stars, mit) — fork it, the project hasn't been touched since 2017 but the cap-feed parsing logic is correct. ~a weekend to port to modern python and add async polling.
- `https://github.com/palewire/atcf-data-parser` — mit, clean cli for atcf a-deck/b-deck files (forecast guidance from gfdl/hwrf/gfs).
- `https://github.com/FEMA/openfema-samples` (public domain) — don't fork the lib, just consume the api directly. the disaster declarations summaries v2 endpoint is your "did this trigger a fema event" flag for buyer pricing.
- `https://github.com/simonw/pge-outages` (mit) — copy the **git-scraping pattern** (github actions cron pulling json into commit history) and apply it to every utility outage page in your target regions. zero infra.
- `https://github.com/GateHouseMedia/power-outages` (gnews, license unclear in repo header — verify before forking) — multi-utility scraper template.

**geospatial intersection**: skip looking for a fork. just `geopandas` + `shapely` in python, or `geo`/`geozero` crates in rust if you want it fast. the wind-swath × parcel intersection is ~50 lines of code.

**what to customize**: build a single `event_detector` service that consumes all of the above and emits a normalized `storm_event` json with `(geometry, severity, fema_eligible, customers_out, source, observed_at)`. that's your trigger primitive.

**wsl2/proxmox**: trivial — pure python, postgres+postgis. on proxmox put it in an lxc with 2gb ram.
**time to mvp**: 1 week.

---

### 2. programmatic seo / landing pages
**primary**: `https://github.com/agamm/pseo-next` — small repo but clean, mit, next 13+ app router with isr, sitemaps via next-sitemap, json-ld, variant routing (`/{vertical}/{slug}`). exactly the (city × service × storm) page pattern you want.

**also check**: `https://github.com/aifa-agi/aifa-v2.1` (mit) — bigger, has parallel routes for static seo pages + dynamic ai overlays. heavier lift to strip down.

**don't fork** the various `next-seo` libs as starting points — they're plugins, not templates.

**what to customize**: 
- replace the mock data fetcher with a query against your postgres `(city, county, zip, service, latest_storm_event)` view
- llm-generate page bodies offline (claude or local llama) into a `pages` table; render statically via isr
- add internal linking by clustering pages on city/county/zip
- ship 5,000-50,000 pages on day one

**wsl2/proxmox**: next.js builds well in wsl2; production runs as a node process behind nginx in coolify or a `caprover`/`coolify` deploy.
**time to mvp**: 1 week to fork+populate, ongoing content tuning.

---

### 3. lead capture forms & tcpa-style consent
**primary**: `https://github.com/formbricks/formbricks` — ~12k stars, **agpl-3.0 with paid enterprise files in `/apps/web/modules/ee`**. next.js + postgres, embeddable widget package is mit. survey/in-app/link forms, conditional logic, webhooks.

⚠️ **gotcha**: as of v3.0 they pulled sso/oidc out of community → enterprise. since you're solo, you don't need sso, so the agpl edition is fine. flag if you ever onboard a team.

**alternatives if agpl scares you**: `https://github.com/JhumanJ/OpnForm` (agpl too — same problem), `https://github.com/SurveyJS/survey-library` (mit but library-only, no backend).

**tcpa consent capture**: there is no open-source trustedform/jornaya equivalent. roll your own:
- record (ip, user_agent, page_url, page_html_hash, click_xy, consent_text, timestamp_utc, session_replay_url) at form submit
- screenshot the page server-side via playwright at submit time, hash + push to s3/minio
- self-host session replay with `https://github.com/rrweb-io/rrweb` (mit) or hook posthog session replay
this is the "self-hosted trustedform" pattern — record an immutable audit trail per submission. ~3 days work.

**bot mitigation**: skip hcaptcha — fork **`https://github.com/Altcha-org/altcha`** (mit), self-hosted proof-of-work captcha. no third-party calls. listmonk just adopted it. for fingerprinting, **`https://github.com/fingerprintjs/fingerprintjs`** has both mit (open-source v3) and a commercial pro version — the open-source one is enough for dedup.

**wsl2/proxmox**: docker compose, postgres dependency. fine in both.
**time to mvp**: 3-5 days (fork + custom consent fields + audit trail).

---

### 4. lead distribution / ping-post (build, don't fork)
**there is nothing forkable here.** every search returned closed saas. your stack:

```
fastapi or axum  →  postgres (leads, buyers, filters, bids, posts)
                →  redis streams (parallel ping fan-out, bid window timer)
                →  river (go) or arq (python) for webhook delivery + retries
                →  cel-go or jsonlogic-rs for buyer filter expressions
```

borrow patterns from:
- `https://github.com/prebid/Prebid.js` (apache-2.0) — header-bidding parallel auction logic and timeout handling
- `https://github.com/openrtb/openrtb` — request/response schemas
- `https://github.com/riverqueue/river` (mpl-2.0) — postgres-backed job queue, perfect for webhook delivery with retry+backoff
- `https://github.com/google/cel-go` (apache-2.0) — buyer filter dsl

write the multi-tenant buyer dashboard inside twenty crm as a "buyers" custom object + a few twenty apps that show bid stats. don't build a separate ui.

**time to mvp**: 2-3 weeks for a working ping-post engine. this is the highest-leverage thing you'll build.

---

### 5. telephony / voice / sms
**primary**: `https://github.com/jambonz` (organization) — mit, all repos public, full self-hosted twilio replacement built on drachtio/freeswitch. multi-tenant cpaas, webhook-driven call control via jambonz application json, byo sip trunks, byo speech (deepgram/azure/elevenlabs/local). eat the twilio bill.

key repos in the org to clone together:
- `jambonz/jambonz-api-server` — rest api
- `jambonz/jambonz-feature-server` — call control
- `jambonz/sbc-sip` and `jambonz/sbc-rtpengine` — sbc + media
- `jambonz/jambonz-webapp` — admin ui
- `jambonz/simple-voice-agent` — fork target for ai-driven outbound calls
- `jambonz/mcp-server` — exposes call control to mcp clients (use this to let claude/agents place calls)

**voice ai pipeline (the brain on top of jambonz)**: choose one:
- `https://github.com/pipecat-ai/pipecat` (~10k stars, bsd-2, python) — most flexible, transport-agnostic, great for outbound dialer agents
- `https://github.com/livekit/agents` (~10k stars, apache-2.0) — webrtc-first, lower latency, has a built-in test/judge framework
- pick **pipecat** if you're going to mostly do outbound phone calls via sip + plivo/jambonz; pick **livekit/agents** if you want browser-based "click to talk to agent" widgets too.

**sms gateway**: 
- `https://github.com/somleng/somleng` (mit) — full twilio-rest-api-compatible open-source implementation
- `https://github.com/android-sms-gateway/server` (apache-2.0) — bridge a rack of cheap android phones with sims to handle a2p volume without 10dlc registration nightmares (cheap deliverability for early days; not compliant at scale)
- for proper a2p 10dlc you still need a carrier — bandwidth.com or telnyx. use jambonz to talk to them, don't pay twilio's markup.

**call tracking (callrail alternative)**: jambonz already has cdrs. add a thin "tracking number → source → destination" mapping table and you have callrail. no fork needed.

**wsl2 reality**: do NOT try to run jambonz in wsl2. udp/rtp + sip alg + nat all break. install jambonz directly on a hetzner dedicated server (their official docker compose works on a single ax41-nvme). use wsl2 only for the application code that *talks to* jambonz over its rest api.

**time to mvp**: jambonz core install on hetzner = 1 day. first ai outbound dialer agent = 1 week.

---

### 6. crm / buyer management
**primary**: `https://github.com/twentyhq/twenty` — ~44k stars, **agpl-3.0 with /enterprise files marked `@license Enterprise`**. typescript/react/nestjs/postgres/graphql. extension framework via `npx create-twenty-app` lets you ship custom objects (deals → leads, companies → buyers), server-side logic functions, react components, agents, and views without forking the core. native mcp server.

⚠️ **agpl gotcha**: outside users (your buyers) hitting your modified ui → must publish modifications. workaround: only let buyers interact via webhooks/api or a separate non-twenty buyer portal you build, and run twenty as your *internal* admin tool.

**alternatives**:
- `https://github.com/mautic/mautic` — gpl, php/symfony, much older, much heavier. better for marketing automation (drip emails, lead scoring, campaigns) than as your primary crm. run it alongside twenty if you do email nurture.
- `https://github.com/EspoCRM/espocrm` (gpl-3.0) — solid mature php crm, clunkier ui.
- `https://github.com/krayin/laravel-crm` (mit!) — much less popular but mit is friendlier if you ever want to multi-tenant resell.

**recommendation**: twenty for buyer/lead crm, mautic only if you actually need drip campaigns to homeowners. don't run both day one.

**wsl2/proxmox**: twenty is docker compose, runs fine in wsl2 dev. on proxmox, put postgres in its own lxc with zfs.
**time to mvp**: 1-2 days fork+populate + 1 week of custom objects/workflows.

---

### 7. agent orchestration / self-improving agents
**primary mega-fork**: `https://github.com/kortix-ai/suna` — apache-2.0. this is the closest thing to a "company-in-a-box agent os" on github right now. python/fastapi backend + nextjs frontend + isolated docker sandbox per agent + supabase + redis + qstash + 60+ skills + 3000+ integrations + cron triggers + webhook triggers + multi-channel (slack/telegram/sms/web). literally designed for "agents running 24/7 on a hetzner box."

if you only fork one repo from this whole list, fork suna. it gives you the agent runtime, ui, storage, sandboxing, scheduling, and observability in one shot.

**self-improvement loop on top**: `https://github.com/NousResearch/hermes-agent-self-evolution` — 2.3k stars, mit, dspy+gepa pipeline that mutates skills/prompts/tool descriptions, evaluates against execution traces, and opens prs against your agent repo. ~$2-10 per optimization run via api. iclr 2026 oral. wire this on a weekly cron against your suna agents.

**memory layer**: `https://github.com/letta-ai/letta` (~20k, apache-2.0) — postgres-backed long-term memory blocks (the rebrand of memgpt). drop in for agents that need to remember buyer preferences, past leads, prior conversations across months.

**workflow glue**: 
- `https://github.com/n8n-io/n8n` — ⚠️ **"sustainable use license" — NOT open source by osi definition.** free for internal use, can't resell as a service. for a single-operator business it's fine but flag for any agency/multi-tenant play. 600+ pre-built lead-gen workflow templates.
- alternative if you want pure mit: `https://github.com/windmill-labs/windmill` (agpl with mit-licensed cli) or `https://github.com/dagster-io/dagster` (apache-2.0, more code-first).

**other agent frameworks worth knowing (not "fork the whole thing"; use as libraries inside suna)**:
- `https://github.com/langchain-ai/langgraph` (mit) — best for stateful, cyclical, production agent flows
- `https://github.com/crewAIInc/crewAI` (mit, ~40k stars) — role-based multi-agent for linear workflows
- `https://github.com/huggingface/smolagents` (apache-2.0) — ~1k loc, code-first agents, perfect for embedded use
- `https://github.com/pydantic/pydantic-ai` (mit) — type-safe agents, great if you want strict contracts

**ide-style agents (skip for backend; useful for your own dev loop)**:
- `https://github.com/OpenHands/OpenHands` (mit core, source-available enterprise) — autonomous coding agent
- `https://github.com/NousResearch/hermes-agent` (mit) — personal cli agent with skill learning

**low-code llm builder (only if you want a visual layer for non-technical helpers)**:
- `https://github.com/langflow-ai/langflow` (mit)
- `https://github.com/langgenius/dify` (~90k stars, apache-2.0 with a "no multi-tenant resale" clause — read the license file)
- `https://github.com/FlowiseAI/Flowise` (apache-2.0; multi-user gated to enterprise)

**mcp ecosystem**: `https://github.com/modelcontextprotocol/servers` (mit) — anthropic's reference. clone for the patterns. for your use case the `git`, `filesystem`, `memory`, `fetch`, and `postgres` reference servers + `jambonz/mcp-server` + `twenty`'s native mcp give you 80% of what you need.

**wsl2/proxmox**: suna runs cleanly in docker compose on both. give the sandbox host 8gb+ ram. on proxmox use a vm (not lxc) for the suna sandbox because docker-in-docker behaves better in a vm.
**time to mvp**: suna up and talking to claude = 1 day. first end-to-end agent (storm event → pseo refresh → outbound dial) = 2 weeks.

---

### 8. web scraping / property data
**primary**: `https://github.com/unclecode/crawl4ai` — apache-2.0, ~50k+ stars, llm-first crawler, ships a docker image with a playground + monitoring dashboard at `:11235`. fork only if you need custom extractors; otherwise just `docker run` it.

**plus**: `https://github.com/browser-use/browser-use` — mit, ~75k stars, the agent-driven browser automation library. uses playwright. great for scraping county assessor sites, atom data sources, etc. that don't have apis. ⚠️ runs chrome → 1-2gb ram per agent → on proxmox give it its own vm.

**parcel/property data without paying attom/regrid**:
- `https://github.com/openaddresses/openaddresses` (varies by source, mostly cc-0/odbl) — addresses worldwide
- `https://github.com/microsoft/USBuildingFootprints` (odbl) — 130m us building polygons
- arcgis open data + each county's open gis portal — scrape with crawl4ai
- osm extracts via geofabrik

build a `parcels` postgis table once, never pay attom.

**other**:
- `https://github.com/mendableai/firecrawl` (mit + commercial) — self-hostable but the self-host story is weaker than crawl4ai
- `https://github.com/scrapy/scrapy` (bsd-3) — old reliable for high-volume structured scraping

**wsl2/proxmox**: crawl4ai docker works perfectly in both. browser-use needs more ram in wsl2 (set `.wslconfig` memory=8gb).

---

### 9. computer vision for tree damage
the open-source tree-damage-classification problem is partially solved but watch licenses.

**dataset & weights**:
- `https://github.com/RSandAI/VHRTrees` — published tree-detection dataset + yolov5/v7/v8/v9 baselines for satellite imagery (1471 images, 25k trees)
- `https://github.com/oracl4/RoadDamageDetection` — yolov8 streamlit app, license check needed
- roboflow universe has ~50 free storm-damage / tree datasets — search "tree damage" "fallen tree" "storm debris"

**model fork target**: AVOID `ultralytics/ultralytics` (yolov8/v11) for production — agpl-3.0 means your inference api would need to be open-sourced if you serve buyers. instead:
- `https://github.com/facebookresearch/detectron2` (apache-2.0) — mature, slower training but commercially permissive
- `https://github.com/microsoft/Florence-2` (mit) — multimodal vlm, can do "is there storm damage in this image" zero-shot, no fine-tune needed
- `https://github.com/haotian-liu/LLaVA` (apache-2.0) — multimodal alternative to claude vision, run locally

**recommendation**: start with florence-2 or llava + a prompt ("classify storm damage severity 0-3 and presence of fallen trees"). only train your own yolo if precision/recall matters at scale, and use detectron2 not ultralytics.

---

### 10. infrastructure / hetzner+proxmox port
**paas**: `https://github.com/coollabsio/coolify` — apache-2.0, ~50k stars. the fork-target for self-hosted heroku/vercel. one-line install on a hetzner box, then deploy all your apps from github with auto ssl. supports multiple servers via ssh. 280+ one-click templates including supabase, plausible, n8n, listmonk, etc.

alternatives: `https://github.com/dokploy/dokploy` (cleaner ui, ~24k stars, mit) — pick this if you prefer dockerfile-native workflows over coolify's bigger template library.

**email send (transactional + bulk)**:
- `https://github.com/mailcow/mailcow-dockerized` — mostly mit, full mail server in containers (postfix/dovecot/sogo/rspamd). run on a separate hetzner box with clean ip + rdns + dkim/spf/dmarc.
- `https://github.com/postalserver/postal` (mit) — postmark/sendgrid alternative, built for transactional volume.
- `https://github.com/knadh/listmonk` — agpl-3.0, single go binary + postgres, for newsletters and mass campaigns. uses your mailcow/postal as smtp relay.

⚠️ hetzner blocks port 25 outbound by default on new accounts. submit a ticket, give them a real reason, and they'll unblock for clean addresses. otherwise relay through ses/postmark/mailgun.

**analytics**:
- `https://github.com/umami-software/umami` (mit) — pick this. simple, mit license safe to modify, postgres-backed.
- skip plausible (agpl) and posthog (mit but self-host is community-build only and they push you to cloud).

**observability**: standard grafana + prometheus + loki stack; nothing to fork, just `docker compose up`. add `grafana/tempo` for distributed traces if you instrument your ping-post engine with otel.

**proxmox layout suggestion** (one ax41-nvme or ax52, 64gb ram):
- lxc 1: postgres + redis (zfs storage)
- lxc 2: twenty crm
- lxc 3: pseo next.js + nginx
- lxc 4: ping-post engine (the thing you're building)
- vm 1: suna agent stack (docker-in-docker prefers vm)
- vm 2: jambonz stack (sip/rtp prefers vm with bridged network)
- lxc 5: mailcow + listmonk + postal
- lxc 6: crawl4ai + browser-use (high ram, isolated)
- lxc 7: coolify + traefik + grafana stack

snapshot weekly to a hetzner storage box. ~€80/month total.

---

### 11. multi-tenant saas starter (for the buyer portal you'll build on top of the ping-post engine)
**primary**: `https://github.com/Razikus/supabase-nextjs-template` — apache-2.0, next.js 15 + supabase, has a multi-org/rbac/paddle paid variant.

alternatives:
- `https://github.com/Saas-Starter-Kit/Saas-Kit-supabase` (open core)
- vercel's b2b multi-tenant starter (mit) — middleware-based subdomain routing
- makerkit / supastarter — paid commercial templates, not forkable

self-host supabase via `https://github.com/supabase/supabase/tree/master/docker` (apache-2.0).

---

## Recommendations — the "clone today" stack

clone these on day one. spend the first weekend wiring them together. nothing else.

### the 9-repo opening move

1. **agent backbone** — `git clone https://github.com/kortix-ai/suna` (apache-2.0)
2. **self-evolution loop** — `git clone https://github.com/NousResearch/hermes-agent-self-evolution` (mit) — wire to suna once it's running
3. **crm** — `git clone https://github.com/twentyhq/twenty` (agpl, internal-only) — keep buyers out of the ui, give them api/webhooks instead
4. **landing pages** — `git clone https://github.com/agamm/pseo-next` (mit) — point at your postgres, generate 10k pages
5. **forms** — `git clone https://github.com/formbricks/formbricks` (agpl + EE) — only embed the mit `packages/js` widget on landing pages, dashboard internal
6. **telephony** — `git clone https://github.com/jambonz/jambonz-api-server` + `jambonz-feature-server` + `sbc-sip` + `sbc-rtpengine` + `simple-voice-agent` (all mit) — install on dedicated hetzner box, NOT in wsl2
7. **voice ai** — `git clone https://github.com/pipecat-ai/pipecat` (bsd-2) — the brain of your outbound dialer
8. **scraper** — `docker pull unclecode/crawl4ai:latest` (apache-2.0) — no fork, just run it
9. **paas** — `curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash` on hetzner (apache-2.0) — one-line install

### the thing you build (no fork)
**ping-post engine** in rust (axum) or go (chi/echo) — postgres + redis + river queue + cel-go for filters. this is your moat. budget 2-3 weeks.

### data ingestion (libraries, not forks)
- `pip install tropycal` for nhc data
- fork `zebpalmer/WeatherAlerts` and modernize for cap alerts (weekend project)
- consume openfema api directly with the patterns from `FEMA/openfema-samples`
- copy the git-scraping pattern from `simonw/pge-outages` into a github repo per utility you care about

### integration plan (wiring it together)
```
storm event detector (python, postgis)
   │ emits storm_event
   ▼
suna agent (custom skill: "trigger_lead_campaign")
   │ writes to twenty crm + triggers pseo refresh
   ▼
pseo-next (next.js isr) ◄── postgres pages table
   │ landing pages live with ranked geo+keyword content
   ▼
formbricks widget submits   ─►  consent audit logger (rrweb + s3)
                               │
                               ▼
                          ping-post engine (you build this)
                               │ parallel pings ─► buyer webhooks
                               ▼
                          twenty crm "leads" object
                               │
                               ▼
                          pipecat agent on jambonz dials buyer
                               │
                               ▼
                          mautic/listmonk drip if no answer
```

### what to ignore for now
- yolo/computer vision — start with florence-2 prompts before training anything
- mcp-everything — install only the mcps you actually use (postgres, fetch, jambonz, twenty)
- langflow/dify/flowise — suna already does this; pick one only if you want a visual layer for non-coders
- multi-tenant saas starter — premature; build it after you have 3+ buyers
- mautic — premature; do drip emails inside listmonk or twenty workflows first

### benchmarks that change the recommendations
- if you onboard a co-founder or contractor: revisit twenty crm agpl exposure
- if you cross 10k inbound calls/day: jambonz needs hetzner ax102 or sb cluster, not ax41
- if you're going to resell the platform to other contractors as multi-tenant saas: rip out twenty (agpl) for an mit crm (krayin or build minimal), rip out formbricks dashboard, rip out n8n if you adopted it, audit dify license clause
- if claude api costs exceed $2k/mo: self-host llama-3.3-70b on a hetzner gpu box (gex44) and route via litellm

---

## Caveats

- **license claims**: i verified mit/apache for jambonz, suna, twenty (agpl-3.0+EE), formbricks (agpl-3.0+EE), listmonk (agpl-3.0), pseo-next, browser-use, crawl4ai, coolify, hermes-agent-self-evolution, letta, smolagents, pipecat, livekit/agents, and the modelcontextprotocol/servers repo. for any borderline-licensed repo (n8n's "sustainable use license", dify's no-resale clause, ultralytics agpl, mautic gpl), read the LICENSE file in the actual repo before shipping — these change. some repos like `GateHouseMedia/power-outages` had no clear license header in the search results; verify before forking.
- **star counts**: the figures here are approximate and rounded — github stars move daily and search results sometimes return cached/stale numbers. don't pick a tool based on stars alone; recency of last commit matters more.
- **repo name changes**: openhands moved from `All-Hands-AI/OpenHands` to `OpenHands/OpenHands` recently. danswer was renamed to onyx (`onyx-dot-app/onyx`). memgpt was renamed to letta (`letta-ai/letta`). github redirects work but bookmark the new urls.
- **wsl2 limitations**: anything involving real-time udp media (jambonz/freeswitch/sip), heavy chrome instances, or kvm-nested virt will frustrate you in wsl2. dev application logic in wsl2, run media servers on the hetzner box from day one, and use `mirrored` networking mode in `.wslconfig` if you need lan access during dev.
- **hermes-agent**: nous research released this around late 2025 / early 2026; it's newer and less battle-tested than suna. the self-evolution repo is a research project — useful, but treat its prompt mutations as "agent suggestions for human review", not full automation, until you've seen it not regress your agents.
- **the "fully automated" honest take**: nothing on github gives you end-to-end autonomous storm-chase tree-removal lead-gen out of the box. the ~8-12 fork stack above gets you to ~70% automated. the last 30% — the ping-post engine, tcpa audit trail, geospatial event detector, and the outbound voice agent script tuning — is bespoke work. that's also the moat. anyone who tells you a single repo solves this is selling something.
- **agpl vs internal use**: i've stated the practical interpretation throughout, but i'm not your lawyer. if this business gets real revenue, spend $500 on an actual oss licensing attorney for a one-hour review of your fork strategy. cheap insurance.
- **tcpa is real**: storm-chase tree-removal leads target post-disaster homeowners in distressed states. tcpa, telemarketing sales rule, dnc, and state-level anti-storm-chasing statutes (florida, texas, north carolina especially) all apply. open-source tooling captures consent; it doesn't make consent legal. lawyer up before the first call.