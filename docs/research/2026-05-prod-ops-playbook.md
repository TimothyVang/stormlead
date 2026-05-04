# 2026-05 Production Operations Playbook

## Scope
This document defines backup/restore, secrets policy, smoke validation, and incident response for Stormlead production.

## RPO / RTO targets

| Component | RPO target | RTO target | Notes |
|---|---:|---:|---|
| Postgres (primary transactional store) | <= 5 minutes | <= 30 minutes | WAL-archived + nightly full backup |
| Object storage (lead evidence/artifacts) | <= 15 minutes | <= 4 hours | Bucket versioning + replication |
| Hatchet metadata DB (`hatchet` schema) | <= 5 minutes | <= 30 minutes | Restored from Postgres backup set |

## Postgres backup and restore

### Backup schedule
- Full backup daily at 02:00 UTC (retention 30 days).
- WAL archive every 5 minutes (retention 7 days) for point-in-time restore.
- Weekly restore drill into staging on Sundays at 03:30 UTC.

### Backup commands
```bash
# full logical backup from prod host
pg_dump -Fc -h "$PGHOST" -U "$PGUSER" -d "$PGDATABASE" > /backup/postgres/stormlead-$(date +%F).dump

# cluster-level roles backup
pg_dumpall -g -h "$PGHOST" -U "$PGUSER" > /backup/postgres/roles-$(date +%F).sql
```

### Restore commands
```bash
# restore into new DB
createdb -h "$PGHOST" -U "$PGUSER" stormlead_restore
pg_restore -h "$PGHOST" -U "$PGUSER" -d stormlead_restore --clean --if-exists /backup/postgres/stormlead-YYYY-MM-DD.dump

# restore roles if required
psql -h "$PGHOST" -U "$PGUSER" -f /backup/postgres/roles-YYYY-MM-DD.sql
```

### PITR procedure
1. Provision fresh Postgres node with matching major version (`pg16`).
2. Restore latest base backup.
3. Replay WAL until target timestamp (`recovery_target_time`).
4. Run smoke validation script (`scripts/smoke_deploy_path.sh`).

## Object storage backup and restore

### Backup schedule
- Bucket versioning enabled always.
- Cross-region replication enabled for `stormlead-prod-artifacts` and `stormlead-prod-langfuse`.
- Nightly inventory + checksum export at 01:00 UTC.

### Backup commands
```bash
# mirror object bucket to cold backup bucket
mc mirror --overwrite --remove prod/stormlead-prod-artifacts backup/stormlead-prod-artifacts
mc mirror --overwrite --remove prod/stormlead-prod-langfuse backup/stormlead-prod-langfuse
```

### Restore commands
```bash
mc mirror --overwrite backup/stormlead-prod-artifacts prod/stormlead-prod-artifacts
mc mirror --overwrite backup/stormlead-prod-langfuse prod/stormlead-prod-langfuse
```

## Secrets handling policy and rotation cadence

| Environment | Secret source of truth | Injection method | Rotation cadence |
|---|---|---|---|
| dev | `.env` + local secret manager namespace | docker compose env-file | every 30 days (or immediately if shared) |
| stage | managed secret manager (dedicated project) | CI/CD runtime injection | every 14 days |
| prod | managed secret manager + dual-control approval | short-lived runtime tokens only, never committed | every 7 days for API keys, every 30 days for DB creds |

Policy rules:
1. No secrets in git, docker-compose YAML, or build args.
2. Production secrets require dual-operator approval and audit trail.
3. Emergency rotation SLA: begin within 15 minutes, complete within 60 minutes.
4. Rotation runbook must include dependent restarts and smoke checks.

## Incident playbook

### Buyer outage
1. Trigger: consecutive ping/post failures > 20% for 5 minutes.
2. Action: set buyer to `paused` in routing controls, shift traffic to secondary buyers.
3. Validate: run `scripts/smoke_deploy_path.sh --buyer-url <secondary>`.
4. Recover: re-enable primary buyer after 15-minute healthy window.

### Model outage (LLM/LiteLLM upstream)
1. Trigger: `agent-runtime` classify/qualify failures > 10% for 5 minutes.
2. Action: switch to fallback model profile and disable non-critical enrichment.
3. Validate: run smoke script with `--skip-enrich` and verify auction still executes.
4. Recover: revert profile after stable success/error budget for 30 minutes.

### Database failover
1. Trigger: Postgres primary unavailable > 60 seconds or replication lag > RPO target.
2. Action: promote hot standby and rotate `DATABASE_URL`/read endpoints.
3. Validate: run `scripts/smoke_deploy_path.sh` and compare lead write counts.
4. Follow-up: run PITR rehearsal in staging within 24 hours.

## Smoke validation requirement
Every production deploy and incident recovery must pass `scripts/smoke_deploy_path.sh` before declaring service healthy.
