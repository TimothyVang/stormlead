#!/usr/bin/env node

import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const runsDir = path.join(repoRoot, 'testing', 'runs');

const TARGET_IDS = ['admin', 'landing', 'buyer-portal'];

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith('--')) continue;
    const key = arg.slice(2).replaceAll('-', '_');
    const next = argv[index + 1];
    if (!next || next.startsWith('--')) {
      args[key] = true;
    } else {
      args[key] = next;
      index += 1;
    }
  }
  return args;
}

function safeRunId(value) {
  const raw = value || new Date().toISOString().replace(/[:.]/g, '-');
  return String(raw).replace(/[^A-Za-z0-9_.-]/g, '-').slice(0, 120);
}

function relativePath(value) {
  return path.relative(repoRoot, value).replaceAll(path.sep, '/');
}

function parseBoolean(value, defaultValue = false) {
  if (value === undefined) return defaultValue;
  if (value === true) return true;
  return ['1', 'true', 'yes', 'on'].includes(String(value).toLowerCase());
}

function isLoopbackHostname(hostname) {
  const host = hostname.toLowerCase();
  const normalized = host.startsWith('[') && host.endsWith(']') ? host.slice(1, -1) : host;
  if (normalized === 'localhost' || normalized === '::1') return true;
  return net.isIP(normalized) === 4 && normalized.split('.')[0] === '127';
}

function assertLoopbackHttpUrl(label, value) {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || !isLoopbackHostname(url.hostname)) {
    throw new Error(`${label} must stay on loopback HTTP(S), got ${value}`);
  }
  return url;
}

function urlWithPath(label, rawUrl, fallbackPath) {
  const url = assertLoopbackHttpUrl(label, rawUrl);
  if (!url.pathname || url.pathname === '/') url.pathname = fallbackPath;
  return url.toString();
}

function selectTargetIds(rawTargets) {
  if (!rawTargets || rawTargets === 'all') return TARGET_IDS;
  const ids = String(rawTargets)
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  const invalid = ids.filter((id) => !TARGET_IDS.includes(id));
  if (invalid.length) {
    throw new Error(`Unknown target(s): ${invalid.join(', ')}. Valid targets: ${TARGET_IDS.join(', ')}`);
  }
  return [...new Set(ids)];
}

function buildTargets(selectedIds) {
  const definitions = {
    admin: {
      id: 'admin',
      title: 'Operator admin console',
      role: 'Operator / Admin',
      url: urlWithPath('STORMLEAD_ADMIN_URL', process.env.STORMLEAD_ADMIN_URL || 'http://127.0.0.1:8003', '/admin'),
      workflows: [
        'Scan KPI cards, launch-readiness copy, buyer roster, recent workflow runs, timeline viewer, and review controls.',
        'Try an empty or invalid timeline lookup and record whether the error/empty state is understandable.',
        'If local services are seeded, inspect a real synthetic workflow run without contacting homeowners or buyers.',
      ],
      visual_checks: [
        'Does the dashboard hierarchy make the next operator action obvious in the first 10 seconds?',
        'Are review controls visually distinct from read-only KPI/status surfaces?',
        'Do dense tables, payload summaries, and readiness cards stay readable at desktop and narrow widths?',
      ],
      mcp_context: [
        'check_local_services',
        'get_admin_kpis',
        'get_workflow_kpis',
        'list_recent_workflow_runs',
        'observe_chrome_page',
      ],
    },
    landing: {
      id: 'landing',
      title: 'Homeowner landing page',
      role: 'Synthetic Homeowner Lead Submitter',
      url: urlWithPath('STORMLEAD_LANDING_URL', process.env.STORMLEAD_LANDING_URL || 'http://127.0.0.1:8005', '/'),
      workflows: [
        'As a first-time visitor, explain the offer, trust signals, local-demo disclosure, and consent language before entering data.',
        'Try required-field validation, then record focus behavior, error copy, recovery path, and post-submit confidence.',
        'Check mobile viewport usability for thumb reach, form length, and CTA confidence.',
      ],
      visual_checks: [
        'Does the page make synthetic/local proof status clear and avoid implying real service dispatch?',
        'Is the form easy to complete without excess cognitive load?',
        'Are urgency and persuasion ethical rather than dark-patterned?',
      ],
      mcp_context: ['observe_chrome_page', 'run_self_learning_loop'],
    },
    'buyer-portal': {
      id: 'buyer-portal',
      title: 'Buyer portal',
      role: 'Buyer / Contractor',
      url: urlWithPath('STORMLEAD_BUYER_PORTAL_URL', process.env.STORMLEAD_BUYER_PORTAL_URL || 'http://127.0.0.1:8004', '/login'),
      workflows: [
        'Review unauthenticated login, invalid credentials, and explanatory denied states.',
        'With a synthetic buyer from local smoke/Playwright evidence, inspect wallet, lead list, and return review flows; if no synthetic session exists, record a blocker instead of using real credentials.',
        'Check that refill and return language stays synthetic/local and does not imply real payment processing.',
      ],
      visual_checks: [
        'Can a contractor understand current balance, delivered leads, and next required action quickly?',
        'Are wallet and return actions clearly separated from informational sections?',
        'Are empty states useful when no delivered leads or wallet history exists?',
      ],
      mcp_context: ['list_buyers_redacted', 'observe_chrome_page', 'get_evidence_manifest'],
    },
  };

  return selectedIds.map((id) => definitions[id]);
}

