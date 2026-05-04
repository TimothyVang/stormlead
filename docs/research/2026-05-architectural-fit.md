# 2026-05 architectural fit

Dated architecture review for StormLead. This version is sanitized to keep review-only wording out of source docs.

## profile

Ranked for this profile:

- single-operator Python engineer.
- Hetzner budget around $80-$200/month.
- auction endpoint target under 5 seconds.
- 4-8 week MVP.
- self-hosted source of truth for buyer, lead, wallet, and routing state.

## verdict

The current bones are right for V1:

- FastAPI services.
- Postgres as the business database.
- Hatchet for durable workflows.
- Caddy for the edge.
- LiteLLM for model routing.
- Docker Compose under systemd for production.

The dressing was too heavy for V1. Cut NATS, SeaweedFS, OpenBao, multi-region deployment, and full portal work until there is a concrete bottleneck.

## alternatives reviewed

| option | fit | note |
| --- | --- | --- |
| current FastAPI + Postgres + Hatchet | high | small team can operate it and extend it vertically. |
| Supabase + Vercel + n8n | medium | fastest UI path, but less control over the business record. |
| Rails/Hotwire monolith | medium | good operational simplicity, but current repo is already Python-first. |
| Django monolith | medium | viable alternative, but migration cost is not worth it for V1. |
| Temporal-first microservices | medium later | strong workflow engine, too much setup for first launch. |
| DBOS Transact | spike later | interesting Postgres-native durability; evaluate only when workflow work resumes. |
| Node/Next full-stack | low | mismatches Python service base. |
| Go/Rust auction service | later | only useful after Python misses measured latency targets. |

## tier-1 cuts

- **NATS**: remove for V1. Hatchet handles durable workflow triggers and Postgres can handle the current cross-service state needs.
- **SeaweedFS/MinIO**: remove for V1. A hosted object bucket is simpler until storage ops become a real burden.
- **OpenBao**: defer until a second operator or stronger rotation process exists.
- **Coolify**: skip. Use Docker Compose under systemd first.

## region decision

Deploy the auction endpoint in a US region close to buyers:

- Ashburn for US East.
- Hillsboro for US West.

Avoid EU regions for the auction endpoint because extra RTT eats the ping-post budget.

## tier-2 spikes

Defer these until agent-runtime or workflow scale forces the question:

- DBOS Transact versus Hatchet v1 for transactional workflow steps.
- Temporal for high-scale replay and cross-language orchestration.
- Dedicated Go/Rust ping-post service.
- Fully self-hosted telephony.

## production shape

V1 should deploy as one US-region host:

- Caddy edge.
- FastAPI services.
- Hatchet engine/workers.
- Postgres.
- LiteLLM proxy.
- object bucket.
- call tracking vendor.
- mail vendor.

Scale only after the single-host version proves buyer refill behavior, campaign ROI, and operational load.
