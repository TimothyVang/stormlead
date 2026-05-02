# research

claude research artifacts that informed the scaffold's choices. the two `2026-05-*-audit.md` / `*-forkable-*.md` docs are preserved verbatim — what was true at audit time. `2026-05-stack-improvements.md` layers on verification + architectural critique and supersedes the older docs where they conflict.

## docs

- **`2026-05-stack-audit.md`** — *what tech to use and why we pinned what we pinned.* security/integration audit across ~28 candidate repos. drives: litellm sha-pin (post mar-2026 supply-chain incident), postgres-mcp-pro over the archived anthropic reference, hatchet for durable execution, coraza+caddy for the waf, langfuse v3 stack.

- **`2026-05-forkable-stack.md`** — *what to fork per layer and the agpl/license traps.* opinionated repo recommendations: tropycal/nws/fema for storm ingestion, formbricks for forms, twenty for crm, jambonz for telephony, pseo-next for landing, suna for the agent runtime, florence-2/detectron2 for vision (avoid ultralytics — agpl). flags agpl exposure on twenty + formbricks + ultralytics.

- **`2026-05-stack-improvements.md`** — *what changed since those docs were written, and what they don't address.* verification of time-sensitive claims (litellm cve, hatchet v1 rewrite, fcc one-to-one rule death) and a register of business-mechanics gaps neither prior doc covers (lead dedup, fraud scoring, buyer disputes, dnc scrub, billing). includes a sequenced action list.

## superseded claims (read `stack-improvements.md` for current truth)

- **litellm pin v1.83.4-stable** → **v1.83.7-stable** (cve-2026-42208).
- **hatchet v0.50.0 healthy** → legacy branch; v1 rewrite shipped mar 2025.
- **fcc one-to-one consent rule = primary tcpa threat** → rule is dead (vacated jan 2025, fcc abandoned aug/sep 2025); pre-2023 pewc standard restored.
- **`crystaldba/postgres-mcp:latest` ok** → pin a specific tag.
- **tropycal actively maintained** → snyk classifies "inactive" since early 2025.

## scaffold divergences from `forkable-stack.md` (deliberate)

- **no suna fork.** agent-runtime is direct on claude agent sdk + litellm (~200 loc target), no supabase. see top-level README.
- **ping-post is python (fastapi + hatchet), not rust/go.** rewrite the hot path later if/when we cross ~500 leads/sec sustained.
- **no coolify.** prod runs docker compose under systemd on hetzner.

## latent risks called out in `forkable-stack.md` (still active)

- **twenty crm = agpl-3.0.** if buyers ever hit a modified twenty ui, source-disclosure triggers. mitigate: keep buyers on api/webhooks, or buy commercial license.
- **formbricks v3+ moved sso/oidc to paid ee.** fine solo; flag if a team forms.
- **hetzner blocks port 25 outbound by default.** matters when email send lands.
- **ultralytics yolov8/v11 = agpl-3.0.** if vision is added, use florence-2 / detectron2 / llava — not ultralytics.