function renderTargetList(targets) {
  return targets.map((target) => [
    `## ${target.title}`,
    '',
    `Role: ${target.role}`,
    `URL: ${target.url}`,
    '',
    'Workflows:',
    ...target.workflows.map((item) => `- ${item}`),
    '',
    'Visual and UX checks:',
    ...target.visual_checks.map((item) => `- ${item}`),
    '',
    'Helpful local MCP context:',
    ...target.mcp_context.map((item) => `- ${item}`),
    '',
  ].join('\n')).join('\n');
}

function renderBrief({ runId, runDir, targets }) {
  return [
    '# StormLead UI-TARS / Agent TARS Exploration Brief',
    '',
    `Run ID: ${runId}`,
    `Evidence folder: ${relativePath(runDir)}`,
    '',
    '## Mission',
    '',
    'Act as a local-only AI coworker for StormLead. Explore the browser surfaces like a careful human operator, contractor, and synthetic homeowner. Catch visual, UX, accessibility, copy, empty-state, and workflow confidence issues that normal Playwright assertions may not notice.',
    '',
    'This does not replace required Playwright, smoke, or MCP verification. It adds exploratory evidence and triage notes.',
    '',
    '## Hard Safety Boundaries',
    '',
    '- Stay on loopback HTTP(S) URLs only: localhost, 127.x.x.x, or ::1. Do not use Docker service DNS names, public hostnames, or remote URLs.',
    '- Use synthetic test data only. Do not contact real homeowners, buyers, ad platforms, payment processors, SMS/email/phone providers, or public webhooks.',
    '- Do not read secrets, cookies, auth headers, `.env` files, kubeconfigs, cloud keys, or payment keys.',
    '- Do not mutate production or remote infrastructure. Generated evidence must stay under `testing/runs/`.',
    '- If a step needs credentials or a real external service, stop and record a blocker instead of improvising.',
    '',
    '## How To Work',
    '',
    '- Move slowly enough that screenshots and videos show what a human would notice.',
    '- Use desktop and mobile/narrow viewport checks where practical.',
    '- Capture the viewport width, page state, and screenshot filename for every meaningful observation.',
    '- Prefer semantic interactions: labels, buttons, links, visible text, and obvious controls.',
    '- Record observations as findings, not code changes. A developer can convert findings into edits, tests, backlog, or blockers.',
    '- When MCP tools are available, use them for local context and browser evidence; do not call tools that require production or external access.',
    '- Treat TARS identification as internal evidence disclosure: the review notes should state an AI coworker produced them. Do not add product-facing AI claims unless the product UI itself introduces AI output.',
    '',
    '## UX Methods To Apply',
    '',
    '- UX heuristics review: visibility of system status, match to real-world language, user control, consistency, error prevention, recognition over recall, efficiency, minimalism, error recovery, and help.',
    '- Cognitive-load conversion: check first 10-second comprehension, competing primary actions, terminology burden, visible status, next step clarity, and whether users must remember details from another page.',
    '- Persuasive UX without dark patterns: check for false urgency, misleading scarcity, ambiguous consent, hidden terms, confirm-shaming, pressure before understanding synthetic/local status, and unclear data-use expectations.',
    '- AI trust builders: clearly identify TARS as an AI coworker, preserve operator control, and leave an auditable footprint in this folder.',
    '',
    '## Accessibility Checks',
    '',
    '- Keyboard path and focus order: WCAG 2.1.1, 2.4.3, and 2.4.7.',
    '- Form labels, instructions, validation, and recovery: WCAG 1.3.1, 3.3.1, 3.3.2, and 3.3.3.',
    '- Color contrast and non-color-only status: WCAG 1.4.1 and 1.4.3.',
    '- Name, role, and value for controls: WCAG 4.1.2.',
    '- Responsive readability and no horizontal scrolling at narrow widths: WCAG 1.4.10.',
    '',
    '## Targets',
    '',
    renderTargetList(targets).trimEnd(),
    '',
    '## Evidence To Leave',
    '',
    '- Save screenshots under `screenshots/` with names like `01-admin-kpi-hierarchy.png`; include viewport width and state in the finding.',
    '- Put concise review notes in `reviews/tars-review.md` using the template in this folder.',
    '- Append machine-readable findings to `logs/findings.jsonl`. Use one JSON object per line.',
    '- If another browser/observer run exists, link its local `testing/runs/.../evidence.json` or Chrome summary path.',
    '',
    'Finding JSONL schema:',
    '',
    '```json',
    '{"id":"tars-001","target":"admin","role":"Operator / Admin","task":"Load timeline with invalid ID","viewport":"1440x900","state":"error","severity":"medium","confidence":"high","category":"visual|ux|accessibility|copy|workflow|performance|security|data","heuristic_or_wcag":"WCAG 3.3.3 or Nielsen error recovery","observed":"What happened","expected_user_need":"What the user needed","impact":"Why it matters","steps":["Step 1","Step 2"],"evidence":"screenshots/01-admin-error.png","triage":"edit|test|backlog|blocker","recommendation":"Specific next action"}',
    '```',
    '',
    'Severity guide:',
    '',
    '- `critical`: unsafe external action, secret exposure, or workflow cannot be completed.',
    '- `high`: role workflow likely fails or misleads a user/operator.',
    '- `medium`: meaningful friction, unclear state, visual regression, or missing empty/error guidance.',
    '- `low`: polish issue or future improvement.',
    '',
    '## Done Criteria',
    '',
    '- Every selected target has at least one human-like pass or an explicit blocker.',
    '- Admin/operator, homeowner/visitor, and buyer/contractor perspectives are considered when selected.',
    '- Findings are actionable: each has an edit, test, backlog, or blocker recommendation.',
    '- No evidence includes secrets, real personal data, or public webhook/contact attempts.',
    '',
  ].join('\n');
}

