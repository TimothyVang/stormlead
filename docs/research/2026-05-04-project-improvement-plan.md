# 2026-05-04 project improvement plan

## why this exists

This plan translates the current repo state into a prioritized improvement backlog that is practical for a solo operator.

## top priorities (next 2 weeks)

1. **Ship CI gates before more feature work**
   - Add a GitHub Actions workflow that runs:
     - `uv sync --frozen`
     - `pytest`
     - `npm ci && npx playwright test --grep @smoke` (or one deterministic smoke spec)
   - Block merges on green checks.

2. **Close placeholder scripts and docs drift**
   - Implement or remove placeholders referenced in README/justfile (`seed`, `smoke`, deploy stubs).
   - Mark every placeholder as either:
     - `implemented`,
     - `deferred with owner/date`, or
     - `removed`.

3. **Define reliability SLOs + alerting for critical path**
   - Start with 3 SLOs:
     - lead capture success rate,
     - ping-post auction completion under 5 seconds,
     - buyer delivery success rate.
   - Add basic alert routes (email/Slack/webhook) for SLO burn and queue backlog.

4. **Harden security baseline**
   - Add `gitleaks` secret scanning in CI.
   - Add dependency scanning (`pip-audit` + `npm audit --omit=dev` or equivalent policy tool).
   - Enforce pinned container digests for every service image, not just LiteLLM.

## medium priorities (next 30 days)

1. **Contract tests between services**
   - Add schema contract tests for emitted/consumed events (`lead.captured`, `lead.enriched`, auction outcomes).
   - Fail CI if event payloads drift without versioning.

2. **Database migration safety checks**
   - Add migration CI job that runs:
     - fresh DB migrate,
     - downgrade/upgrade cycle,
     - smoke query checks.
   - Require migration notes for every schema change.

3. **Replay + incident workflow maturity**
   - Standardize “incident package” output in `testing/evidence-summary.md` format.
   - Add one-command replay for a failed lead path (capture → enrich → auction).

4. **Observability consistency**
   - Ensure all services emit:
     - correlation/request IDs,
     - consistent event names,
     - latency + outcome metrics.
   - Create one operator dashboard for funnel and failure points.

## longer-term improvements (60–90 days)

1. **Performance envelope testing**
   - Add load tests for ping-post and form-receiver at realistic burst patterns.
   - Track p50/p95/p99 latency and timeout budgets per buyer.

2. **Feature flag and rollout controls**
   - Add config-driven toggles for risky changes (new qualification policy, buyer routing logic).
   - Support canary rollout by buyer segment.

3. **Data governance + retention policy**
   - Define PII retention windows, deletion workflows, and audit evidence.
   - Add automated cleanup jobs and verification reports.

## suggested scorecard

Track progress weekly with a simple scorecard:

- **Build health:** CI pass rate, mean time to fix red pipeline.
- **Lead funnel:** capture→qualified conversion, sold rate, unsold recovery.
- **Ops reliability:** incidents/week, mean time to detection, mean time to recovery.
- **Economics:** margin per sold lead, refund/credit rate, buyer acceptance rate.

## recommended execution order

1. CI + security gates.
2. Placeholder cleanup and operational SLOs.
3. Contract tests + migration safety.
4. Performance and rollout sophistication.

This order keeps the system safe while preserving velocity on product execution.
