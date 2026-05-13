#!/usr/bin/env node

import { chromium } from '@playwright/test';
import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const runsDir = path.join(repoRoot, 'testing', 'runs');

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

function parseBoolean(value, defaultValue) {
  if (value === undefined) return defaultValue;
  if (value === true) return true;
  return ['1', 'true', 'yes', 'on'].includes(String(value).toLowerCase());
}

function safeRunId(value) {
  return String(value || '').replace(/[^A-Za-z0-9_.-]/g, '-').slice(0, 160);
}

function relativePath(value) {
  return path.relative(repoRoot, value).replaceAll(path.sep, '/');
}

function isLoopbackHostname(hostname) {
  const host = hostname.toLowerCase();
  const normalized = host.startsWith('[') && host.endsWith(']') ? host.slice(1, -1) : host;
  if (normalized === 'localhost' || normalized === '::1') return true;
  return net.isIP(normalized) === 4 && normalized.split('.')[0] === '127';
}

const SENSITIVE_EVENT_KEY = /authorization|cookie|credential|headers|password|payload|secret|token|api[_-]?key|webhook/i;
const SENSITIVE_TEXT = /(authorization|cookie|password|secret|token|api[_-]?key|webhook)(["'\s:=]+)([^"'\s,}]+)/gi;

function redactText(value) {
  return String(value ?? '').replace(SENSITIVE_TEXT, '$1$2[REDACTED]');
}

function redactUrl(value) {
  try {
    const url = new URL(value);
    url.username = '';
    url.password = '';
    for (const key of [...url.searchParams.keys()]) {
      if (SENSITIVE_EVENT_KEY.test(key)) url.searchParams.set(key, '[REDACTED]');
    }
    return url.toString();
  } catch {
    return redactText(value);
  }
}

function isAllowedBrowserRequest(rawUrl) {
  try {
    const url = new URL(rawUrl);
    if (['about:', 'blob:', 'data:'].includes(url.protocol)) return true;
    if (!['http:', 'https:', 'ws:', 'wss:'].includes(url.protocol)) return false;
    return isLoopbackHostname(url.hostname);
  } catch {
    return false;
  }
}

async function enforceLoopbackOnly(context) {
  await context.route('**/*', async (route) => {
    const requestUrl = route.request().url();
    if (!isAllowedBrowserRequest(requestUrl)) {
      await route.abort('blockedbyclient');
      return;
    }
    await route.continue();
  });
}

function assertLoopbackHttpUrl(label, value) {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || !isLoopbackHostname(url.hostname)) {
    throw new Error(`${label} must stay on loopback HTTP(S), got ${value}`);
  }
  return url;
}

function resolveRunDir(args) {
  if (args.run_dir) {
    const resolved = path.resolve(repoRoot, String(args.run_dir));
    if (!resolved.startsWith(path.resolve(runsDir) + path.sep)) {
      throw new Error('--run-dir must point inside testing/runs');
    }
    return resolved;
  }
  if (args.run_id) {
    const id = safeRunId(args.run_id);
    const exact = path.join(runsDir, id);
    const suffixed = path.join(runsDir, `${id}-tars-exploration`);
    if (existsSync(exact)) return exact;
    return suffixed;
  }

  const candidates = readdirSync(runsDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name.endsWith('-tars-exploration'))
    .map((entry) => path.join(runsDir, entry.name))
    .sort((left, right) => statSync(right).mtimeMs - statSync(left).mtimeMs);
  if (!candidates.length) throw new Error('No TARS exploration package found. Run npm run tars:brief first.');
  return candidates[0];
}

function readJson(filePath) {
  return JSON.parse(readFileSync(filePath, 'utf8'));
}

function appendFinding(findingsPath, finding) {
  appendFileSync(findingsPath, `${JSON.stringify(finding)}\n`, 'utf8');
}

function writeReview({ reviewPath, results, findings }) {
  const highest = findings.some((finding) => finding.severity === 'critical') ? 'critical'
    : findings.some((finding) => finding.severity === 'high') ? 'high'
      : findings.some((finding) => finding.severity === 'medium') ? 'medium'
        : findings.some((finding) => finding.severity === 'low') ? 'low'
          : 'none';
  const lines = [
    '# TARS Exploration Review',
    '',
    '## Summary',
    '',
    `- Overall result: ${findings.length ? 'needs edits' : 'pass'}`,
    `- Highest severity found: ${highest}`,
    '- Evidence produced by: StormLead local TARS runner bridge consuming `runner-prompt.md`.',
    '',
    '## Target Results',
    '',
  ];

  for (const result of results) {
    lines.push(`### ${result.title}`);
    lines.push('');
    lines.push(`- Workflow status: ${result.status}`);
    lines.push(`- Screenshots: ${result.screenshots.join(', ') || 'none'}`);
    lines.push(`- Findings: ${result.findings.length ? result.findings.join(', ') : 'none'}`);
    lines.push(`- Human-like task notes: ${result.notes}`);
    lines.push(`- Recommended next action: ${result.findings.length ? 'edit / test' : 'none'}`);
    lines.push('');
  }

  lines.push('## Cross-Cutting Notes');
  lines.push('');
  lines.push('- Local-only safety: all targets were checked for loopback HTTP(S) before browser launch.');
  lines.push('- AI coworker disclosure in evidence: this is a deterministic local runner bridge, not an external UI-TARS/Agent TARS model run.');
  lines.push('');
  writeFileSync(reviewPath, lines.join('\n'), 'utf8');
}

async function screenshot(page, screenshotsDir, filename) {
  const screenshotPath = path.join(screenshotsDir, filename);
  await page.screenshot({ path: screenshotPath, fullPage: false, timeout: 5000 });
  return relativePath(screenshotPath);
}

async function openPage(context, target) {
  const page = await context.newPage();
  const events = [];
  page.on('console', (message) => {
    if (message.type() === 'error') events.push({ type: 'console', text: redactText(message.text()), url: redactUrl(page.url()) });
  });
  page.on('pageerror', (error) => events.push({ type: 'pageerror', text: redactText(error.message), url: redactUrl(page.url()) }));
  page.on('response', (response) => {
    if (response.status() >= 400) {
      events.push({ type: 'http', status: response.status(), url: redactUrl(response.url()), method: response.request().method() });
    }
  });
  page.on('requestfailed', (request) => {
    if (!isAllowedBrowserRequest(request.url())) {
      events.push({ type: 'external_blocked', url: redactUrl(request.url()), method: request.method() });
    }
  });
  await page.goto(target.url, { waitUntil: 'domcontentloaded', timeout: 20_000 });
  await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => undefined);
  return { page, events };
}

