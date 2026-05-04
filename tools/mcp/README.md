# StormLead MCP Servers

This directory contains project-local MCP servers. They are local/dev by default and must not contact real homeowners, buyers, ad platforms, payment processors, SMS/email providers, or production webhooks.

## StormLead Local Ops

Run directly:

```powershell
npm run mcp:stormlead
```

Validate without starting an agent:

```powershell
npm run mcp:stormlead:check
npm run mcp:stormlead:smoke
```

OpenCode loads this MCP from `opencode.json`. Codex loads it from `.codex/config.toml` after the project is trusted.

## Tools

- `check_local_services`: checks local ping-post, form-receiver, and LiteLLM health/readiness URLs.
- `get_admin_kpis`: reads `/v1/admin/kpis`.
- `get_workflow_kpis`: reads `/v1/admin/workflow-kpis`.
- `get_launch_readiness`: reads `/v1/admin/launch-readiness` with optional market/service scope.
- `list_recent_workflow_runs`: reads recent audited workflow runs.
- `get_lead_timeline`: reads a redacted lead timeline by lead UUID.
- `list_buyers_redacted`: lists buyer roster rows without contact details, notes, or webhook URLs.
- `list_evidence_runs`: lists ignored local evidence folders under `testing/runs`.
- `get_evidence_manifest`: reads an `evidence.json` manifest from `testing/runs`.
- `run_v1_simulation`: runs `scripts/simulate_v1_leads.py` only when `confirm_synthetic_local=true`.
- `run_local_smoke`: runs `scripts/smoke_e2e.py` only when `confirm_synthetic_local=true`.

## Safety Model

- Read tools call local APIs or read ignored `testing/` artifacts only.
- Command tools are fixed to existing repo scripts and require `confirm_synthetic_local=true`.
- Command tools are still local/dev proofing tools; they can create synthetic database rows and ignored evidence artifacts.
- Do not add tools that send real outbound homeowner/buyer contact, mutate production infrastructure, or expose secrets.
