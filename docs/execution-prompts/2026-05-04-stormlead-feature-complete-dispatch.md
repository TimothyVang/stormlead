# StormLead Feature-Complete: 20-Agent Dispatch Plan

Date: 2026-05-04

Inherits: `docs/execution-prompts/master-agent-execution-prompt.md`

This document is the orchestration index for the 20-agent parallel build that drives StormLead to feature-complete. Each agent has its own execution prompt file in this directory. Dispatch agents in wave order — do not start Wave 2 until Wave 1 is committed and tested.

---

## Pre-Dispatch Checklist

Before launching Wave 1, confirm:

- [ ] `uv run pytest services libs -x -q` passes (baseline green)
- [ ] `uv run alembic upgrade head` succeeds (DB is at current head)
- [ ] `git status --short` shows no uncommitted changes that would conflict with agent work
- [ ] Docker dev stack can start: `docker compose --env-file .env.example -f infra/compose/dev/docker-compose.yml config --quiet`

---

## Wave 1 — 10 Parallel Agents

**Launch all 10 simultaneously.** Each agent owns an isolated file domain with zero write conflicts.

| Agent | Prompt File | Primary Output | Timebox |
|-------|------------|----------------|---------|
| 01 | `2026-05-04-agent-01-storm-tropycal-nhc-poller.md` | `tropycal_poller.py` + Hatchet cron | 1h |
| 02 | `2026-05-04-agent-02-storm-watcher-tests.md` | `tests/test_nws.py`, `test_fema.py`, `test_tropycal.py` | 1h |
| 03 | `2026-05-04-agent-03-enrich-worker-full.md` | `geocode.py`, `photo.py`, enrich.py extension | 1h |
| 04 | `2026-05-04-agent-04-nurture-outreach.md` | `nurture.py` stub → real HTTP outreach | 45m |
| 05 | `2026-05-04-agent-05-hermes-self-evolution.md` | `hermes.py` TODOs + migration `0007` + `SkillProposalRow` | 1.5h |
| 06 | `2026-05-04-agent-06-agent-runtime-tests.md` | `test_hermes.py`, `test_qualify_edge_cases.py` | 45m |
| 07 | `2026-05-04-agent-07-call-tracking-ingestion.md` | `call_tracking.py`, `compliance.py`, `CallEventRow` | 1h |
| 08 | `2026-05-04-agent-08-campaign-attribution.md` | `attribution.py` with ROI functions | 45m |
| 09 | `2026-05-04-agent-09-landing-page.md` | `apps/landing/` + dev compose entry | 1h |
| 10 | `2026-05-04-agent-10-cicd-pipeline.md` | `.github/workflows/ci.yml`, `smoke.yml` | 45m |

### Wave 1 Completion Gate

Before launching Wave 2, verify:

```bash
uv run pytest services libs -x -q
uv run python -c "from storm_watcher.tropycal_poller import normalize_tropical_storm; print('ok')"
uv run python -c "from enrich_worker.geocode import geocode_address; print('ok')"
uv run alembic upgrade head  # migration 0007 must be applied
```

---

## Wave 2 — 6 Parallel Agents

**Launch after Wave 1 is committed and gates pass.**

| Agent | Prompt File | Primary Output | Timebox |
|-------|------------|----------------|---------|
| 11 | `2026-05-04-agent-11-buyer-crm-fields.md` | `BuyerRow` CRM columns + migration `0008` + `buyer_crm.py` | 1h |
| 12 | `2026-05-04-agent-12-guardrail-automation.md` | `guardrails.py` + daily cron | 1h |
| 13 | `2026-05-04-agent-13-mailer-csv-export.md` | `mailer.py` with CSV export function | 30m |
| 14 | `2026-05-04-agent-14-integration-tests.md` | `test_integration.py` for ping-post API | 1h |
| 15 | `2026-05-04-agent-15-prod-compose.md` | `prod/docker-compose.yml`, `systemd/`, `deploy.sh` | 1h |
| 16 | `2026-05-04-agent-16-buyer-portal.md` | `apps/buyer-portal/` + dev compose entry | 1.5h |

### Wave 2 Completion Gate

Before launching Wave 3, verify:

```bash
uv run alembic upgrade head  # migration 0008 must be applied
uv run pytest services libs -x -q
uv run python -c "from ping_post.buyer_crm import check_exclusive_zip_conflict; print('ok')"
docker compose --env-file .env.example -f infra/compose/prod/docker-compose.yml config --quiet
```

---

## Wave 3 — 4 Parallel Agents

**Launch after Wave 2 is committed and gates pass.**

| Agent | Prompt File | Primary Output | Timebox |
|-------|------------|----------------|---------|
| 17 | `2026-05-04-agent-17-routing-enforcement.md` | Cap/territory/class enforcement in `auction.py`, 4 new admin endpoints | 2h |
| 18 | `2026-05-04-agent-18-timescale-hypertables.md` | Migration `0009` + `scripts/retention.py` | 1h |
| 19 | `2026-05-04-agent-19-caddy-waf-hardening.md` | Caddyfile: CrowdSec + rate limit + admin WAF | 45m |
| 20 | `2026-05-04-agent-20-form-receiver-wiring.md` | `api.py`: call tracking endpoint + TrustedForm | 1h |

---

## Final Verification (After Wave 3)

Run these in order after all Wave 3 agents are committed:

