# Role Experience Agentic Workflow Test Plan

StormLead's current proof is a local role-experience test, not a production launch
exercise. It uses synthetic leads, local buyers, local wallet/reporting APIs, and
ignored evidence under `testing/runs/`.

## Role Matrix

| Role | Current surface | UX goal | Evidence |
| --- | --- | --- | --- |
| Homeowner Lead Submitter | Formbricks webhook path exercised by `scripts/simulate_v1_leads.py` | Confirm a synthetic tree-removal request creates a lead ID/status without contacting a real homeowner | Simulation evidence JSON plus admin timeline screenshot |
| Agentic Workflow Worker | Hatchet-backed workflow services and persisted timeline events | Confirm capture, enrichment, qualification/rejection, auction, sold/unsold/nurture, return, and review transitions are recorded | `/v1/admin/leads/{lead_id}/timeline` plus role Playwright screenshots |
| Buyer / Contractor | Local buyer APIs, listener, wallet, return, and daily-report endpoints | Confirm an active funded local buyer can receive lead delivery state, request returns, and see wallet/report data | Buyer roster screenshot plus `/v1/buyers/{buyer_id}/daily-report` response checks |
| Operator / Admin | `/admin` | Confirm KPIs, recent runs, timeline, review controls, buyer roster, wallet controls, and readiness are visible and usable | Role Playwright evidence manifest and screenshots |
| Business Owner | `/admin` readiness section and readiness API | Confirm local technical readiness can be reviewed while commercial paid launch stays blocked without explicit approval | Readiness screenshot plus `/v1/admin/launch-readiness` response checks |

## Sample Scenarios

The browser role proof expects the V1 simulation evidence to be available first:

- `qualified_sold`
- `returned_approved`
- `unsold_no_buyer`
- `rejected_low_quality`
- `duplicate_capture`
- `suppressed_opt_out`
- `nurtured_unsold`
- `nurtured_rejected`

Acceptance for the simulation layer is that every scenario reports
`status: passed` in `testing/runs/<run_id>/v1-simulation-evidence.json`.

## Browser Proof

The tracked workflow metadata lives in
`tests/playwright/workflows/role-experience.workflow.ts`.

The role proof spec lives in `tests/playwright/role-experience.spec.ts` and:

- opens `/admin`;
- verifies role-relevant UI regions;
- selects a recent workflow run and loads its timeline;
- checks timeline events through the admin API;
- checks buyer wallet/report data through the local buyer APIs;
- exercises hold and approve review controls with synthetic notes;
- captures screenshots for homeowner/agent, buyer, operator, and business-owner sections.

## Validation Commands

Run these from the repository root:

```powershell
uv run python scripts/simulate_v1_leads.py
uv run python scripts/smoke_e2e.py
npm run test:playwright -- --project=chromium --reporter=line
npm run mcp:stormlead:smoke
git diff --check
```

If `.env` is missing, copy `.env.example` to `.env` before starting local
services. Keep `.env` local and ignored.

## Future Role UI/Auth Phase

Add true role-specific surfaces only after the current local proof passes:

- homeowner landing/intake UI;
- buyer portal for lead review, returns, daily reports, wallet, and refill status;
- operator/admin auth and role-gated controls;
- business-owner reporting/readiness dashboard.

Use a local dev role switcher first. Real auth, credentials, paid traffic, and
production launch controls stay out of this milestone unless explicitly approved.
