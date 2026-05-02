# deep audit: 28 repos for the storm-chase / tree-removal agentic stack

## tl;dr

- **the stack mostly works, but four things will eat your weekend**: (1) suna's agent loop is welded to supabase + daytona + qstash and ripping it out is a multi-day rewrite; (2) hatchet has no official rust sdk, only an unofficial `eswolinsky3241/hatchet-rust-sdk` (your axum service must use http/grpc or a go sidecar); (3) the claude agent sdk's bundled `claude` cli **ignores `ANTHROPIC_BASE_URL`** — you must pin `cli_path=shutil.which("claude")` to actually route through litellm; (4) the reference `@modelcontextprotocol/server-postgres` is **archived, read-only, and has a known sql-injection bypass** — do not use it, use `crystaldba/postgres-mcp-pro` or zed's fork.
- **license traps to read before you commit**: twenty has `/* @license Enterprise */` markers inside otherwise-agpl files (sso is one of them — production use without a commercial key is a violation); formbricks gates `/apps/web/modules/ee/` with a separate ee license while `/packages/js` is mit; n8n is sustainable use license (no resale, no charging users for access); dify has an explicit `multi-tenant saas` clause requiring written authorization; netbird flipped `management/`, `signal/`, `relay/` from bsd-3 to agpl-3 in v0.53.0 (aug 2025) — the binaries you self-host are now agpl.
- **the recent litellm supply-chain compromise (1.82.7/1.82.8, march 2026) is still a live concern**: pin to `1.82.6` or `>=1.83.0`, use the official docker image (not pypi), and verify with cosign. crawl4ai already cut over to `unclecode-litellm` in v0.8.6 because of this.

---

## key findings

### the per-repo verdict table

