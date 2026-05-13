#!/usr/bin/env node

import { execFile } from 'node:child_process';
import { promises as fs } from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';

const execFileAsync = promisify(execFile);
const repoRoot = path.resolve(fileURLToPath(new URL('../..', import.meta.url)));
const runsDir = path.join(repoRoot, 'testing', 'runs');
const adminBaseUrl = assertLoopbackBaseUrl('STORMLEAD_ADMIN_URL', process.env.STORMLEAD_ADMIN_URL || 'http://127.0.0.1:8003');
const formReceiverBaseUrl = assertLoopbackBaseUrl('STORMLEAD_FORM_RECEIVER_URL', process.env.STORMLEAD_FORM_RECEIVER_URL || 'http://127.0.0.1:8002');
const litellmBaseUrl = assertLoopbackBaseUrl('STORMLEAD_LITELLM_URL', process.env.STORMLEAD_LITELLM_URL || 'http://127.0.0.1:4000');

const server = new McpServer({
  name: 'stormlead-local-ops',
  version: '0.1.0',
});

function jsonResult(value) {
  return {
    content: [{ type: 'text', text: JSON.stringify(value, null, 2) }],
  };
}

function textResult(text) {
  return {
    content: [{ type: 'text', text }],
  };
}

function errorResult(value) {
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  return {
    isError: true,
    content: [{ type: 'text', text }],
  };
}

function isLoopbackHostname(hostname) {
  const host = hostname.toLowerCase();
  const normalized = host.startsWith('[') && host.endsWith(']') ? host.slice(1, -1) : host;
  if (normalized === 'localhost' || normalized === '::1') return true;
  return net.isIP(normalized) === 4 && normalized.split('.')[0] === '127';
}

function assertLoopbackBaseUrl(name, value) {
  const url = new URL(value);
  if (!isLoopbackHostname(url.hostname)) {
    throw new Error(`${name} must use a loopback hostname for local-only MCP access: ${value}`);
  }
  return url.toString();
}

function relativePath(value) {
  return path.relative(repoRoot, value).replaceAll(path.sep, '/');
}

function assertSafeRunId(runId) {
  if (!runId || runId.includes('/') || runId.includes('\\') || runId.includes('..')) {
    throw new Error('run_id must be a testing/runs directory name, not a path');
  }
  const resolved = path.resolve(runsDir, runId);
  if (!resolved.startsWith(path.resolve(runsDir) + path.sep)) {
    throw new Error('run_id resolved outside testing/runs');
  }
  return resolved;
}

function trimOutput(value, maxLength = 12000) {
  const text = String(value || '');
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}\n...[truncated ${text.length - maxLength} chars]`;
}

async function fetchJson(baseUrl, pathname, params = {}) {
  const url = new URL(pathname, baseUrl);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, String(value));
    }
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10_000);
  try {
    const response = await fetch(url, { signal: controller.signal });
    const text = await response.text();
    let body = null;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = text;
      }
    }
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}: ${JSON.stringify(body)}`);
    }
    return body;
  } finally {
    clearTimeout(timeout);
  }
}