```bash
# 1. Start dev stack
docker compose --env-file .env.example -f infra/compose/dev/docker-compose.yml up -d

# 2. Wait for health checks
curl -sf http://localhost:8002/healthz && echo "form-receiver: ok"
curl -sf http://localhost:8003/healthz && echo "ping-post: ok"
curl -sf http://localhost:8001/healthz && echo "landing: ok"
curl -sf http://localhost:8004/healthz && echo "buyer-portal: ok"

# 3. Full smoke test
uv run python scripts/smoke_e2e.py

# 4. V1 lead simulation
uv run python scripts/simulate_v1_leads.py

# 5. KPI check
curl http://localhost:8003/v1/admin/kpis

# 6. Guardrail check
curl -X POST http://localhost:8003/v1/admin/guardrails/evaluate

# 7. Mailer CSV check
curl "http://localhost:8003/v1/admin/export/mailer-csv?state=FL"

# 8. Full test suite
uv run pytest services libs -q

# 9. Playwright browser evidence
npm run test:playwright -- --project=chromium --reporter=line
```

---

## Feature-Complete Definition of Done

All 20 items must be green before declaring feature-complete:

- [ ] Agent-01: Tropycal/NHC poller registered in Hatchet, season-gated
- [ ] Agent-02: Storm-watcher test suite passing (NWS, FEMA, Tropycal)
- [ ] Agent-03: Enrich-worker geocodes addresses and classifies photos via LiteLLM vision
- [ ] Agent-04: Nurture outreach sends real HTTP POST to `NURTURE_WEBHOOK_URL`
- [ ] Agent-05: Hermes persists weekly proposals to `skill_proposals` DB table
- [ ] Agent-06: Agent-runtime test suite covers Hermes and qualify edge cases
- [ ] Agent-07: Call tracking and TrustedForm compliance modules exist and import cleanly
- [ ] Agent-08: Campaign ROI attribution functions exist and return correct types
- [ ] Agent-09: Landing page serves Formbricks embed with UTM attribution
- [ ] Agent-10: CI/CD pipeline runs on PR with lint, test, and Docker build jobs
- [ ] Agent-11: Buyer CRM fields (sales_stage, services_offered, etc.) in DB and model
- [ ] Agent-12: Guardrail automation pauses buyers who exceed adjustment rate or response time thresholds
- [ ] Agent-13: Mailer CSV export function returns valid CSV with tracking codes
- [ ] Agent-14: Ping-post integration tests pass (health check, buyer creation, zip conflict)
- [ ] Agent-15: Prod compose complete with pinned images, systemd unit, and deploy script
- [ ] Agent-16: Buyer portal serves wallet, leads, and return request pages
- [ ] Agent-17: Daily/monthly caps, territory/service matching, and lead class routing enforced; 4 admin endpoints wired
- [ ] Agent-18: Timescale hypertables on ping_attempts and billing_events; PII retention script
- [ ] Agent-19: CrowdSec re-enabled, rate limiting on webhook, admin WAF restriction
- [ ] Agent-20: Call tracking endpoint live; TrustedForm integrated into Formbricks handler

---

## File Conflict Map (Safe Parallel Zones)

```
Wave 1 — Zero shared file writes:
  Agent-01  → services/storm-watcher/tropycal_poller.py (NEW), worker.py
  Agent-02  → services/storm-watcher/tests/ (NEW)
  Agent-03  → services/enrich-worker/geocode.py (NEW), photo.py (NEW), enrich.py
  Agent-04  → services/agent-runtime/nurture.py
  Agent-05  → services/agent-runtime/hermes.py + libs/stormlead_db/tables.py (SkillProposalRow) + migration 0007
  Agent-06  → services/agent-runtime/tests/ (new files only)
  Agent-07  → services/form-receiver/call_tracking.py (NEW), compliance.py (NEW) + libs/stormlead_db/tables.py (CallEventRow)
  Agent-08  → services/ping-post/attribution.py (NEW)
  Agent-09  → apps/landing/ (NEW dir) + infra/compose/dev/docker-compose.yml
  Agent-10  → .github/workflows/ (NEW files)

  ⚠️  CONFLICT RISK: Agents 05 and 07 both write to libs/stormlead_db/tables.py.
      Resolve: run Agent-05 first (it owns the Alembic migration), then Agent-07 adds CallEventRow
      to tables.py in a separate step AFTER Agent-05 is done, OR merge both changes manually.

Wave 2 — Distinct files within wave:
  Agent-11  → libs/stormlead_db/tables.py (buyer CRM columns) + migration 0008 + ping-post/buyer_crm.py
  Agent-12  → services/ping-post/guardrails.py (NEW)
  Agent-13  → services/ping-post/mailer.py (NEW)
  Agent-14  → services/ping-post/tests/test_integration.py (NEW)
  Agent-15  → infra/compose/prod/ + infra/systemd/ + scripts/deploy.sh
  Agent-16  → apps/buyer-portal/ (NEW) + infra/compose/dev/docker-compose.yml

  ⚠️  CONFLICT RISK: Agents 11 and 16 both touch infra/compose/dev/docker-compose.yml.
      Resolve: merge both service additions after agents complete.

Wave 3 — Distinct files within wave:
  Agent-17  → services/ping-post/auction.py + services/ping-post/api.py
  Agent-18  → libs/stormlead_db/migrations/versions/0009_... (NEW) + scripts/retention.py (NEW)
  Agent-19  → infra/caddy/Caddyfile
  Agent-20  → services/form-receiver/api.py + services/form-receiver/schemas.py
```

---

## Safety Rules for All Agents

All agents must follow the full safety contract from `docs/execution-prompts/master-agent-execution-prompt.md`:

- Use synthetic/dev data only — no real homeowner contact
- No commits unless user explicitly asks
- No production deployments
- No real paid services (SMS, email, ad platforms, payment processors)
- All generated evidence under ignored `testing/` paths
- Stop and ask if credentials, destructive actions, or real-world activation are required