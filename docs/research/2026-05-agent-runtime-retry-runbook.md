# Agent Runtime Retry & Dead-Letter Runbook

Date: 2026-05-04

## Auto-retry triggers

Agent-runtime tasks should auto-retry when failures are likely transient:

- Provider/API availability issues (timeouts, 5xx, connection resets).
- Short-lived platform resource contention.
- Model primary-route failure where fallback model succeeds.

Current retry rules:

- `qualify_lead`: 2 retries, 120 second step timeout.
- `hermes_self_evolution`: 1 retry, 600 second step timeout.

## Manual intervention triggers

Require manual intervention when repeated failures indicate non-transient faults:

- Dead-letter emission (`agent.task.dead_lettered`) after retry budget exhausted.
- Input payload schema defects (missing `lead_id`, invalid UUIDs).
- Deterministic cap failures: token cap or cost cap exceeded.
- Persistent data-layer failures (missing rows, migration drift).

## Dead-letter handling

When dead-lettered events appear in operator dashboards/log sinks:

1. Inspect `correlation_id`, `run_id`, and `task_name`.
2. Validate token/cost cap reason and adjust caps only with approval.
3. Confirm whether fallback model was used before final failure.
4. Requeue only after root-cause is fixed; do not blind-retry repeatedly.

## Dashboard/log sink signals

Dashboards should alert on:

- Any `agent.task.dead_lettered` event.
- More than 3 `agent.task.failed` events for same task in 15 minutes.
- Repeated cap violations (`cost cap exceeded`, `token cap exceeded`).

