# UI-TARS / Agent TARS Local Exploration Runbook

StormLead can use a UI-TARS Desktop or Agent TARS fork as a local AI coworker for exploratory browser evidence. The goal is to catch visual, UX, accessibility, copy, and workflow issues on local surfaces that deterministic Playwright assertions may miss.

This is a local proof workflow only. It must not contact real homeowners, buyers, ad platforms, payment processors, SMS/email/phone providers, public webhooks, or production infrastructure.

## When To Use It

- Before or after headed Playwright runs when a human-like scan of `/admin`, landing, or buyer portal is useful.
- When the UI looks technically correct but may still have unclear hierarchy, confusing copy, weak empty states, or awkward mobile behavior.
- When you want an AI coworker to produce review notes and screenshots that can become edits, tests, backlog items, or blockers.

## Prepare A Brief

## Installed Real Runners

StormLead installs the scoped npm CLIs as local dev dependencies:

- `@ui-tars/cli` provides `ui-tars`.
- `@agent-tars/cli` provides `agent-tars`.

Use them through npm so the project-local binaries are on `PATH`:

```powershell
npm run tars:ui -- --help
npm run tars:agent -- --help
```

Direct local execution also works through npm exec:

```powershell
npm exec -- ui-tars --version
npm exec -- agent-tars --version
```

This command does not install, launch, or control UI-TARS/Agent TARS; it writes a local brief and evidence scaffold.

```powershell
npm run tars:brief
```

Narrow targets when needed:

```powershell
npm run tars:brief -- --targets admin,landing
```

MCP equivalent:

```text
prepare_tars_exploration(confirm_synthetic_local=true, targets=["admin", "landing", "buyer-portal"])
```

The command writes `testing/runs/<run-id>-tars-exploration/` with:

- `tars-brief.md` and `runner-prompt.md` for the TARS agent.
- `targets.json` with loopback URLs and role/workflow checklists.
- `reviews/tars-review-template.md` for final notes.
- `logs/findings.jsonl` for machine-readable findings.
- `evidence.json` so existing StormLead evidence readers can find the run.

If a run folder with the same ID already exists, the generator refuses to overwrite it by default so reviewer findings are not lost. Use a new run ID for a fresh pass.

## Run The Local Bridge

If a UI-TARS/Agent TARS fork is not available, run StormLead's deterministic local bridge against the prepared package:

```powershell
npm run tars:run -- --run-id <run-id>
```

MCP equivalent:

```text
run_tars_exploration(confirm_synthetic_local=true, run_id="<run-id>")
```

The bridge consumes `runner-prompt.md`, checks loopback target URLs, captures screenshots, appends structured findings to `logs/findings.jsonl`, writes `reviews/tars-review.md`, and updates `evidence.json`. It is not a replacement for an external TARS model/fork, but it removes the no-runner blocker for repeatable local fallback coverage.

## Recommended TARS Pass

1. Start local services with `npm run start:local` or the current local stack command.
2. Run `npm run tars:brief` and open the generated `tars-brief.md`.
3. Give the brief to your UI-TARS/Agent TARS fork.
4. Ask it to explore selected loopback URLs only, save screenshots under the run folder, and append findings to `logs/findings.jsonl`.
5. Use MCP tools such as `check_local_services`, `observe_chrome_page`, `list_recent_workflow_runs`, `list_buyers_redacted`, and `get_evidence_manifest` when the TARS environment supports them.
6. If no fork is attached, run `npm run tars:run -- --run-id <run-id>` for deterministic fallback coverage.
7. Triage every finding into a code edit, test addition, backlog item, or explicit blocker.

## Role Coverage

- Operator/Admin: `/admin` KPIs, workflow runs, timeline viewer, buyer roster, readiness, and review actions.
- Synthetic Homeowner: landing page hero, form, consent, validation, local-demo disclosure, and mobile completion.
- Buyer/Contractor: login, denied credentials, wallet, lead list, return review, empty states, and synthetic refill language.

Authenticated buyer portal checks require a synthetic buyer session from existing local smoke or Playwright setup. If no synthetic buyer ID/API key is available, record a blocker and only review unauthenticated or denied states.

## Validation Boundary

TARS is not a replacement for required StormLead proof. Keep these checks as the verification source of truth when relevant:

```powershell
npm run mcp:stormlead:check
npm run test:playwright -- --project=chromium --reporter=line
npm run observe:chrome -- --url http://127.0.0.1:8003/admin --duration-seconds 10 --headless true
```

Generated TARS evidence should stay ignored under `testing/runs/` unless a curated review artifact is explicitly needed.