| # | repo | claimed features | license verified | last commit signal | fork-target risk (1=safe, 10=fragile) | notes |
|---|---|---|---|---|---|---|
| 1 | kortix-ai/suna | partial | apache-2.0 | very active (~daily, 19.6k stars, 3 named maintainers) | **8** | hard-bound to cloud supabase + daytona + qstash + redis + rabbitmq; "local supabase + docker" is a known unsupported config (issue #1920, marko kraemer himself). agent loop lives in `backend/agent/run.py:1-337`, jwt validated against supabase in `backend/core/utils/auth_utils.py:41-89`. dramatiq workers on rabbitmq. ripping out supabase auth is real work. |
| 2 | hatchet-dev/hatchet | yes | mit (`hatchet/LICENSE`) | very active, vc-backed, ~4 person team | **3** | postgres-only, confirmed in repo. official sdks: go, python, typescript (`@hatchet-dev/typescript-sdk` v1.21.0 published 10 days before this audit). **no official rust sdk** — `crates.io/hatchet-sdk` is unofficial (`eswolinsky3241/hatchet-rust-sdk`). durable execution is real, not vapor. |
| 3 | jambonz/* | yes | mit (org-wide) | active, commercial backing (jambonz.io) | **4** | full stack: drachtio sip server + freeswitch + rtpengine + mysql + redis + influx + grafana + homer. STIR/SHAKEN verstat passthrough is in the feature server (verstat header parsing). audio bridge to ai is the **`listen` verb over websocket subprotocol `audio.jambonz.org`**, 16-bit linear pcm binary frames, json control frames. telnyx/bandwidth integration is "configure a sip trunk" — works fine, not a custom integration. |
| 4 | pipecat-ai/pipecat | yes | bsd-2 | very active, daily.co backing | **3** | transports: daily (webrtc), livekit, fastapi-websocket, smallwebrtc, websocket-server, whatsapp, local. service integrations confirmed for anthropic, openai, deepgram, elevenlabs, cartesia, etc. as optional extras in `pyproject.toml` (`Provides-Extra: anthropic, deepgram, elevenlabs, ...`). |
| 5 | anthropics/claude-agent-sdk-python + ts | partial | mit | active, anthropic-maintained | **5** | `query()` and `ClaudeSDKClient` work. tool use, mcp servers, hooks all real (`src/claude_agent_sdk/client.py`). **the bundled cli (auto-installed) silently ignores `ANTHROPIC_BASE_URL`** — open issue #677. workaround: `ClaudeAgentOptions(cli_path=shutil.which("claude"), env={"ANTHROPIC_BASE_URL": ...})`. branding: anthropic commercial tos, not pure mit-permissive use. |
| 6 | BerriAI/litellm | yes (with caveats) | mit | active but **march 2026 supply-chain incident** | **7** | proxy in `litellm/proxy/proxy_server.py`, postgres-backed virtual keys + budgets work. **versions 1.82.7 and 1.82.8 contained a credential-stealing payload** (CVE-tracked, cosign signing introduced in v1.83.0). use docker image only, pin sha. claude agent sdk integration documented and works (modulo the cli bug above). |
| 7 | NousResearch/hermes-agent-self-evolution | yes (research-quality) | mit | nous research-maintained, real | **6** | actually a working dspy + gepa pipeline, not vaporware. requires `NousResearch/hermes-agent` to be installed/cloned. operates by api calls only (no gpu training). it outputs PRs against hermes-agent. **it is not generic** — to point it at suna or your own runtime, you'd be rewriting the eval harness. |
| 8 | twentyhq/twenty | partial | **agpl-3.0 + enterprise license** | very active | **8** | `LICENSE` file says: *"certain files are clearly marked with `/* @license Enterprise */` ... files with this comment are not licensed under the agpl v3"*. sso (oidc/saml) is one of those files. graphql + rest apis exist (`/api/graphql`), api key auth via bearer token, but **the in-app playground generates queries the api refuses** (issue #12991). custom objects api works (`createOneObject`, `createOneField`). there is no native oidc forward-auth integration — auth is bearer-token api keys only for external systems. |
| 9 | formbricks/formbricks | yes | **agpl-3 + ee + mit (split)** | active | **6** | top-level `LICENSE` carves out three zones: `/apps/web/modules/ee/` is **enterprise license** (sso, advanced rbac), `/packages/js`, `/packages/android`, `/packages/ios`, `/packages/api` are **mit**, everything else is agpl-3. webhooks fully supported, signed with **standard webhooks format** (`whsec_` prefix, hmac-sha256, 5-min tolerance window). docker images include ee code but require a license key to unlock. ssrf-protection blocks private-ip webhook urls by default — flip via env var if your ping-post collector is internal. |
| 10 | agamm/pseo-next | partial | mit | **abandoned** (last meaningful commit 2023) | **9** | next 13, prisma, vercel-targeted. isr support is real (`revalidate` in `getStaticProps`), but the readme says "remember to uncomment the comments there to actually fetch from your db" — you are wiring db integration yourself. treat this as a starter snippet, not a maintained project. |
| 11 | unclecode/crawl4ai | yes | apache-2.0 (with attribution req) | very active, 50k+ stars | **5** | docker exposes `/playground` and `/dashboard` on port 11235, llm extraction in `crawl4ai/extraction_strategy.py`, async api is genuinely async (playwright-driven). v0.8.6 (recent) **replaced litellm with `unclecode-litellm`** to dodge the supply-chain attack. dependency footprint is heavy (playwright, torch optional). |
| 12 | letta-ai/letta | yes | apache-2.0 | very active | **4** | postgres + pgvector backend (`pgvector/pgvector:pg16` is the recommended db image), rest api on `:8283`, python + typescript sdks. memgpt → letta rename is not a paywall — same code, same capabilities. external db is supported (set `LETTA_PG_URI`). good service citizen for "agent calls letta for memory." |
| 13 | modelcontextprotocol/servers | partial | mit | active for *some* servers | **7** | the postgres reference server (`@modelcontextprotocol/server-postgres`) is **archived as of jul 10, 2025**, lives in `modelcontextprotocol/servers-archived`, and has a documented sql-injection bypass (datadog security labs, aug 2025): `COMMIT; DROP SCHEMA public CASCADE;` escapes the read-only transaction. fetch, filesystem, memory, git, time, sequentialthinking remain officially maintained. for postgres use **crystaldba/postgres-mcp-pro** (read+write, parameterized) or **`@zeddotdev/postgres-context-server`**. |
| 14 | langfuse/langfuse | yes | mit + ee files | very active | **3** | `docker-compose.yml` requires postgres + clickhouse + redis/valkey + s3-compatible blob store. **all three storage tiers are mandatory** (no postgres-only mode since v3 — explicitly rejected by the team in their architecture blog post). minimum prod sizing: 2 cpu / 4 gb per app container, 2 instances of langfuse-web. native oidc sso for authentik, okta, azure ad, keycloak, github, google all wired in `AUTH_<PROVIDER>_*` env vars. **timezone gotcha: postgres + clickhouse must be utc or queries return wrong/empty results.** |
| 15 | SigNoz/signoz | yes | **mit-expat + ee license** | very active | **5** | `LICENSE` says: *"all content that resides under the `ee/` and the `cmd/enterprise/` directory of this repository ... is licensed under the license defined in `ee/LICENSE`. content outside ... is available under the `mit expat` license."* the docker image ships with ee code; community edition has full traces+logs+metrics+apm in one app. **community edition has no oidc sso** — issue #1188 still open. minimum docker memory: **4 gb hard floor** (install script enforces), 8 gb recommended, 16 gb for production loads. clickhouse + zookeeper + postgres-for-metadata + signoz query service + otel collector. |
| 16 | caddyserver/caddy + corazawaf/coraza-caddy | yes | apache-2.0 (both) | both active | **3** | build with `xcaddy build --with github.com/corazawaf/coraza-caddy/v2`. caddyfile must include `{ order coraza_waf first }`. owasp crs loads via `load_owasp_crs` directive + `Include @owasp_crs/*.conf`. confirmed working in production deployments (juan pablo tosso's own elastic + caddy stack). performance overhead is real but in microseconds per request per the coraza benchmarks. |

### supporting repos

| # | repo | verdict | license | notes |
|---|---|---|---|---|
| 17 | openbao/openbao | real | mpl-2.0 | linux foundation governed, controlplane / ibm contributors; v2.5.0 (feb 2026) added namespaces + horizontal read scalability that were vault enterprise-only. drop-in api-compatible with vault `<= 1.14`. dr replication still missing. |
| 18 | netbirdio/netbird | watch the license | bsd-3 root + **agpl-3 for `management/`, `signal/`, `relay/`, `combined/`** since v0.53.0 (aug 2025) | client agents are still bsd-3. self-hosting the management plane is now agpl — fine for internal use, but if you white-label or resell you need the commercial license. |
| 19 | crowdsecurity/crowdsec | real | mit (engine) + mit (hub scenarios) | scenarios cover http brute-force, scanner detection, credential stuffing patterns, and form abuse via the `appsec` rule engine. bouncers integrate with caddy, nginx, iptables, cloudflare. the "community blocklist" is a centralized service — consider it telemetry-out. |
| 20 | cilium/tetragon | real | apache-2.0 | ebpf-based runtime security, isovalent-maintained, very active. policy yaml format is straightforward. needs kernel >= 5.4 with btf for full functionality. |
| 21 | seaweedfs/seaweedfs | real | apache-2.0 | s3 api compatibility is mature; works as drop-in for langfuse, signoz s3 archival, pgbackrest (langfuse/signoz both speak generic aws-sdk-style s3 — endpoint url override is enough). actively maintained, kubeflow pipelines adopted it as default. |
| 22 | nats-io/nats-server | real | apache-2.0 | jetstream is stable, persistent streams + key-value + object stores all production-ready. complements hatchet — nats for fire-and-forget event bus, hatchet for durable workflow state. they do not conflict architecturally. |
| 23 | timescale/timescaledb | real | apache-2.0 (community) | hypertables + continuous aggregates are in the apache version. compression, columnstore, and some advanced features are tsl (timescale community license). check `tsl/` directory before assuming. |
| 24 | pgvector/pgvector + timescale/pgvectorscale | real | postgresql license / **postgresql-style with tsl** for pgvectorscale | pgvector is solid, ubiquitous. pgvectorscale's streamingdiskann index is licensed under tsl ("timescale license") — free for use, not for offering as a managed service. |
| 25 | GlitchTip/glitchtip | yes (with gaps) | mit | sentry sdk compatibility for **errors**: solid. for **performance/tracing/replay/profiling**: mostly absent or experimental. cli is `glitchtip-cli` (sentry-cli moved to non-free). 4-container deploy (postgres + redis + web + worker). |
| 26 | langgenius/dify | watch the license | apache-2.0 + commercial restrictions in `LICENSE` | exact text from `dify/LICENSE`: *"a. multi-tenant service: unless explicitly authorized by dify in writing, you may not use the dify source code to operate a multi-tenant environment. tenant definition: within the context of dify, one tenant corresponds to one workspace."* and *"b. logo and copyright information: in the process of using dify's frontend, you may not remove or modify the logo or copyright information in the dify console or applications."* — for the user's single-org use this is fine. **do not** white-label or run multiple customer workspaces. |
| 27 | n8n-io/n8n | watch the license | sustainable use license (sul-1.0) + ee files | exact restrictions from `n8n/LICENSE.md`: *"you may use or modify the software only for your own internal business purposes or for non-commercial or personal use. you may distribute the software or provide it to others only if you do so free of charge for non-commercial purposes."* and *"source code files that contain `.ee.` in their filename or `.ee` in their dirname are not licensed under the sustainable use license."* internal automation for the storm-chase business is fine. monetizing n8n workflows as a product is not. |
| 28 | microsoft/Florence-2 | real | mit (both code and weights) | confirmed in `huggingface.co/microsoft/Florence-2-large/blob/main/LICENSE`. inference example uses `AutoProcessor` + `AutoModelForCausalLM` with `trust_remote_code=True`. ~1.5 gb model, ~1 sec/image on a t4. ocr, captioning, detection, grounding, segmentation all in one. |

---

## integration risk register (a–i)

| # | integration | status | what breaks / workaround |
|---|---|---|---|
| **a** | hatchet ↔ rust axum service | ⚠️ **showstopper for "ergonomic" path** | no official rust sdk. options, ranked: (1) call hatchet's grpc api directly from axum (auth: bearer jwt, schema in `api-contracts/dispatcher.proto`); (2) use the unofficial `hatchet-sdk` crate from `eswolinsky3241/hatchet-rust-sdk` and accept maintenance risk; (3) write a tiny go or python sidecar that owns hatchet workers and exposes an http rpc to axum. **option 3 is the lowest-risk for production.** |
| **b** | claude agent sdk ↔ litellm proxy | ⚠️ **broken default, fixable** | the auto-bundled `claude` cli inside the python sdk silently ignores `ANTHROPIC_BASE_URL` (issue #677). fix: install claude code system-wide (`curl -fsSL https://claude.ai/install.sh \| bash`), then `ClaudeAgentOptions(cli_path=shutil.which("claude"), env={"ANTHROPIC_BASE_URL": "http://litellm:4000", "ANTHROPIC_AUTH_TOKEN": "<litellm-key>"})`. also gateway must implement `/v1/messages`, `/v1/messages/count_tokens`, and forward `anthropic-beta`, `anthropic-version` headers. litellm does. **subagents may still ignore the model env var** (issue #5680 in claude-code) — verify with a sub-agent test before relying on it. |
| **c** | jambonz ↔ pipecat | ⚠️ **no shipped bridge, but the protocol is documented** | jambonz exposes audio via the `listen` verb to a websocket using subprotocol `audio.jambonz.org`, sending 16-bit linear pcm binary frames + json control frames (`playAudio`, `killAudio`, `mark`, `disconnect`). pipecat has `WebSocketServerTransport` that accepts raw pcm frames. you write the adapter: a small fastapi/aiohttp ws server that translates jambonz's binary pcm + json control protocol into pipecat's `InputAudioRawFrame` / `OutputAudioRawFrame`. estimated effort: 1–2 days for a working e2e demo. reference impls: `jambonz/test-listen-server` and `sammachin/jambonz_audiosocket` show the wire format. |
| **d** | formbricks → postgres → ping-post | ✅ **works** | webhooks are first-class. configure in ui or via management api, signed with standard webhooks (`whsec_*`). default ssrf protection blocks `localhost`/private ranges — set the documented opt-out env var if your collector is internal. |
| **e** | twenty ↔ external lead creation | ✅ **works (with quirks)** | bearer-token api key auth, `mutation createOneObject` / `createOneField` work. **the playground generates wrong queries** (issue #12991) — write your mutations by hand or copy from network tab. there is **no native oidc** for the community edition; sso is `/* @license Enterprise */`. for headless lead ingestion, api keys are sufficient. |
| **f** | mcp postgres server (read+write) | ❌ **reference server is dead, use a fork** | `modelcontextprotocol/server-postgres` is **archived** (jul 2025), still gets 21k weekly npm downloads, contains a **sql-injection-style read-only bypass** (datadog research, cve-tracked). use `crystaldba/postgres-mcp-pro` (supports read+write with proper parameterization, npm `postgres-mcp`) or `@zeddotdev/postgres-context-server` (read-only, patched). create a least-privilege db role and don't expose to untrusted llm input either way. |
| **g** | nats jetstream ↔ hatchet | ✅ **complementary, not conflicting** | use nats jetstream for low-latency event fanout (storm radar feeds, sip events, formbricks webhooks coming in), and hatchet for durable, retryable, observable workflows (lead enrichment pipeline, voice call orchestration, billing). hatchet does not need an external broker — it uses postgres. nats-to-hatchet is a one-way push (nats consumer → hatchet `task.run()`). |
| **h** | seaweedfs s3 ↔ langfuse / signoz / pgbackrest | ✅ **drop-in works** | langfuse uses generic s3 sdk (`LANGFUSE_S3_*` env vars include `_ENDPOINT`, `_FORCE_PATH_STYLE`). signoz cold-storage is via clickhouse `s3` disk type. pgbackrest has explicit `repo1-s3-uri-style=path`. all three are happy with seaweedfs's s3 endpoint. one caveat: clickhouse on seaweedfs as a disk has caveats around versioning + lifecycle policies (langfuse docs warn explicitly). |
| **i** | authentik forward-auth ↔ apps | 🟡 **uneven** | **langfuse**: yes, native oidc, dedicated `AUTH_AUTHENTIK_*` env vars, even has authorization-url override for split-dns. **twenty**: no — community edition is api-key + email/password only; sso lives in `/* @license Enterprise */` files. **formbricks**: sso is in `/apps/web/modules/ee/` — paid ee license. **signoz**: no oidc in community (issue #1188 still open). **letta**: api-key + `LETTA_SERVER_PASSWORD` only, no oidc. **hatchet**: oidc/oauth supported but config is sparse. **plan accordingly**: put twenty/formbricks/signoz behind authentik **proxy provider** (header auth) instead of expecting native oidc. |

---

## the "this won't actually work" list

things that, if assumed in the prior plan, will eat hours:

1. **"i'll just rip out supabase from suna"**: not a 1-day job. the agent loop in `backend/agent/run.py`, the auth layer in `backend/core/utils/auth_utils.py:41-89`, the realtime channels for streaming agent output, the basejump multi-tenancy schema, and the frontend's supabase-js dependency all ship together. plan ~3 days minimum, and you'll lose realtime streaming during the transition. **better: fork suna, keep cloud supabase as a hosted dependency for the agent runtime, and add your own postgres alongside for business data.** or skip suna and build the agent loop on the claude agent sdk + litellm directly — it's ~200 lines.
2. **"i'll write the axum service in rust and call hatchet from it"**: no first-party rust sdk. accept either the unofficial crate (one maintainer, 6 months of activity) or write a go sidecar that owns hatchet workers.
3. **"litellm proxy is fine, i'll `pip install litellm`"**: not in a fresh env you can't. pin to `1.82.6` or `>=1.83.0`, **use the official docker image** (`ghcr.io/berriai/litellm:main-stable`), and verify with cosign. the supply-chain attack credential-stole from any system where the bad versions ran. `pip install` is hot-radioactive for this package right now.
4. **"i'll point claude code / agent sdk at litellm and forget about it"**: bundled cli ignores `ANTHROPIC_BASE_URL`. workaround documented above.
5. **"the postgres mcp server lets the agent read crm data safely"**: the reference server is archived and exploitable. use postgres-mcp-pro or zed's fork, behind a read-only db role, behind a pgbouncer with statement-level rate limits.
6. **"twenty has sso so authentik forward-auth will just work"**: no, sso is enterprise-licensed. you either pay, run twenty behind authentik's proxy provider with header forwarding, or accept api-key auth for the human ui (which means twenty's own login screen).
7. **"formbricks free includes sso"**: no. sso lives in `/apps/web/modules/ee/`. for a single-operator / single-team self-hosted use, that's fine — basic auth suffices.
8. **"netbird is bsd-3 so commercial use is open"**: not anymore. `management/`, `signal/`, `relay/`, `combined/` are agpl-3 since v0.53.0 (aug 2025). client agents remain bsd-3. internal use is unaffected; reselling/saas-ifying netbird is a license event.
9. **"signoz community has oidc"**: it does not. issue #1188 has been open for years. either pay for ee (`$2500/month base`), put signoz behind authentik proxy auth, or accept local accounts.
10. **"langfuse self-hosted is just a docker container"**: not since v3. you must run postgres + clickhouse + redis + s3-compatible storage. clickhouse and postgres **must both be utc-tz** or queries silently return empty.
11. **"crawl4ai is just `pip install`"**: it pulls playwright + torch (optional) + a heavy graph of llm clients. budget ~2 gb of image. and yes, the docker variant works at `:11235/playground` as advertised.
12. **"pseo-next is a maintained template"**: it isn't. last meaningful commits in 2023, next 13 era, prisma stubs you have to wire yourself. treat it as a reference implementation, not a dependency.
13. **"jambonz + pipecat will plug together"**: no shared abstraction. you write the websocket adapter that speaks the `audio.jambonz.org` subprotocol on one side and feeds pipecat's frame pipeline on the other. ~1-2 days.
14. **"hermes-agent-self-evolution is generic prompt evolution"**: it's specifically wired to evolve `NousResearch/hermes-agent`'s skills/tools/prompts. to use it on suna or your own runtime, you re-implement the eval harness. legitimate research code, not plug-and-play.
15. **"dify is fine for a small saas"**: read the license. multi-tenant operation requires written authorization. for your own single-org use, you're fine. for offering it to multiple storm-chase teams as a paid product, you need a commercial agreement.

---

## revised stack (where the audit changes the choice)

| layer | original assumption | revised choice | why |
|---|---|---|---|
| agent runtime | suna (self-hosted) | **claude agent sdk + litellm directly**, optionally with letta for memory; keep suna only if you want its ui out-of-the-box and tolerate cloud supabase | suna's supabase + daytona + qstash dependency stack is heavier than what you need for headless lead-gen agents. building the loop on the sdk is ~200 loc. |
| durable workflows from rust | hatchet rust sdk | **hatchet + thin go sidecar OR direct grpc from rust** | no official rust sdk. |
| llm gateway | `pip install litellm` | **`ghcr.io/berriai/litellm` docker, pinned by sha, cosign-verified, started post-1.83.0** | march 2026 supply-chain attack. |
| crm | twenty self-hosted with sso | **twenty self-hosted + authentik proxy auth (header forwarding)**, OR pay for twenty enterprise oidc | community sso is `@license Enterprise`. |
| forms | formbricks with sso | **formbricks community + authentik proxy auth in front** | sso is ee. webhook delivery + js widget are mit/agpl, fine. |
| postgres mcp | `@modelcontextprotocol/server-postgres` | **`crystaldba/postgres-mcp-pro` behind a read-only role and pgbouncer** | reference server is archived + exploitable. |
| voice ↔ ai bridge | "pipecat plugs into jambonz" | **bespoke fastapi ws adapter speaking jambonz's `audio.jambonz.org` protocol on one side, pipecat pipeline on the other** | no shipped integration. ~1-2 days to write. |
| programmatic seo | pseo-next template | **fork pseo-next or write fresh in next 14/15 with the same isr pattern** | abandoned since 2023. |
| object storage | minio | **seaweedfs** | minio went maintenance-mode dec 2025; seaweedfs is the lightest mature s3-compatible alternative, apache-2.0, plays nice with langfuse / pgbackrest / signoz s3 archival. |
| observability sso | "signoz has oidc" | **signoz behind authentik proxy auth, or oneuptime if you want native sso** | signoz community oidc has been open since 2022. |
| memory store | suna's memory | **letta as a sidecar service, called over rest from your agent loop** | letta is built for this; suna's memory is intertwined with supabase. |

---

## code-level surprises to know before writing the first line

- **suna's dramatiq workers depend on rabbitmq**, not just redis. the `docker-compose.yaml` brings up redis + rabbitmq + backend api + worker (`uv run dramatiq run_agent_background`) + frontend. if you skip rabbitmq, the worker silently fails to dequeue.
- **suna's `backend/core/services/supabase.py` is referenced from ~40 call sites** including auth, file storage, conversation history, project state. it is not a pluggable adapter — it's a concrete client.
- **hatchet's typescript sdk is `@hatchet-dev/typescript-sdk`** (npm), python is `hatchet-sdk` (pypi), go is `github.com/hatchet-dev/hatchet/pkg/v1`. none of these are interchangeable wrappers — each implements the grpc client natively. the rust ecosystem has only the unofficial crate.
- **jambonz `listen` verb supports bidirectional audio only when not nested in `dial`** — this matters if you want the ai to barge-in during a dialed call. work around with a separate `config` verb attaching the listen.
- **jambonz mysql schema has `accounts.registration_hook` per sip realm** — your auth http callback receives username, realm, nonce, response — you implement digest auth, jambonz doesn't store passwords.
- **pipecat's `WebSocketServerTransport` only supports one client at a time** ("if a new client connects while one is already connected, the existing connection will be closed" — pipecat docs). this is fine for one call per process; not fine if you want multi-tenant on a single transport.
- **claude agent sdk's `query()` is one-shot; `ClaudeSDKClient` is for bidirectional/streaming + custom tools + hooks**. mcp servers are in-process (when defined as python functions) or external (when spawned subprocess) — only the external ones are kill-on-disconnect.
- **claude code v2.1.126+ does gateway model discovery via `/v1/models`** — only models whose id starts with `claude` or `anthropic` show up in the picker. if your litellm config exposes `bedrock-claude-sonnet-4` it will appear; `gpt-4o` will not (use it via the api but not the picker).
- **litellm sets `LITELLM_ANTHROPIC_DISABLE_URL_SUFFIX=true` is needed if your custom base url already contains the full path** (otherwise litellm appends `/v1/messages` and double-paths).
- **twenty's graphql schema is generated per workspace** — your custom objects get their own mutations. the docs api playground generates queries that the api refuses (issue #12991) — copy from the network tab instead.
- **twenty's auth is jwt, not oidc, in the community edition**. authentik integration requires either ee or putting twenty behind authentik's proxy provider with `Authorization` header forwarding to twenty's existing login flow.
- **formbricks webhooks block private-ip urls by default** (ssrf protection). set the documented env var if your ping-post collector is on the same docker network.
- **langfuse postgres + clickhouse must both be utc**. non-utc returns wrong/empty results. they say so explicitly in their troubleshooting docs.
- **signoz install script enforces 4 gb min docker memory**. clickhouse alone wants 8+ gb for production loads.
- **caddy + coraza requires `{ order coraza_waf first }`** in the global caddyfile block, otherwise the waf runs after other handlers and is useless.
- **netbird's dashboard repo defaults to auth0 if you don't override `AUTHENTIK_*` env** — check `docker run -e AUTH0_DOMAIN=...` in the readme; you must point it at authentik or your own oidc.
- **letta's docker image bundles postgres+pgvector internally by default**; for production use external postgres via `LETTA_PG_URI=postgresql://...` env, otherwise the persistent volume is your only backup story.
- **florence-2 inference requires `trust_remote_code=True`** — model code is loaded from huggingface, not packaged in transformers. pin the revision sha.
- **pgvectorscale's streamingdiskann is tsl-licensed**, not apache. the `vector` index is fine; `diskann` is not for managed-saas resale.
- **n8n `.ee.` files in filename or `.ee` in dirname** are excluded from the sustainable use license — these contain advanced rbac, ldap, environments, audit logs, etc. do not redistribute.

---

## recommendations

### immediate (this weekend)

1. **set up the spine first**: caddy + coraza-caddy + crowdsec on the edge, openbao for secrets, postgres + timescale + pgvector + pgvectorscale (one cluster, schemas separate per app), seaweedfs for s3, nats for fanout. these are the lowest-risk choices and will not change.
2. **stand up langfuse v3 with seaweedfs as s3** behind authentik oidc — verify the seaweedfs↔langfuse path with a smoke test (a single trace + observation) before building anything else on it.
3. **stand up litellm proxy from the official docker image, pinned sha, cosign-verified**, with a yaml that exposes `claude-sonnet-4-5` and one fallback (openrouter or vllm). do **not** `pip install litellm` anywhere on the host.
4. **stand up hatchet (postgres-only) and run one toy workflow from a python sdk client**. then write a one-day spike of the go sidecar that hatchet workers live in, exposing http to your eventual rust axum service.

### week one

5. **decide on suna vs roll-your-own**: spend half a day reading `backend/agent/run.py`. if your agent's behavior is "tool-use loop + browser via daytona + file ops", you don't need suna — `claude_agent_sdk.ClaudeSDKClient` + a few mcp servers does it. if you need suna's ui for human-in-the-loop, accept cloud supabase.
6. **wire claude agent sdk → litellm** with the `cli_path` workaround. write a smoke test that verifies a query routes through litellm (check langfuse for the trace).
7. **stand up jambonz** with rtpengine + drachtio + freeswitch + mysql + redis. configure a telnyx sip trunk. write the websocket adapter from `audio.jambonz.org` to pipecat. demo: phone call → deepgram stt → claude → cartesia tts → caller hears response. budget 2 days.
8. **postgres mcp pro behind a read-only role**, exposed only to the agent runtime, never to a public-facing chat ui.

### week two

9. **twenty + formbricks + glitchtip** behind authentik proxy auth. accept that twenty's lead-creation flow is a graphql mutation called from your agent runtime, not a sso-aware ui.
10. **signoz** for traces+logs+metrics if you want one app; otherwise just stick with langfuse for llm + prometheus + grafana for infra. signoz has a real memory floor (8gb+) and no community sso.
11. **netbird** for the wireguard mesh between your hetzner nodes and operator laptops; understand the agpl-3 carve-out before you redistribute anything.

### thresholds that change the recommendation

- **if litellm publishes a clean post-incident retro with full ci/cd hardening (cosign + pep 740 attestations + branch-protected releases)** → safe to use litellm pypi again.
- **if hatchet ships an official rust sdk** → drop the go sidecar.
- **if anthropic merges issue #677** → drop the `cli_path` workaround.
- **if twenty open-sources oidc (the agpl camp keeps asking)** → drop the authentik proxy-auth shim.
- **if signoz adds community oidc (issue #1188 closes)** → use signoz with native sso.
- **if you need multi-tenant operation of dify or n8n or twenty for a paid product** → all three require commercial licenses; budget accordingly.

---

## caveats

- the may 2, 2026 search results include **future-dated material** (e.g., "2026-04-20 v2.5.3 release" of openbao, signoz repo activity dated apr 2026). where these dates are after today's audit window, i've used them as the most recent state from the project's own pages but flag that some of this is live. nothing changes the licensing or architectural conclusions.
- **license interpretations are not legal advice**. quoted clauses are pulled from the actual `LICENSE` files in each repo at the time of audit (twenty, formbricks, n8n, dify, signoz, netbird quotes are all verbatim from their `LICENSE`/`LICENSE.md` on github main). for go/no-go on commercial use, get a real lawyer.
- **the litellm supply-chain incident is recent and ongoing**. cosign signing infra was added in v1.83.0; older versions, including 1.82.6 (the recommended pin during the incident), are not signed. revisit before deploy.
- **suna**, **letta**, **hatchet**, **langfuse**, and **pipecat** are all **vc-backed startups**. they are healthy now; risk of license change in 18-24 months is non-zero. mitigation: pin a known-good sha, keep your own fork, and don't wire anything to their hosted offering as a hard dependency.
- **i did not run the code**. this audit is from reading the public repos, license files, docker-composes, sdk apis, recent issues, and the projects' own deep-dive docs (deepwiki, project blogs, official self-hosting guides). actual integration testing will turn up additional surprises — that's normal. the surprises listed above are the ones predictable from a code/doc read.
- **integration point a (rust ↔ hatchet)** has the highest unknown — the unofficial rust crate is recent enough that its behavior under load is unverified. budget time for this if you commit to rust for the axum service.
- **if you must run any version of litellm 1.82.7 or 1.82.8 was ever installed on a host**, treat all credentials on that host as compromised: rotate ssh keys, cloud creds, db passwords, api keys, k8s service account tokens. that includes ci runners.