function buildFinding({ id, target, severity, category, observed, expectedUserNeed, impact, steps, evidence, triage, recommendation }) {
  return {
    id,
    target: target.id,
    role: target.role,
    task: target.title,
    viewport: '1440x900',
    state: severity === 'high' ? 'blocked' : 'observed',
    severity,
    confidence: 'high',
    category,
    heuristic_or_wcag: 'Nielsen error recovery / WCAG 3.3.3',
    observed,
    expected_user_need: expectedUserNeed,
    impact,
    steps,
    evidence,
    triage,
    recommendation,
  };
}

async function exploreAdmin(context, target, paths, nextFindingId) {
  const { page, events } = await openPage(context, target);
  const screenshots = [];
  const findings = [];
  await page.locator('#timeline-form').waitFor({ state: 'visible', timeout: 10_000 });
  screenshots.push(await screenshot(page, paths.screenshotsDir, '01-admin-initial.png'));
  await page.locator('#timeline-lead-id').fill('not-a-uuid');
  await page.locator('#timeline-form button[type="submit"]').click();
  await page.waitForTimeout(800);
  screenshots.push(await screenshot(page, paths.screenshotsDir, '02-admin-invalid-timeline.png'));
  const summary = await page.locator('#timeline-summary').innerText();
  const invalidFetch = events.find((event) => event.url.includes('/not-a-uuid/timeline'));
  if (!/valid UUID/i.test(summary) || invalidFetch) {
    findings.push(buildFinding({
      id: `local-tars-${String(nextFindingId()).padStart(3, '0')}`,
      target,
      severity: 'medium',
      category: 'ux',
      observed: invalidFetch
        ? 'Invalid timeline input still reached the timeline API and produced a browser error.'
        : 'Invalid timeline input did not present clear UUID recovery copy.',
      expectedUserNeed: 'Operator needs client-side validation and a readable recovery message before any timeline fetch.',
      impact: 'Invalid input can look like an application failure during operator review.',
      steps: ['Open /admin', 'Enter not-a-uuid in Lead ID', 'Click Load Timeline'],
      evidence: screenshots.at(-1),
      triage: 'edit',
      recommendation: 'Keep invalid Lead ID submissions on the page and show UUID-specific recovery copy.',
    }));
  }
  await page.close();
  return { title: target.title, status: findings.length ? 'needs edits' : 'pass', screenshots, findings, notes: 'Reviewed dashboard load and invalid timeline recovery.' };
}

