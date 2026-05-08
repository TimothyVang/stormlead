#!/usr/bin/env node

import { execFile } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);
const repoRoot = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const runsDir = path.join(repoRoot, 'testing', 'runs');
const currentDir = path.join(runsDir, 'free-build-current');

function commandName(name) {
  return process.platform === 'win32' ? `${name}.cmd` : name;
}

function relativePath(value) {
  return path.relative(repoRoot, value).replaceAll(path.sep, '/');
}

function trimOutput(value, maxLength = 12000) {
  const text = String(value ?? '');
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}\n...[truncated ${text.length - maxLength} chars]`;
}

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

async function runCommand(label, command, args, timeoutSeconds = 30) {
  const startedAt = new Date();
  const usesWindowsCommandShim = process.platform === 'win32' && command.endsWith('.cmd');
  const executable = usesWindowsCommandShim ? process.env.ComSpec || 'cmd.exe' : command;
  const executableArgs = usesWindowsCommandShim ? ['/d', '/c', command, ...args] : args;
  try {
    const result = await execFileAsync(executable, executableArgs, {
      cwd: repoRoot,
      encoding: 'utf8',
      timeout: timeoutSeconds * 1000,
      maxBuffer: 10 * 1024 * 1024,
      windowsHide: true,
    });
    return {
      label,
      ok: true,
      command: [command, ...args],
      started_at: startedAt.toISOString(),
      finished_at: new Date().toISOString(),
      stdout: trimOutput(result.stdout),
      stderr: trimOutput(result.stderr),
    };
  } catch (error) {
    return {
      label,
      ok: false,
      command: [command, ...args],
      started_at: startedAt.toISOString(),
      finished_at: new Date().toISOString(),
      finished_with: error?.signal ? 'signal' : 'exit',
      exit_code: typeof error?.code === 'number' ? error.code : null,
      signal: error?.signal ?? null,
      stdout: trimOutput(error?.stdout),
      stderr: trimOutput(error?.stderr),
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

async function checkEndpoint(name, url) {
  const startedAt = new Date();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    const response = await fetch(url, { signal: controller.signal });
    const text = await response.text();
    let body = text;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      // keep text body
    }
    return {
      name,
      ok: response.ok,
      url,
      status: response.status,
      started_at: startedAt.toISOString(),
      finished_at: new Date().toISOString(),
      body,
    };
  } catch (error) {
    return {
      name,
      ok: false,
      url,
      started_at: startedAt.toISOString(),
      finished_at: new Date().toISOString(),
      error: error instanceof Error ? error.message : String(error),
    };
  } finally {
    clearTimeout(timeout);
  }
}

function readJsonIfExists(filePath) {
  if (!existsSync(filePath)) return null;
  try {
    return JSON.parse(readFileSync(filePath, 'utf8'));
  } catch (error) {
    return { parse_error: error instanceof Error ? error.message : String(error) };
  }
}

function analyzePlaywrightResults() {
  const filePath = path.join(repoRoot, 'testing', 'logs', 'playwright-results.json');
  const parsed = readJsonIfExists(filePath);
  if (!parsed) {
    return {
      ok: false,
      status: 'missing',
      path: relativePath(filePath),
      finding: 'No Playwright JSON result exists yet; regenerate browser proof.',
    };
  }
  if (parsed.parse_error) {
    return {
      ok: false,
      status: 'invalid_json',
      path: relativePath(filePath),
      finding: `Playwright JSON could not be parsed: ${parsed.parse_error}`,
    };
  }
  const stats = parsed.stats || {};
  const executed = Number(stats.expected || 0) + Number(stats.unexpected || 0) + Number(stats.flaky || 0);
  const ok = executed > 0 && Number(stats.unexpected || 0) === 0;
  return {
    ok,
    status: ok ? 'valid_pass_or_expected_only' : 'not_valid_proof',
    path: relativePath(filePath),
    stats,
    executed,
    finding: ok
      ? `Playwright JSON has ${executed} executed tests and no unexpected failures.`
      : `Playwright JSON is not proof yet: executed=${executed}, unexpected=${stats.unexpected ?? 0}.`,
  };
}

async function listEvidenceRuns(limit = 8) {
  let entries = [];
  try {
    entries = await fs.readdir(runsDir, { withFileTypes: true });
  } catch (error) {
    if (error?.code === 'ENOENT') return [];
    throw error;
  }
  const dirs = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const dir = path.join(runsDir, entry.name);
    const stat = await fs.stat(dir);
    dirs.push({ name: entry.name, dir, stat });
  }
  dirs.sort((a, b) => b.stat.mtimeMs - a.stat.mtimeMs);
  return Promise.all(dirs.slice(0, limit).map(async (entry) => {
    const evidencePath = path.join(entry.dir, 'evidence.json');
    const summaryPath = path.join(entry.dir, 'self-learning-summary.json');
    return {
      run_id: entry.name,
      path: relativePath(entry.dir),
      modified_at: entry.stat.mtime.toISOString(),
      evidence_manifest: existsSync(evidencePath) ? relativePath(evidencePath) : null,
      self_learning_summary: existsSync(summaryPath) ? relativePath(summaryPath) : null,
    };
  }));
}

function sourceCheck(name, relativeFile, predicate, passDetail, failDetail) {
  const filePath = path.join(repoRoot, relativeFile);
  if (!existsSync(filePath)) {
    return { name, ok: false, path: relativeFile, detail: `Missing ${relativeFile}` };
  }
  const content = readFileSync(filePath, 'utf8');
  const ok = predicate(content);
  return { name, ok, path: relativeFile, detail: ok ? passDetail : failDetail };
}

function analyzeKnownGaps() {
  return [
    sourceCheck(
      'Class C/D leads are blocked before auction entry',
      'services/ping-post/src/ping_post/auction.py',
      (content) => {
        const fnStart = content.indexOf('def _lead_can_enter_auction');
        const fnEnd = content.indexOf('\ndef ', fnStart + 1);
        const fnBody = content.slice(fnStart, fnEnd === -1 ? undefined : fnEnd);
        const leadClassIndex = fnBody.indexOf('lead_class');
        const classGateIndex = fnBody.indexOf('class_requires_review');
        const scoreRouteIndex = fnBody.indexOf('score >= ab_min');
        return leadClassIndex !== -1
          && classGateIndex !== -1
          && scoreRouteIndex !== -1
          && leadClassIndex < scoreRouteIndex
          && classGateIndex < scoreRouteIndex;
      },
      'Auction entry gate checks lead class before score-based routing.',
      'Auction entry gate may allow high-score class C/D leads until later buyer filtering.',
    ),
    sourceCheck(
      'Admin KPIs include buyer adjustments and campaign margin',
      'services/ping-post/src/ping_post/api.py',
      (content) => content.includes('buyer_adjustments_cents') && content.includes('campaign_margin_cents'),
      'Admin KPI response includes buyer adjustment and campaign margin fields.',
      'Admin KPI response does not expose buyer adjustment and campaign margin fields.',
    ),
    sourceCheck(
      'Buyer daily report includes delivered lead details',
      'services/ping-post/src/ping_post/api.py',
      (content) => content.includes('delivered_lead_details'),
      'Buyer daily report includes delivered lead details for portal/reporting proof.',
      'Buyer daily report only exposes counts, not delivered lead details.',
    ),
    sourceCheck(
      'Readiness includes synthetic call tracking proof',
      'services/ping-post/src/ping_post/api.py',
      (content) => content.includes('synthetic_call_tracking_ingested') || content.includes('call_tracking'),
      'Readiness code references call-tracking proof.',
      'Readiness does not appear to include call-tracking proof.',
    ),
    sourceCheck(
      'Readiness includes buyer wallet runway proof',
      'services/ping-post/src/ping_post/api.py',
      (content) => content.includes('buyer_wallet_runway_covers_pause_threshold'),
      'Readiness requires scoped buyers to clear the wallet runway threshold.',
      'Readiness does not appear to require buyer wallet runway coverage.',
    ),
    sourceCheck(
      'Operator API surfaces have an app-level gate',
      'services/ping-post/src/ping_post/api.py',
      (content) => content.includes('operator_surface_gate') && content.includes('STORMLEAD_OPERATOR_TOKEN'),
      'Admin and funding APIs have an app-level operator-token gate.',
      'Admin and funding APIs do not appear to have an app-level operator-token gate.',
    ),
    sourceCheck(
      'Buyer portal validates API keys before setting cookies',
      'apps/buyer-portal/main.py',
      (content) => content.includes('Buyer ID or API key was rejected') && content.includes('/wallet'),
      'Buyer portal login validates buyer credentials before issuing cookies.',
      'Buyer portal login does not appear to validate buyer credentials before issuing cookies.',
    ),
  ];
}

function computeStatus({ compose, mcpSyntax, services, playwright, knownGaps }) {
  const blockers = [];
  const warnings = [];
  if (!compose.ok) blockers.push('Docker Compose config validation failed.');
  if (!mcpSyntax.ok) blockers.push('StormLead MCP syntax check failed.');
  const downServices = services.filter((service) => !service.ok);
  const blockedServices = downServices.filter((service) => service.name !== 'litellm readiness');
  const warningServices = downServices.filter((service) => service.name === 'litellm readiness');
  if (blockedServices.length) {
    blockers.push(`Local services unreachable: ${blockedServices.map((service) => service.name).join(', ')}.`);
  }
  if (warningServices.length) {
    warnings.push(`Optional local services unreachable: ${warningServices.map((service) => service.name).join(', ')}.`);
  }
  if (!playwright.ok) warnings.push(playwright.finding);
  for (const gap of knownGaps.filter((item) => !item.ok)) warnings.push(gap.detail);

  if (blockers.length) {
    return {
      status: 'blocked',
      blockers,
      warnings,
      next_command: 'docker compose --env-file .env.example -f infra/compose/dev/docker-compose.yml --profile pipeline up -d',
      resume_phase: 'local_stack_recovery',
    };
  }
  if (knownGaps.some((item) => !item.ok)) {
    return {
      status: 'resume_needed',
      blockers,
      warnings,
      next_command: 'Fix the highest-priority launch-gate source gap, then run npm run check:build-status.',
      resume_phase: 'launch_gate_gap_fixes',
    };
  }
  if (!playwright.ok) {
    return {
      status: 'resume_needed',
      blockers,
      warnings,
      next_command: 'npm run test:playwright -- --project=chromium --reporter=line',
      resume_phase: 'browser_proof_regeneration',
    };
  }
  return {
    status: 'ready',
    blockers,
    warnings,
    next_command: 'npm run learn:loop:api',
    resume_phase: 'self_learning_evidence',
  };
}

function markdownList(items) {
  return items.length ? items.map((item) => `- ${item}`).join('\n') : '- None.';
}

function writeMarkdown(summary, filePath) {
  const lines = [
    '# Free Build Status Check',
    '',
    `Run ID: ${summary.run_id}`,
    `Status: ${summary.status}`,
    `Resume phase: ${summary.resume_phase}`,
    `Next command: \`${summary.next_command}\``,
    '',
    '## Blockers',
    markdownList(summary.blockers),
    '',
    '## Warnings',
    markdownList(summary.warnings),
    '',
    '## Local Services',
    ...summary.services.map((service) => `- ${service.ok ? 'PASS' : 'FAIL'} ${service.name}: ${service.url}${service.status ? ` (${service.status})` : ''}${service.error ? ` - ${service.error}` : ''}`),
    '',
    '## Static Checks',
    `- ${summary.compose.ok ? 'PASS' : 'FAIL'} Compose config: \`${summary.compose.command.join(' ')}\``,
    `- ${summary.mcp_syntax.ok ? 'PASS' : 'FAIL'} MCP syntax: \`${summary.mcp_syntax.command.join(' ')}\``,
    `- ${summary.playwright.ok ? 'PASS' : 'WARN'} Playwright result proof: ${summary.playwright.finding}`,
    '',
    '## Known Launch-Gate Gaps',
    ...summary.known_gaps.map((gap) => `- ${gap.ok ? 'PASS' : 'WARN'} ${gap.name}: ${gap.detail} (${gap.path})`),
    '',
    '## Recent Evidence Runs',
    ...summary.recent_evidence_runs.map((run) => `- ${run.run_id}: \`${run.path}\``),
    '',
  ];
  writeFileSync(filePath, lines.join('\n'));
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const runId = `${safeRunId(args.run_id)}-build-check`;
  const runDir = path.join(runsDir, runId);
  mkdirSync(runDir, { recursive: true });
  mkdirSync(currentDir, { recursive: true });

  const startedAt = new Date();
  const [compose, mcpSyntax, services, recentEvidenceRuns] = await Promise.all([
    runCommand('Compose config', 'docker', ['compose', '--env-file', '.env.example', '-f', 'infra/compose/dev/docker-compose.yml', 'config', '--quiet'], 45),
    runCommand('StormLead MCP syntax', process.execPath, ['--check', 'tools/mcp/stormlead-local-ops.mjs'], 30),
    Promise.all([
      checkEndpoint('ping-post health', process.env.STORMLEAD_ADMIN_URL ? `${process.env.STORMLEAD_ADMIN_URL.replace(/\/$/, '')}/healthz` : 'http://127.0.0.1:8003/healthz'),
      checkEndpoint('ping-post ready', process.env.STORMLEAD_ADMIN_URL ? `${process.env.STORMLEAD_ADMIN_URL.replace(/\/$/, '')}/readyz` : 'http://127.0.0.1:8003/readyz'),
      checkEndpoint('form-receiver health', process.env.STORMLEAD_FORM_RECEIVER_URL ? `${process.env.STORMLEAD_FORM_RECEIVER_URL.replace(/\/$/, '')}/healthz` : 'http://127.0.0.1:8002/healthz'),
      checkEndpoint('litellm readiness', process.env.STORMLEAD_LITELLM_URL ? `${process.env.STORMLEAD_LITELLM_URL.replace(/\/$/, '')}/health/readiness` : 'http://127.0.0.1:4000/health/readiness'),
    ]),
    listEvidenceRuns(),
  ]);
  const playwright = analyzePlaywrightResults();
  const knownGaps = analyzeKnownGaps();
  const status = computeStatus({ compose, mcpSyntax, services, playwright, knownGaps });

  const summary = {
    schema_version: 1,
    run_id: runId,
    ok: status.status === 'ready',
    status: status.status,
    started_at: startedAt.toISOString(),
    finished_at: new Date().toISOString(),
    resume_phase: status.resume_phase,
    next_command: status.next_command,
    blockers: status.blockers,
    warnings: status.warnings,
    compose,
    mcp_syntax: mcpSyntax,
    services,
    playwright,
    known_gaps: knownGaps,
    recent_evidence_runs: recentEvidenceRuns,
    artifacts: {
      run_dir: relativePath(runDir),
      summary_json: relativePath(path.join(runDir, 'build-check-summary.json')),
      summary_markdown: relativePath(path.join(runDir, 'build-check.md')),
      current_state: relativePath(path.join(currentDir, 'state.json')),
    },
  };

  writeFileSync(path.join(runDir, 'build-check-summary.json'), JSON.stringify(summary, null, 2) + '\n');
  writeFileSync(path.join(currentDir, 'state.json'), JSON.stringify(summary, null, 2) + '\n');
  writeMarkdown(summary, path.join(runDir, 'build-check.md'));
  writeMarkdown(summary, path.join(currentDir, 'status.md'));

  console.log(JSON.stringify({
    status: summary.status,
    resume_phase: summary.resume_phase,
    next_command: summary.next_command,
    blockers: summary.blockers,
    warnings: summary.warnings,
    artifacts: summary.artifacts,
  }, null, 2));
  if (args.fail_on_blocked && summary.status === 'blocked') process.exitCode = 1;
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