async function checkEndpoint(name, baseUrl, pathname) {
  try {
    const body = await fetchJson(baseUrl, pathname);
    return { name, ok: true, url: new URL(pathname, baseUrl).toString(), body };
  } catch (error) {
    return {
      name,
      ok: false,
      url: new URL(pathname, baseUrl).toString(),
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

async function listEvidenceRunDirs(limit) {
  let entries;
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
  return dirs.slice(0, limit);
}

async function summarizeEvidenceRun(entry) {
  const evidencePath = path.join(entry.dir, 'evidence.json');
  const screenshotsDir = path.join(entry.dir, 'screenshots');
  const reviewsDir = path.join(entry.dir, 'reviews');
  const [evidenceExists, screenshots, reviews] = await Promise.all([
    fs.access(evidencePath).then(() => true, () => false),
    fs.readdir(screenshotsDir).catch(() => []),
    fs.readdir(reviewsDir).catch(() => []),
  ]);
  return {
    run_id: entry.name,
    path: relativePath(entry.dir),
    modified_at: entry.stat.mtime.toISOString(),
    evidence_manifest: evidenceExists ? relativePath(evidencePath) : null,
    screenshots: screenshots.length,
    reviews: reviews.length,
  };
}

function redactBuyer(buyer) {
  return {
    buyer_id: buyer.buyer_id,
    company: buyer.company,
    status: buyer.status,
    sales_stage: buyer.sales_stage,
    deposit_balance_cents: buyer.deposit_balance_cents,
    lifetime_spend_cents: buyer.lifetime_spend_cents,
    daily_cap: buyer.daily_cap,
    monthly_budget_cents: buyer.monthly_budget_cents,
    services: buyer.services || [],
    target_zips: buyer.target_zips || [],
    exclusive_zips: buyer.exclusive_zips || [],
    low_balance_threshold_cents: buyer.low_balance_threshold_cents,
    license_state: buyer.license_state,
    contact_redacted: true,
    webhook_redacted: true,
  };
}

async function runLocalCommand({ script, args = [], timeoutSeconds }) {
  const timeoutMs = Math.max(30, Math.min(timeoutSeconds || 180, 600)) * 1000;
  const startedAt = new Date();
  try {
    const result = await execFileAsync(
      'uv',
      ['run', 'python', script, ...args],
      {
        cwd: repoRoot,
        timeout: timeoutMs,
        maxBuffer: 10 * 1024 * 1024,
        windowsHide: true,
      },
    );
    return {
      ok: true,
      script,
      started_at: startedAt.toISOString(),
      finished_at: new Date().toISOString(),
      stdout: trimOutput(result.stdout),
      stderr: trimOutput(result.stderr),
    };
  } catch (error) {
    return {
      ok: false,
      script,
      started_at: startedAt.toISOString(),
      finished_at: new Date().toISOString(),
      exit_code: error?.code ?? null,
      signal: error?.signal ?? null,
      stdout: trimOutput(error?.stdout),
      stderr: trimOutput(error?.stderr),
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

async function runNodeLocalCommand({ script, args = [], timeoutSeconds }) {
  const timeoutMs = Math.max(5, Math.min(timeoutSeconds || 60, 900)) * 1000;
  const startedAt = new Date();
  try {
    const result = await execFileAsync(
      process.execPath,
      [script, ...args],
      {
        cwd: repoRoot,
        timeout: timeoutMs,
        maxBuffer: 10 * 1024 * 1024,
        windowsHide: true,
      },
    );
    return {
      ok: true,
      script,
      started_at: startedAt.toISOString(),
      finished_at: new Date().toISOString(),
      stdout: trimOutput(result.stdout),
      stderr: trimOutput(result.stderr),
    };
  } catch (error) {
    return {
      ok: false,
      script,
      started_at: startedAt.toISOString(),
      finished_at: new Date().toISOString(),
      exit_code: error?.code ?? null,
      signal: error?.signal ?? null,
      stdout: trimOutput(error?.stdout),
      stderr: trimOutput(error?.stderr),
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

server.registerTool(
  'check_local_services',
  {
    title: 'Check Local Services',
    description: 'Check local/dev StormLead HTTP health endpoints without contacting external services.',
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  },
  async () => jsonResult({
    local_only: true,
    services: await Promise.all([
      checkEndpoint('ping-post health', adminBaseUrl, '/healthz'),
      checkEndpoint('ping-post ready', adminBaseUrl, '/readyz'),
      checkEndpoint('form-receiver health', formReceiverBaseUrl, '/healthz'),
      checkEndpoint('litellm readiness', litellmBaseUrl, '/health/readiness'),
    ]),
  }),
);

server.registerTool(
  'get_admin_kpis',
  {
    title: 'Get Admin KPIs',
    description: 'Read the local admin KPI endpoint.',
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  },
  async () => jsonResult(await fetchJson(adminBaseUrl, '/v1/admin/kpis')),
);

server.registerTool(
  'get_workflow_kpis',
  {
    title: 'Get Workflow KPIs',
    description: 'Read agentic workflow KPI metrics from the local admin API.',
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  },
  async () => jsonResult(await fetchJson(adminBaseUrl, '/v1/admin/workflow-kpis')),
);

server.registerTool(
  'get_launch_readiness',
  {
    title: 'Get Launch Readiness',
    description: 'Read local simulation, technical, and commercial readiness gates from the admin API.',
    inputSchema: {
      market_state: z.string().length(2).optional(),
      market_zip: z.string().min(3).max(10).optional(),
      service: z.string().min(1).max(64).optional(),
      campaign_budget_cents: z.number().int().min(0).optional(),
    },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  },
  async (args) => jsonResult(await fetchJson(adminBaseUrl, '/v1/admin/launch-readiness', args)),
);

server.registerTool(
  'list_recent_workflow_runs',
  {
    title: 'List Recent Workflow Runs',
    description: 'List recent audited lead workflow runs from the local admin API.',
    inputSchema: { limit: z.number().int().min(1).max(100).default(20) },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  },
  async ({ limit }) => jsonResult(await fetchJson(adminBaseUrl, '/v1/admin/workflow-runs/recent', { limit })),
);

server.registerTool(
  'get_lead_timeline',
  {
    title: 'Get Lead Timeline',
    description: 'Read a redacted lead state-transition timeline from the local admin API.',
    inputSchema: {
      lead_id: z.string().uuid(),
      limit: z.number().int().min(1).max(250).default(100),
    },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  },
  async ({ lead_id, limit }) => jsonResult(await fetchJson(adminBaseUrl, `/v1/admin/leads/${lead_id}/timeline`, { limit })),
);

server.registerTool(
  'list_buyers_redacted',
  {
    title: 'List Buyers Redacted',
    description: 'List local buyer roster rows with contacts, notes, and webhook URLs removed.',
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  },
  async () => {
    const data = await fetchJson(adminBaseUrl, '/v1/buyers');
    return jsonResult({ buyers: (data.buyers || []).map(redactBuyer) });
  },
);

server.registerTool(
  'list_evidence_runs',
  {
    title: 'List Evidence Runs',
    description: 'List recent ignored local evidence folders under testing/runs.',
    inputSchema: { limit: z.number().int().min(1).max(50).default(10) },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  },
  async ({ limit }) => {
    const entries = await listEvidenceRunDirs(limit);
    return jsonResult({ runs: await Promise.all(entries.map(summarizeEvidenceRun)) });
  },
);

server.registerTool(
  'get_evidence_manifest',
  {
    title: 'Get Evidence Manifest',
    description: 'Read an evidence.json manifest from testing/runs. Defaults to the latest run.',
    inputSchema: { run_id: z.string().min(1).optional() },
    annotations: { readOnlyHint: true, destructiveHint: false, openWorldHint: false },
  },
  async ({ run_id }) => {
    const dir = run_id ? assertSafeRunId(run_id) : (await listEvidenceRunDirs(1))[0]?.dir;
    if (!dir) return textResult('No testing/runs evidence folders exist yet.');
    const evidencePath = path.join(dir, 'evidence.json');
    const raw = await fs.readFile(evidencePath, 'utf8');
    return jsonResult({ path: relativePath(evidencePath), manifest: JSON.parse(raw) });
  },
);

server.registerTool(
  'prepare_tars_exploration',
  {
    title: 'Prepare TARS Exploration',
    description: 'Prepare a local-only UI-TARS/Agent TARS browser exploration brief and evidence folder under testing/runs. Requires explicit confirm_synthetic_local=true.',
    inputSchema: {
      confirm_synthetic_local: z.boolean().default(false),
      targets: z.array(z.enum(['admin', 'landing', 'buyer-portal'])).default(['admin', 'landing', 'buyer-portal']),
      run_id: z.string().min(1).max(120).optional(),
      timeout_seconds: z.number().int().min(5).max(60).default(30),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  },
  async ({ confirm_synthetic_local, targets, run_id, timeout_seconds }) => {
    if (!confirm_synthetic_local) {
      return textResult('Refusing to run. Call again with confirm_synthetic_local=true to prepare a local-only TARS exploration package under testing/runs.');
    }

    const selectedTargets = targets?.length ? targets : ['admin', 'landing', 'buyer-portal'];
    const commandArgs = ['--targets', selectedTargets.join(',')];
    if (run_id) commandArgs.push('--run-id', run_id);
    const result = await runNodeLocalCommand({
      script: 'scripts/prepare_tars_exploration.mjs',
      args: commandArgs,
      timeoutSeconds: timeout_seconds,
    });
    if (!result.ok) return errorResult({ local_only: true, command: result });
    try {
      return jsonResult({ local_only: true, result: JSON.parse(result.stdout), command: { ok: result.ok, stderr: result.stderr } });
    } catch {
      return jsonResult({ local_only: true, command: result });
    }
  },
);

server.registerTool(
  'run_tars_exploration',
  {
    title: 'Run TARS Exploration',
    description: 'Run the local StormLead TARS runner bridge against a prepared TARS package. Consumes runner-prompt.md, saves screenshots, and appends structured findings. Requires explicit confirm_synthetic_local=true.',
    inputSchema: {
      confirm_synthetic_local: z.boolean().default(false),
      run_id: z.string().min(1).max(160).optional(),
      targets: z.array(z.enum(['admin', 'landing', 'buyer-portal'])).default(['admin', 'landing', 'buyer-portal']),
      headless: z.boolean().default(true),
      timeout_seconds: z.number().int().min(30).max(180).default(90),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  },
  async ({ confirm_synthetic_local, run_id, targets, headless, timeout_seconds }) => {
    if (!confirm_synthetic_local) {
      return textResult('Refusing to run. Call again with confirm_synthetic_local=true to run the local TARS bridge against loopback StormLead surfaces.');
    }

    const selectedTargets = targets?.length ? targets : ['admin', 'landing', 'buyer-portal'];
    const commandArgs = ['--targets', selectedTargets.join(','), '--headless', String(headless)];
    if (run_id) commandArgs.push('--run-id', run_id);
    const result = await runNodeLocalCommand({
      script: 'scripts/run_tars_exploration.mjs',
      args: commandArgs,
      timeoutSeconds: timeout_seconds,
    });
    if (!result.ok) return errorResult({ local_only: true, command: result });
    try {
      return jsonResult({ local_only: true, result: JSON.parse(result.stdout), command: { ok: result.ok, stderr: result.stderr } });
    } catch {
      return jsonResult({ local_only: true, command: result });
    }
  },
);

server.registerTool(
  'run_v1_simulation',
  {
    title: 'Run V1 Simulation',
    description: 'Run the existing synthetic V1 local simulation script. Requires explicit confirm_synthetic_local=true.',
    inputSchema: {
      confirm_synthetic_local: z.boolean().default(false),
      timeout_seconds: z.number().int().min(30).max(600).default(240),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  },
  async ({ confirm_synthetic_local, timeout_seconds }) => {
    if (!confirm_synthetic_local) {
      return textResult('Refusing to run. Call again with confirm_synthetic_local=true to run scripts/simulate_v1_leads.py against local/dev services.');
    }
    return jsonResult(await runLocalCommand({ script: 'scripts/simulate_v1_leads.py', timeoutSeconds: timeout_seconds }));
  },
);

server.registerTool(
  'run_local_smoke',
  {
    title: 'Run Local Smoke',
    description: 'Run the existing local smoke test script. Requires explicit confirm_synthetic_local=true.',
    inputSchema: {
      confirm_synthetic_local: z.boolean().default(false),
      timeout_seconds: z.number().int().min(30).max(600).default(240),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  },
  async ({ confirm_synthetic_local, timeout_seconds }) => {
    if (!confirm_synthetic_local) {
      return textResult('Refusing to run. Call again with confirm_synthetic_local=true to run scripts/smoke_e2e.py against local/dev services.');
    }
    return jsonResult(await runLocalCommand({ script: 'scripts/smoke_e2e.py', timeoutSeconds: timeout_seconds }));
  },
);

server.registerTool(
  'run_chrome_observer_functional_test',
  {
    title: 'Run Chrome Observer Functional Test',
    description: 'Run the functional Chrome observer test through local loopback pages and verify both CLI and MCP observer paths capture browser evidence. Requires explicit confirm_synthetic_local=true.',
    inputSchema: {
      confirm_synthetic_local: z.boolean().default(false),
      timeout_seconds: z.number().int().min(30).max(180).default(120),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  },
  async ({ confirm_synthetic_local, timeout_seconds }) => {
    if (!confirm_synthetic_local) {
      return textResult('Refusing to run. Call again with confirm_synthetic_local=true to run the local Chrome observer functional test and write testing/runs browser evidence.');
    }

    const result = await runNodeLocalCommand({
      script: 'scripts/test_chrome_observer.mjs',
      timeoutSeconds: timeout_seconds,
    });
    try {
      return jsonResult({ local_only: true, result: JSON.parse(result.stdout), command: { ok: result.ok, stderr: result.stderr } });
    } catch {
      return jsonResult({ local_only: true, command: result });
    }
  },
);

server.registerTool(
  'run_self_learning_loop',
  {
    title: 'Run Self-Learning Loop',
    description: 'Run the local Playwright, Puppeteer, and MCP self-learning evidence loop. Requires explicit confirm_synthetic_local=true.',
    inputSchema: {
      confirm_synthetic_local: z.boolean().default(false),
      url: z.string().url().optional(),
      max_iterations: z.number().int().min(1).max(3).default(1),
      playwright_project: z.enum(['none', 'api', 'chromium', 'all']).default('none'),
      include_observer: z.boolean().default(true),
      include_puppeteer: z.boolean().default(true),
      include_smoke: z.boolean().default(false),
      include_v1: z.boolean().default(false),
      headless: z.boolean().default(true),
      channel: z.string().min(1).max(40).optional(),
      dispatch_codex: z.boolean().default(false),
      confirm_external_llm_dispatch: z.boolean().default(false),
      max_runners: z.number().int().min(1).max(3).default(1),
      timeout_seconds: z.number().int().min(30).max(900).default(240),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  },
  async ({
    confirm_synthetic_local,
    url,
    max_iterations,
    playwright_project,
    include_observer,
    include_puppeteer,
    include_smoke,
    include_v1,
    headless,
    channel,
    dispatch_codex,
    confirm_external_llm_dispatch,
    max_runners,
    timeout_seconds,
  }) => {
    if (!confirm_synthetic_local) {
      return textResult('Refusing to run. Call again with confirm_synthetic_local=true to run the local self-learning loop and write testing/runs evidence.');
    }
    if (dispatch_codex && !confirm_external_llm_dispatch) {
      return textResult('Refusing to dispatch Codex from MCP without confirm_external_llm_dispatch=true. Keep MCP self-learning local-only by default.');
    }

    const commandArgs = [
      '--max-iterations', String(max_iterations),
      '--playwright-project', playwright_project,
      '--include-observer', String(include_observer),
      '--include-puppeteer', String(include_puppeteer),
      '--include-smoke', String(include_smoke),
      '--include-v1', String(include_v1),
      '--headless', String(headless),
      '--dispatch-codex', String(dispatch_codex),
      '--max-runners', String(max_runners),
      '--timeout-seconds', String(timeout_seconds),
    ];
    if (url) commandArgs.push('--url', url);
    if (channel) commandArgs.push('--channel', channel);

    const result = await runNodeLocalCommand({
      script: 'scripts/self_learning_loop.mjs',
      args: commandArgs,
      timeoutSeconds: timeout_seconds,
    });
    try {
      return jsonResult({ local_only: true, result: JSON.parse(result.stdout), command: { ok: result.ok, stderr: result.stderr } });
    } catch {
      return jsonResult({ local_only: true, command: result });
    }
  },
);

server.registerTool(
  'observe_chrome_page',
  {
    title: 'Observe Chrome Page',
    description: 'Launch a local-only Chrome/Chromium page, stream browser console/network/page logs to testing/runs, and return an evidence summary. Requires explicit confirm_synthetic_local=true.',
    inputSchema: {
      confirm_synthetic_local: z.boolean().default(false),
      url: z.string().url().optional(),
      duration_seconds: z.number().int().min(0).max(45).default(10),
      headless: z.boolean().default(true),
      channel: z.string().min(1).max(40).optional(),
      run_id: z.string().min(1).max(120).optional(),
      actions: z.array(z.object({
        type: z.enum([
          'click',
          'fill',
          'press',
          'wait',
          'wait_for_selector',
          'wait_for_response',
          'screenshot',
        ]),
        selector: z.string().min(1).optional(),
        value: z.union([z.string(), z.number(), z.boolean()]).optional(),
        key: z.string().min(1).optional(),
        ms: z.number().int().min(0).max(60_000).optional(),
        state: z.enum(['attached', 'detached', 'visible', 'hidden']).optional(),
        url_includes: z.string().optional(),
        status: z.number().int().min(100).max(599).optional(),
        timeout_ms: z.number().int().min(1).max(120_000).optional(),
        name: z.string().min(1).max(80).optional(),
        full_page: z.boolean().optional(),
      })).default([]),
    },
    annotations: { readOnlyHint: false, destructiveHint: false, openWorldHint: false },
  },
  async ({ confirm_synthetic_local, url, duration_seconds, headless, channel, run_id, actions }) => {
    if (!confirm_synthetic_local) {
      return textResult('Refusing to run. Call again with confirm_synthetic_local=true to launch Chrome against local/dev services and write testing/runs browser evidence.');
    }

    const commandArgs = [
      '--duration-seconds', String(duration_seconds),
      '--headless', String(headless),
    ];
    if (url) commandArgs.push('--url', url);
    if (channel) commandArgs.push('--channel', channel);
    if (run_id) commandArgs.push('--run-id', run_id);
    if (actions?.length) commandArgs.push('--actions-json', JSON.stringify(actions));

    const result = await runNodeLocalCommand({
      script: 'scripts/chrome_observe.mjs',
      args: commandArgs,
      timeoutSeconds: Math.max(20, Math.min((duration_seconds || 0) + 35, 55)),
    });
    try {
      return jsonResult({ local_only: true, result: JSON.parse(result.stdout), command: { ok: result.ok, stderr: result.stderr } });
    } catch {
      return jsonResult({ local_only: true, command: result });
    }
  },
);

await server.connect(new StdioServerTransport());
