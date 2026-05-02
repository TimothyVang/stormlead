# agent auth patterns — oauth subscription vs api key

## origin

i previously told the user that `CLAUDE_CODE_OAUTH_TOKEN` couldn't authenticate claude agent sdk agents, citing anthropic's policy line: *"unless previously approved, anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the claude agent sdk."*

the user pointed at https://github.com/coleam00/Linear-Coding-Agent-Harness — a public claude agent sdk demo authenticated via `CLAUDE_CODE_OAUTH_TOKEN`, running claude opus 4.5 on a claude.ai subscription. that contradicted what i said. this doc reconciles.

## what i got wrong

the policy quote is real but the interpretation was over-conservative. the prohibited pattern is **third-party developers offering claude.ai login *to their end users*** — building a saas where *your customers* sign in with claude.ai. that's clear-cut not allowed.

it is **not** a prohibition on a single developer using their own claude.ai subscription via oauth for their own private agents. evidence:

1. anthropic ships `claude setup-token` *for exactly this purpose* (non-interactive claude code use).
2. claude code's docs document `CLAUDE_CODE_OAUTH_TOKEN` for ci / scripted usage.
3. coleam00's repo is public; analogous patterns aren't being taken down.

so the corrected answer: **for a single-operator project, `CLAUDE_CODE_OAUTH_TOKEN` is a viable path.** the harness proves it works.

## the technical chain

claude agent sdk python doesn't accept the oauth token as a python kwarg. the chain is:

```
your python code
  └─ claude_agent_sdk.query(...)
       └─ subprocess: claude code cli (reads CLAUDE_CODE_OAUTH_TOKEN from env)
            └─ anthropic api (subscription billing)
```

the sdk shells out to the cli; the cli authenticates via the oauth token. you generate the token once with `claude setup-token` on a machine where you've signed into claude code with your claude.ai pro/max account.

## tradeoffs

| dimension | oauth (subscription) | api key |
|---|---|---|
| billing | flat rate, included in pro/max | pay-per-token |
| model access | opus + sonnet + haiku at flat rate | same, but each call costs |
| rate limits | 5-hour windows (pro); weekly caps (max). **shared with your interactive claude.ai use** | standard anthropic api rate limits |
| token lifecycle | long-lived (~30–60 days), manual rotation | static, rotate on your schedule |
| goes through litellm? | **no** — bypasses the proxy entirely | yes; scaffold's `infra/litellm/config.yaml` already wired for this |
| observability | langfuse can trace if you point the sdk at langfuse directly; lose litellm's per-route budget caps | full litellm + langfuse stack (default scaffold path) |
| tos posture | grey zone for b2b saas; clear violation if buyers get login | clear, no question |
| runaway cost protection | rate limits cap you; can't accidentally rack up $$$ | uncapped without litellm budgets |

## stormlead-specific decision: hybrid

the agent workloads here are heterogeneous. one auth doesn't fit all.

| workload | volume | latency | model fit | best auth |
|---|---|---|---|---|
| storm-watcher (deterministic polling) | n/a | n/a | no llm | n/a |
| hermes-style self-evolution loop (weekly) | very low | relaxed | opus-quality | **oauth** ✓ |
| hard-reasoning lead qualification (complex cases) | low | seconds ok | opus / sonnet | **oauth** ✓ |
| per-lead bulk qualification (every inbound lead) | high (10–100s/day mvp; 1000s+ later) | seconds | haiku | **api + litellm** |
| voice-bridge real-time conversation | high (concurrent calls) | <500ms ttft | haiku / groq | **api + litellm** |
| pseo body generation (offline) | one-shot bulk | n/a | gemini flash (free) | litellm `bulk-offline` route |

**rule of thumb**: oauth is for the low-volume, high-value opus work where flat-rate subscription billing wins. litellm + api key is for the high-volume / latency-sensitive paths where rate-limit ceilings would bite. the api path is already wired in commit `5199ff2`; adding the oauth path is purely additive — agent-runtime (when built) can support both.

## fallback contingency

if anthropic changes the policy or revokes oauth-for-personal-projects, every workload above can fall back to the api path with one config swap. `infra/litellm/config.yaml` already exposes `claude-opus-4`, `claude-sonnet-4-5`, `claude-haiku` routes; the hermes / qualification flows can re-route there with no code change.

## footguns

1. **rate limits shared with interactive use.** if you're using claude code or claude.ai yourself, you're eating your own quota.
2. **token rotation is manual.** plan a calendar reminder or a wrapper that warns when the token's near expiry. there's no documented refresh api.
3. **langfuse tracing won't go through litellm on this path.** to trace oauth-authenticated agent runs, point the agent sdk at langfuse directly via its python sdk integration.
4. **tos gray zone for b2b saas.** stormlead's *buyers* never invoke agents directly — only the operator does. that keeps it on the right side of the policy. if buyers ever get a "talk to my agent" feature where they're the principal, switch that path to api keys immediately.
5. **agent-runtime needs claude code installed and on path** for the subprocess to work. on hetzner, this is `npm install -g @anthropic-ai/claude-code` in the dockerfile.

## references

- coleam00 harness (canonical oauth + agent sdk reference): https://github.com/coleam00/Linear-Coding-Agent-Harness
- claude code's `setup-token` workflow: https://docs.claude.com/en/docs/claude-code/sdk
- open sdk issue requesting max-plan billing as a first-class feature: https://github.com/anthropics/claude-agent-sdk-python/issues/559
- prior session's research on the api-key path: `2026-05-stack-improvements.md` (litellm cve, model id updates), `2026-05-architectural-fit.md` (decision to keep litellm in front of all api-billed traffic)

## decision summary

- **oauth via `CLAUDE_CODE_OAUTH_TOKEN` is viable for stormlead's single-operator workloads.** the prior "officially no" was wrong scope; the policy is about end-user login, not personal automation.
- **adopt a hybrid auth model** when agent-runtime is built: oauth for hermes self-evolution + complex qualification, api+litellm for everything else.
- **document `CLAUDE_CODE_OAUTH_TOKEN` in `.env.example`** so future-self / contributors know the slot exists.
- **no code changes this session.** agent-runtime is still a deleted stub by prior decision; the wiring decision lives here until someone builds it.