async function exploreLanding(context, target, paths, nextFindingId) {
  const { page, events } = await openPage(context, target);
  const screenshots = [];
  const findings = [];
  await page.locator('[data-testid="local-lead-form"], [data-testid="local-demo-disabled"]').first().waitFor({ state: 'visible', timeout: 10_000 });
  screenshots.push(await screenshot(page, paths.screenshotsDir, '03-landing-ready.png'));
  const form = page.locator('[data-testid="local-lead-form"]');
  if (await form.count()) {
    const nameInput = page.locator('input[name="name"]');
    await nameInput.fill('');
    await page.locator('[data-testid="local-lead-submit"]').click();
    await page.waitForTimeout(500);
    screenshots.push(await screenshot(page, paths.screenshotsDir, '04-landing-required-validation.png'));
    const validationMessage = await nameInput.evaluate((input) => input.validationMessage);
    if (!validationMessage) {
      findings.push(buildFinding({
        id: `local-tars-${String(nextFindingId()).padStart(3, '0')}`,
        target,
        severity: 'medium',
        category: 'accessibility',
        observed: 'Required name validation did not expose a browser validation message.',
        expectedUserNeed: 'Synthetic homeowner needs clear required-field recovery before submitting local proof data.',
        impact: 'Missing validation feedback can reduce form completion confidence.',
        steps: ['Open landing page', 'Clear Name', 'Submit synthetic lead'],
        evidence: screenshots.at(-1),
        triage: 'edit',
        recommendation: 'Ensure required fields expose visible and assistive validation feedback.',
      }));
    }
  }
  const unexpectedErrors = events;
  if (unexpectedErrors.length) {
    findings.push(buildFinding({
      id: `local-tars-${String(nextFindingId()).padStart(3, '0')}`,
      target,
      severity: 'medium',
      category: 'workflow',
      observed: `Unexpected browser errors occurred: ${unexpectedErrors.map((event) => event.text || `${event.status} ${event.url}`).join('; ')}`,
      expectedUserNeed: 'Landing page should load and validate without console or network failures.',
      impact: 'Browser errors can indicate broken local proof or confusing visitor state.',
      steps: ['Open landing page', 'Exercise required-field validation'],
      evidence: screenshots.at(-1),
      triage: 'test',
      recommendation: 'Inspect browser logs and add a regression test for the failing resource or script.',
    }));
  }
  await page.close();
  return { title: target.title, status: findings.length ? 'needs edits' : 'pass', screenshots, findings, notes: 'Reviewed first visible form state and required-field validation.' };
}

async function exploreBuyer(context, target, paths, nextFindingId) {
  const { page } = await openPage(context, target);
  const screenshots = [];
  const findings = [];
  await page.locator('form[aria-label="buyer login form"]').waitFor({ state: 'visible', timeout: 10_000 });
  screenshots.push(await screenshot(page, paths.screenshotsDir, '05-buyer-login-ready.png'));
  await page.locator('input[name="buyer_id"]').fill('00000000-0000-0000-0000-000000000000');
  await page.locator('input[name="buyer_api_key"]').fill('synthetic-invalid-key');
  await page.locator('button[type="submit"]').click();
  await page.waitForTimeout(800);
  screenshots.push(await screenshot(page, paths.screenshotsDir, '06-buyer-invalid-credentials.png'));
  if (!(await page.getByText('Access denied').count())) {
    findings.push(buildFinding({
      id: `local-tars-${String(nextFindingId()).padStart(3, '0')}`,
      target,
      severity: 'medium',
      category: 'workflow',
      observed: 'Invalid buyer credentials did not produce visible denied-state copy.',
      expectedUserNeed: 'Contractor needs a clear denied state without using real credentials.',
      impact: 'Unclear login failure can look like a broken portal or missing account setup.',
      steps: ['Open buyer login', 'Enter invalid synthetic credentials', 'Submit'],
      evidence: screenshots.at(-1),
      triage: 'edit',
      recommendation: 'Render explicit access-denied copy and recovery guidance for invalid credentials.',
    }));
  }
  await page.close();
  return { title: target.title, status: findings.length ? 'needs edits' : 'pass', screenshots, findings, notes: 'Reviewed unauthenticated login and invalid credential denial.' };
}

