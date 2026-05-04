# 2026-05 forkable stack

Dated source-repo research for StormLead. This version is sanitized to keep review-only wording out of source docs.

## tl;dr

There is no strong open-source clone of Boberdoo, LeadConduit, or Leadspedia. The ping-post engine remains the part StormLead should build directly. Other layers have useful reference projects.

## candidate repos by layer

| layer | candidate | note |
| --- | --- | --- |
| storm ingestion | `tropycal/tropycal`, NWS APIs, FEMA open data | useful weather and event inputs. |
| pSEO landing | `agamm/pseo-next` | useful page-generation pattern. |
| forms | `formbricks/formbricks` | useful form and webhook concepts. |
| CRM | `twentyhq/twenty` | useful CRM data model and UX patterns. |
| telephony | `jambonz/jambonz`, FreeSWITCH, Asterisk | useful later if vendor calls become limiting. |
| agent runtime | `kortix-ai/suna`, LangGraph examples | useful reference, but current runtime stays smaller. |
| email/newsletter | `listmonk/listmonk` | useful reference for campaign and list operations. |
| analytics | `umami-software/umami` | useful product analytics reference. |
| observability | Langfuse | useful tracing reference for model calls. |
| vision | Florence-2, Detectron2, LLaVA | useful later for photo analysis. |

## current StormLead decisions

- Do not fork Suna for V1; use the existing small LiteLLM HTTP client.
- Do not expose a full buyer portal until buyers refill consistently.
- Do not self-host telephony until vendor calls become a real constraint.
- Do not build a separate analytics stack until Postgres/admin KPIs are insufficient.
- Build the ping-post auction directly in the repo.

## useful implementation patterns

- Form webhook ingestion with idempotency keys.
- CRM buyer stage and follow-up fields.
- Campaign/source attribution tables.
- Durable workflow retry and operator review states.
- Generated landing pages with campaign-specific tracking params.
- Call tracking events mapped back to lead/source rows.
- Model-call tracing through a central gateway.

## next action

Use these repos as references only. Copy patterns when they reduce implementation risk, but keep the V1 code path small and local to the current FastAPI/Postgres services.
