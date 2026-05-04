#!/usr/bin/env node

import { execFile } from 'node:child_process';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';

const execFileAsync = promisify(execFile);
const repoRoot = path.resolve(fileURLToPath(new URL('../..', import.meta.url)));
const runsDir = path.join(repoRoot, 'testing', 'runs');
const adminBaseUrl = process.env.STORMLEAD_ADMIN_URL || 'http://127.0.0.1:8003';
const formReceiverBaseUrl = process.env.STORMLEAD_FORM_RECEIVER_URL || 'http://127.0.0.1:8002';
const litellmBaseUrl = process.env.STORMLEAD_LITELLM_URL || 'http://127.0.0.1:4000';

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

await server.connect(new StdioServerTransport());
