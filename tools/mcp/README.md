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
- `observe_chrome_page`: launches a local-only Chrome/Chromium browser session, performs optional simple actions, and streams console/page/network/WebSocket evidence to `testing/runs`.
- `run_chrome_observer_functional_test`: starts a local loopback web page and functionally verifies both the direct Chrome observer and the MCP `observe_chrome_page` tool capture browser evidence.
- `run_self_learning_loop`: runs the local Playwright, Puppeteer/Lighthouse, and MCP THINK -> ACT -> OBSERVE -> DECIDE evidence loop and writes runner prompts under `testing/runs`.
- `run_v1_simulation`: runs `scripts/simulate_v1_leads.py` only when `confirm_synthetic_local=true`.
- `run_local_smoke`: runs `scripts/smoke_e2e.py` only when `confirm_synthetic_local=true`.

## Safety Model

- Read tools call local APIs or read ignored `testing/` artifacts only.
- `STORMLEAD_ADMIN_URL`, `STORMLEAD_FORM_RECEIVER_URL`, and `STORMLEAD_LITELLM_URL` overrides must stay on loopback hostnames such as `127.0.0.1` or `localhost`.
- Command tools are fixed to existing repo scripts and require `confirm_synthetic_local=true`.
- Command tools are still local/dev proofing tools; they can create synthetic database rows and ignored evidence artifacts.
- `observe_chrome_page` refuses non-loopback URLs; it is for local browser evidence only, not public browsing or real user contact.
- `run_self_learning_loop` refuses to run without `confirm_synthetic_local=true`; Codex runner dispatch is off unless `dispatch_codex=true` is explicitly passed.
- Do not add tools that send real outbound homeowner/buyer contact, mutate production infrastructure, or expose secrets.

## Chrome Observer

Run directly:

```powershell
npm run observe:chrome -- --url http://127.0.0.1:8003/admin --duration-seconds 10 --headless true
```

Use installed Google Chrome instead of Playwright-managed Chromium when needed:

```powershell
npm run observe:chrome -- --url http://127.0.0.1:8003/admin --channel chrome --headless false
```

Artifacts are written under `testing/runs/<run-id>-chrome-observe/`, including `logs/chrome-events.jsonl`, `logs/chrome-summary.json`, and screenshots. Agents should read those files before deciding whether to edit app code, update tests, or collect more evidence.

Functional verification for the observer:

```powershell
npm run test:chrome-observer
```

Preferred MCP function-call verification:

```text
run_chrome_observer_functional_test(confirm_synthetic_local=true)
```

Both paths start a local loopback page, emit real browser console logs and HTTP failures, then assert both the direct CLI and MCP `observe_chrome_page` function-call path captured the expected JSONL events.

## Self-Learning Loop

Run directly:

```powershell
npm run learn:loop
```

Run through MCP after explicit local confirmation:

```text
run_self_learning_loop(confirm_synthetic_local=true, playwright_project="none")
```

The loop writes `testing/runs/<run-id>-self-learning-loop/` with iteration markdown, MCP/Chrome evidence, optional Puppeteer/Lighthouse reports, a summary JSON file, and runner prompts. It does not dispatch Codex runners unless `dispatch_codex=true` is explicitly passed.
