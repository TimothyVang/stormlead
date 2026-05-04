# StormLead Operations Dashboard Spec (May 4, 2026)

## KPIs (required)
- **Funnel counts/rates** by stage with shared `correlation_id`: captured, qualified, auctioned, sold, unsold, retried, adjusted.
- **Conversion rates**: captured→qualified, qualified→auctioned, auctioned→sold.
- **Queue lag**: p50/p95 lag seconds for Hatchet workflows (`lead.captured`, `lead.qualified`).
- **Buyer endpoint health**: failure rate (%), timeout rate (%), p95 latency, retry volume.
- **Qualification quality**: qualification parse/processing error rate (%), reject ratio (%).
- **Adjustment exposure**: adjusted leads and adjusted cents per day.

## Alerts / SLA thresholds
- Queue lag p95 > **120s** for 10m => page on-call.
- Buyer endpoint failure rate > **5%** for 5m => page on-call.
- Buyer timeout rate > **3%** for 5m => warn.
- Qualification error rate > **2%** for 15m => page on-call.
- Sold rate drop > **30%** vs trailing 7-day baseline for 30m => warn.
- Adjusted lead ratio > **8%** for 30m => warn.

## Operator-facing health checks
- `/healthz`: process liveness.
- `/readyz`: dependency readiness (DB/Hatchet).
- Synthetic probe for buyer post endpoint success every 5 minutes from worker network.
- Queue depth and oldest-message age surfaced as health panel.

## Correlation requirements
- Every critical-path log/event/metric must include `correlation_id`.
- Correlation id must be propagated from ingress (`form-receiver` webhook id / lead id fallback) to `agent-runtime`, `ping-post`, and `storm-watcher` workflows.