function renderReviewTemplate(targets) {
  return [
    '# TARS Exploration Review',
    '',
    '## Summary',
    '',
    '- Overall result: pass / needs edits / blocked',
    '- Highest severity found: none / low / medium / high / critical',
    '- Evidence folder reviewed:',
    '',
    '## Target Results',
    '',
    ...targets.map((target) => [
      `### ${target.title}`,
      '',
      '- Workflow status: pass / needs edits / blocked',
      '- Screenshots:',
      '- Findings:',
      '- Accessibility checks:',
      '- Human-like task notes:',
      '- Recommended next action: edit / test / backlog / blocker',
      '',
    ].join('\n')),
    '## Cross-Cutting Notes',
    '',
    '- Accessibility:',
    '- Cognitive load:',
    '- Visual hierarchy:',
    '- Copy and trust:',
    '- Dark-pattern risk:',
    '- AI coworker disclosure in evidence:',
    '- Local-only safety:',
    '',
  ].join('\n');
}

function renderLogReadme() {
  return [
    '# TARS Finding Logs',
    '',
    '`findings.jsonl` is intentionally empty until UI-TARS/Agent TARS or a human reviewer appends findings.',
    '',
    'Append one JSON object per line using this shape:',
    '',
    '```json',
    '{"id":"tars-001","target":"admin","role":"Operator / Admin","task":"Review KPI cards","viewport":"1440x900","state":"default","severity":"medium","confidence":"high","category":"ux","heuristic_or_wcag":"Nielsen visibility of system status","observed":"The next action is unclear","expected_user_need":"Operator needs a clear review priority","impact":"Slower review and higher missed-lead risk","steps":["Open /admin","Scan KPI row"],"evidence":"screenshots/01-admin.png","triage":"edit","recommendation":"Add clearer review CTA copy"}',
    '```',
    '',
  ].join('\n');
}

