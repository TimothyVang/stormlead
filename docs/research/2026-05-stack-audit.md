# 2026-05 stack audit

Dated technical audit across candidate repos. This version is sanitized to keep review-only wording out of source docs.

## tl;dr

- Use LiteLLM through a pinned, verified Docker image instead of adding provider SDKs to runtime services.
- Use Postgres as the system of record and keep buyer/wallet/routing data in the repo's own schema.
- Use Hatchet for durable workflows in V1.
- Use Caddy/Coraza for the public edge when production routes exist.
- Keep Langfuse available for model-call observability.
- Do not fork a large agent platform unless the small runtime becomes a bottleneck.

## repos reviewed

| layer | repo | verdict |
| --- | --- | --- |
| agent runtime | Suna, Letta, LangGraph examples | useful references, not a V1 fork target. |
| CRM | Twenty | useful buyer CRM reference. |
| forms | Formbricks | useful webhook and form reference. |
| workflow | Hatchet, n8n, Temporal | Hatchet is current V1 path. |
| observability | Langfuse, SigNoz | Langfuse for model traces; defer bigger stack work. |
| database | Postgres, Timescale, pgvector | current Postgres stack remains right. |
| edge | Caddy, Coraza | current edge plan remains right. |
| mesh | Netbird, Tailscale-like patterns | optional later for operator access. |

## integration notes

- Form webhooks can feed Postgres and ping-post through existing FastAPI services.
- Twenty-style CRM objects map to buyer stages, territories, and follow-up fields.
- Hatchet workflows map to lead lifecycle events and retry handling.
- Langfuse traces can attach model route, latency, score, and token cost to agent-runtime decisions.
- Postgres MCP should run through a read-only role when used for agent research.
- Caddy should route only implemented public services.

## common wrong assumptions

1. Do not assume a large agent framework is needed for V1.
2. Do not assume every self-hosted app needs native SSO before the first operator workflow.
3. Do not assume the buyer portal is required before buyer refill behavior is proven.
4. Do not assume a separate event bus is required while Hatchet/Postgres cover the current workflow path.
5. Do not assume a Go/Rust auction rewrite is needed before measuring Python latency under load.

## recommended V1 picks

| layer | pick |
| --- | --- |
| runtime language | Python |
| API framework | FastAPI |
| database | Postgres |
| workflow | Hatchet |
| model gateway | LiteLLM |
| edge | Caddy |
| WAF | Coraza when public routes exist |
| browser proof | Playwright/Cowork |
| deployment | Docker Compose under systemd |

## next implementation actions

1. Keep image/version pins explicit.
2. Keep runtime model access behind LiteLLM.
3. Keep admin/mutation surfaces private or authenticated.
4. Keep workflow evidence in Postgres transition rows.
5. Keep generated browser artifacts ignored.
6. Add production compose only when the implemented service set is clear.
