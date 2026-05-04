# 2026-05 stack improvements

Dated technical follow-up to the original stack audit and forkable-stack notes. This file is sanitized to keep review-only wording out of source docs.

## current technical deltas

- LiteLLM image pin moved from `v1.83.4-stable` to `v1.83.7-stable`.
- Hatchet v0.50.x is legacy; plan against the v1 rewrite where new workflow work depends on Hatchet internals.
- `crystaldba/postgres-mcp` should be pinned to a specific tag rather than `latest`.
- Tropycal activity should be checked before relying on it for production storm ingestion.
- NATS is not needed for V1 because Hatchet and Postgres cover the first durable workflow path.
- SeaweedFS is deferred for V1; use a hosted object bucket until storage operations justify more infra.
- OpenBao is deferred until the operator model or secret-rotation workflow requires it.
- US-region deployment remains important for the ping-post auction latency budget.

## business-mechanics gaps

The earlier docs did not fully model these product mechanics:

1. lead deduplication across form, call, and import sources.
2. fraud/spam scoring.
3. buyer review workflow.
4. buyer billing ledger and wallet refill flow.
5. campaign attribution and source ROI.
6. buyer cap and territory enforcement.
7. call tracking ingestion.
8. daily buyer reports.

## recommended sequence

1. Pin production images and document rollback versions.
2. Keep Hatchet as the workflow engine for V1 and defer additional event buses.
3. Add buyer CRM fields and wallet controls.
4. Add territory and service matching to ping-post eligibility.
5. Add campaign/source fields to leads.
6. Add buyer review request and wallet adjustment flow.
7. Add buyer daily report endpoint.
8. Add mailer CSV export and call tracking ingestion.
9. Add low-wallet alert/refill recommendation logic.

## deferred technical work

- Postgres MCP integration can stay behind a read-only role until agent tooling needs write workflows.
- Vision models can wait until photo ingestion produces enough samples.
- Fully self-hosted telephony should wait until the lead marketplace proves volume and margin.
- Multi-region deployment should wait until a single-region V1 is saturated.