const args = parseArgs(process.argv.slice(2));
const selectedIds = selectTargetIds(args.targets);
const targets = buildTargets(selectedIds);
const runId = `${safeRunId(args.run_id)}-tars-exploration`;
const runDir = path.join(runsDir, runId);
const screenshotsDir = path.join(runDir, 'screenshots');
const logsDir = path.join(runDir, 'logs');
const reviewsDir = path.join(runDir, 'reviews');
const force = parseBoolean(args.force, false);

if (existsSync(runDir) && !force) {
  throw new Error(`${relativePath(runDir)} already exists. Use a new --run-id or pass --force true to overwrite local TARS scaffold files.`);
}

mkdirSync(screenshotsDir, { recursive: true });
mkdirSync(logsDir, { recursive: true });
mkdirSync(reviewsDir, { recursive: true });

const briefPath = path.join(runDir, 'tars-brief.md');
const promptPath = path.join(runDir, 'runner-prompt.md');
const targetsPath = path.join(runDir, 'targets.json');
const reviewTemplatePath = path.join(reviewsDir, 'tars-review-template.md');
const evidencePath = path.join(runDir, 'evidence.json');
const findingsPath = path.join(logsDir, 'findings.jsonl');
const logReadmePath = path.join(logsDir, 'README.md');

const brief = renderBrief({ runId, runDir, targets });
writeFileSync(briefPath, brief, 'utf8');
writeFileSync(promptPath, brief, 'utf8');
writeFileSync(targetsPath, JSON.stringify({ schema_version: 1, local_only: true, run_id: runId, targets }, null, 2), 'utf8');
writeFileSync(reviewTemplatePath, renderReviewTemplate(targets), 'utf8');
writeFileSync(findingsPath, '', 'utf8');
writeFileSync(logReadmePath, renderLogReadme(), 'utf8');

const evidence = {
  schema_version: 1,
  workflow: 'ui-tars-agent-tars-exploration-brief',
  run_id: runId,
  status: 'prepared',
  local_only: true,
  generated_at: new Date().toISOString(),
  target_ids: selectedIds,
  artifacts: {
    brief: relativePath(briefPath),
    runner_prompt: relativePath(promptPath),
    targets: relativePath(targetsPath),
    review_template: relativePath(reviewTemplatePath),
    findings_jsonl: relativePath(findingsPath),
    screenshots_dir: relativePath(screenshotsDir),
  },
  safety: {
    loopback_only: true,
    synthetic_only: true,
    production_side_effects_allowed: false,
    external_contact_allowed: false,
  },
};
writeFileSync(evidencePath, JSON.stringify(evidence, null, 2), 'utf8');

console.log(JSON.stringify({
  ok: true,
  local_only: true,
  run_id: runId,
  path: relativePath(runDir),
  evidence_manifest: relativePath(evidencePath),
  brief: relativePath(briefPath),
  targets: selectedIds,
}, null, 2));