const args = parseArgs(process.argv.slice(2));
const runDir = resolveRunDir(args);
const runnerPromptPath = path.join(runDir, 'runner-prompt.md');
const targetsPath = path.join(runDir, 'targets.json');
const evidencePath = path.join(runDir, 'evidence.json');
const logsDir = path.join(runDir, 'logs');
const reviewsDir = path.join(runDir, 'reviews');
const screenshotsDir = path.join(runDir, 'screenshots');
const findingsPath = path.join(logsDir, 'findings.jsonl');
const summaryPath = path.join(logsDir, 'tars-runner-summary.json');
const reviewPath = path.join(reviewsDir, 'tars-review.md');
const headless = parseBoolean(args.headless, true);
const selectedTargets = String(args.targets || '')
  .split(',')
  .map((target) => target.trim())
  .filter(Boolean);

for (const filePath of [runnerPromptPath, targetsPath, evidencePath]) {
  if (!existsSync(filePath)) throw new Error(`Missing TARS package artifact: ${relativePath(filePath)}`);
}
mkdirSync(logsDir, { recursive: true });
mkdirSync(reviewsDir, { recursive: true });
mkdirSync(screenshotsDir, { recursive: true });

const runnerPrompt = readFileSync(runnerPromptPath, 'utf8');
const targetsManifest = readJson(targetsPath);
const evidence = readJson(evidencePath);
if (!targetsManifest.local_only || !evidence.local_only || !evidence.safety?.loopback_only) {
  throw new Error('Refusing to run: TARS package must be marked local_only with loopback safety.');
}

const targets = targetsManifest.targets
  .filter((target) => !selectedTargets.length || selectedTargets.includes(target.id));
for (const target of targets) {
  target.url = assertLoopbackHttpUrl(target.id, target.url).toString();
}
if (!targets.length) throw new Error('No selected targets to explore.');

let findingCounter = 1;
const nextFindingId = () => findingCounter++;
const startedAt = new Date().toISOString();
const browser = await chromium.launch({ headless });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await enforceLoopbackOnly(context);
const results = [];
const findings = [];

try {
  for (const target of targets) {
    let result;
    if (target.id === 'admin') result = await exploreAdmin(context, target, { screenshotsDir }, nextFindingId);
    else if (target.id === 'landing') result = await exploreLanding(context, target, { screenshotsDir }, nextFindingId);
    else if (target.id === 'buyer-portal') result = await exploreBuyer(context, target, { screenshotsDir }, nextFindingId);
    else {
      const finding = buildFinding({
        id: `local-tars-${String(nextFindingId()).padStart(3, '0')}`,
        target,
        severity: 'high',
        category: 'workflow',
        observed: `No local runner workflow exists for target ${target.id}.`,
        expectedUserNeed: 'Each selected target needs at least one human-like pass or explicit blocker.',
        impact: 'Target coverage is incomplete.',
        steps: ['Load TARS package', `Select target ${target.id}`],
        evidence: relativePath(targetsPath),
        triage: 'blocker',
        recommendation: 'Add a target runner implementation.',
      });
      result = { title: target.title, status: 'blocked', screenshots: [], findings: [finding], notes: 'No local runner implementation.' };
    }
    results.push({ ...result, findings: result.findings.map((finding) => finding.id) });
    findings.push(...result.findings);
  }
} finally {
  await browser.close().catch(() => undefined);
}

for (const finding of findings) appendFinding(findingsPath, finding);
writeReview({ reviewPath, results, findings });

const summary = {
  schema_version: 1,
  ok: true,
  local_only: true,
  run_id: targetsManifest.run_id,
  runner: 'stormlead-local-tars-runner',
  runner_prompt_consumed: runnerPrompt.length > 0,
  started_at: startedAt,
  finished_at: new Date().toISOString(),
  targets: targets.map((target) => target.id),
  finding_count: findings.length,
  findings: findings.map((finding) => finding.id),
  artifacts: {
    run_dir: relativePath(runDir),
    runner_prompt: relativePath(runnerPromptPath),
    targets: relativePath(targetsPath),
    findings_jsonl: relativePath(findingsPath),
    review: relativePath(reviewPath),
    screenshots_dir: relativePath(screenshotsDir),
    summary: relativePath(summaryPath),
  },
};

evidence.status = 'explored';
evidence.explored_at = summary.finished_at;
evidence.runner = {
  name: summary.runner,
  runner_prompt_consumed: summary.runner_prompt_consumed,
  finding_count: summary.finding_count,
};
evidence.artifacts = { ...evidence.artifacts, local_runner_summary: relativePath(summaryPath), local_runner_review: relativePath(reviewPath) };
writeFileSync(evidencePath, JSON.stringify(evidence, null, 2), 'utf8');
writeFileSync(summaryPath, JSON.stringify(summary, null, 2), 'utf8');
console.log(JSON.stringify(summary, null, 2));
