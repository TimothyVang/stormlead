#!/usr/bin/env node

import { execFile } from 'node:child_process';
import { appendFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

const execFileAsync = promisify(execFile);
const repoRoot = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const runsDir = path.join(repoRoot, 'testing', 'runs');

const RESEARCH_SOURCES = [
  {
    name: 'Playwright Trace Viewer',
    url: 'https://playwright.dev/docs/trace-viewer',
    note: 'Traces expose actions, DOM snapshots, console, network, errors, and metadata for debugging.',
  },
  {
    name: 'Playwright Network',
    url: 'https://playwright.dev/docs/network',
    note: 'Request/response events and waitForResponse provide browser evidence without mocking production APIs.',
  },
  {
    name: 'Puppeteer Page Interactions',
    url: 'https://pptr.dev/guides/page-interactions',
    note: 'Puppeteer locators auto-wait for visible, enabled, stable elements before interaction.',
  },
  {
    name: 'Lighthouse User Flows',
    url: 'https://github.com/GoogleChrome/lighthouse/blob/main/docs/user-flows.md',
    note: 'Puppeteer plus Lighthouse can audit navigation, timespan, and snapshot phases of an app flow.',
  },
  {
    name: 'MCP Tools',
    url: 'https://modelcontextprotocol.io/docs/concepts/tools',
    note: 'MCP tools should validate inputs, surface tool use clearly, and keep a human confirmation path for sensitive operations.',
  },
];

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

function parseInteger(value, defaultValue, min, max) {
  const parsed = Number(value ?? defaultValue);
  if (!Number.isFinite(parsed)) return defaultValue;
  return Math.max(min, Math.min(Math.trunc(parsed), max));
}

function commandName(name) {
  return process.platform === 'win32' ? `${name}.cmd` : name;
}

function assertLoopbackHttpUrl(value) {
  const url = new URL(value);
  const hostname = url.hostname.toLowerCase();
  const isLoopback = hostname === 'localhost'
    || hostname === '::1'
    || hostname === '[::1]'
    || hostname.startsWith('127.');
  if (!['http:', 'https:'].includes(url.protocol) || !isLoopback) {
    throw new Error(`Self-learning loop only accepts loopback HTTP(S) URLs: ${value}`);
  }
  return url.toString();
}

function safeRunId(value) {
  const raw = value || new Date().toISOString().replace(/[:.]/g, '-');
  return String(raw).replace(/[^A-Za-z0-9_.-]/g, '-').slice(0, 120);
}

function relativePath(value) {
  return path.relative(repoRoot, value).replaceAll(path.sep, '/');
}

function trimOutput(value, maxLength = 16000) {
  const text = String(value ?? '');
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}\n...[truncated ${text.length - maxLength} chars]`;
}

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}

function markdownList(items) {
  return items.length ? items.map((item) => `- ${item}`).join('\n') : '- None.';
}

function textContent(result) {
  return (result.content || [])
    .filter((item) => item.type === 'text')
    .map((item) => item.text)
    .join('\n');
}

function parseJsonMaybe(text) {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function serviceOk(step, name) {
  return Boolean(step.output?.services?.some((service) => service.name === name && service.ok));
}

async function runCommand(label, command, args, timeoutSeconds) {
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
      kind: 'command',
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
      kind: 'command',
      label,
      ok: false,
      command: [command, ...args],
      started_at: startedAt.toISOString(),
      finished_at: new Date().toISOString(),
      exit_code: typeof error?.code === 'number' ? error.code : null,
      signal: error?.signal ?? null,
      stdout: trimOutput(error?.stdout),
      stderr: trimOutput(error?.stderr),
      error: errorMessage(error),
    };
  }
}

async function withMcp(callback) {
  const client = new Client({ name: 'stormlead-self-learning-loop', version: '0.1.0' });
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: ['tools/mcp/stormlead-local-ops.mjs'],
    cwd: repoRoot,
    stderr: 'pipe',
  });

  await client.connect(transport);
  try {
    return await callback(client);
  } finally {
    await client.close();
  }
}

async function runMcpTool(client, name, args = {}) {
  const startedAt = new Date();
  try {
    const result = await client.callTool({ name, arguments: args });
    const text = textContent(result);
    return {
      kind: 'mcp_tool',
      name,
      ok: result.isError !== true,
      arguments: args,
      started_at: startedAt.toISOString(),
      finished_at: new Date().toISOString(),
      output: parseJsonMaybe(text),
    };
  } catch (error) {
    return {
      kind: 'mcp_tool',
      name,
      ok: false,
      arguments: args,
      started_at: startedAt.toISOString(),
      finished_at: new Date().toISOString(),
      error: errorMessage(error),
    };
  }
}

function appendBrowserEvent(eventsPath, eventCounts, recentErrors, pageUrl, runId, type, severity, data = {}) {
  const event = {
    schema_version: 1,
    at: new Date().toISOString(),
    run_id: runId,
    type,
    severity,
    page_url: pageUrl,
    data,
  };
  eventCounts[type] = (eventCounts[type] ?? 0) + 1;
  if (severity === 'error') recentErrors.push(event);
  appendFileSync(eventsPath, JSON.stringify(event) + '\n');
}

function installPuppeteerObserver(page, runId, eventsPath) {
  const eventCounts = {};
  const recentErrors = [];
  const record = (type, severity, data = {}) => appendBrowserEvent(
    eventsPath,
    eventCounts,
    recentErrors,
    typeof page.url === 'function' ? page.url() : '',
    runId,
    type,
    severity,
    data,
  );

  page.on('console', (message) => {
    const level = message.type();
    record('puppeteer.console', level === 'error' ? 'error' : level === 'warning' ? 'warning' : 'info', {
      level,
      text: trimOutput(message.text(), 4000),
      location: message.location(),
    });
  });
  page.on('pageerror', (error) => record('puppeteer.page_error', 'error', { message: errorMessage(error) }));
  page.on('requestfailed', (request) => record('puppeteer.request_failed', 'error', {
    method: request.method(),
    url: request.url(),
    resource_type: request.resourceType(),
    failure: request.failure()?.errorText ?? null,
  }));
  page.on('response', (response) => {
    void (async () => {
      const status = response.status();
      const resourceType = response.request().resourceType();
      if (status < 400) {
        if (['document', 'fetch', 'xhr'].includes(resourceType)) {
          record('puppeteer.response', 'info', {
            method: response.request().method(),
            url: response.url(),
            status,
            resource_type: resourceType,
            content_type: response.headers()['content-type'] ?? null,
          });
        }
        return;
      }

      const data = {
        method: response.request().method(),
        url: response.url(),
        status,
        resource_type: resourceType,
        content_type: response.headers()['content-type'] ?? null,
      };
      if (['document', 'fetch', 'xhr'].includes(resourceType) && /json|text|html|plain|problem\+json/i.test(data.content_type ?? '')) {
        try {
          data.body_preview = trimOutput(await response.text(), 8000);
        } catch (error) {
          data.body_error = errorMessage(error);
        }
      }
      record('puppeteer.http_error', 'error', data);
    })();
  });
  page.on('framenavigated', (frame) => {
    if (frame === page.mainFrame()) record('puppeteer.navigation', 'info', { url: frame.url() });
  });

  record('puppeteer.observe_started', 'info', { note: 'Puppeteer evidence stream for self-learning loop.' });
  return { eventCounts, recentErrors, record };
}

async function delay(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function runPuppeteerAction(page, action, observer, screenshotsDir, index) {
  const type = action?.type;
  observer.record('puppeteer.action_started', 'info', { index, action });
  switch (type) {
    case 'click':
      await page.locator(action.selector).setTimeout(action.timeout_ms ?? 30_000).click();
      break;
    case 'fill':
      await page.locator(action.selector).setTimeout(action.timeout_ms ?? 30_000).fill(String(action.value ?? ''));
      break;
    case 'press': {
      const handle = await page.waitForSelector(action.selector, { timeout: action.timeout_ms ?? 30_000 });
      if (!handle) throw new Error(`No element found for ${action.selector}`);
      await handle.press(String(action.key ?? 'Enter'));
      await handle.dispose();
      break;
    }
    case 'wait':
      await delay(Math.max(0, Math.min(Number(action.ms ?? 1000), 60_000)));
      break;
    case 'wait_for_selector':
      await page.locator(action.selector).setTimeout(action.timeout_ms ?? 30_000).wait();
      break;
    case 'wait_for_response':
      await page.waitForResponse(
        (response) => response.url().includes(String(action.url_includes ?? ''))
          && (action.status === undefined || response.status() === Number(action.status)),
        { timeout: action.timeout_ms ?? 30_000 },
      );
      break;
    case 'screenshot': {
      const name = String(action.name ?? `action-${index}`).replace(/[^A-Za-z0-9_.-]/g, '-');
      const screenshotPath = path.join(screenshotsDir, `${String(index).padStart(2, '0')}-${name}.png`);
      await page.screenshot({ path: screenshotPath, fullPage: action.full_page !== false });
      observer.record('puppeteer.screenshot', 'info', { path: relativePath(screenshotPath) });
      break;
    }
    default:
      throw new Error(`Unsupported Puppeteer action type: ${type}`);
  }
  observer.record('puppeteer.action_finished', 'info', { index, action });
}

function summarizeFlowResult(flowResult) {
  return (flowResult.steps || []).map((step) => ({
    name: step.name ?? step.gatherMode ?? 'unnamed step',
    mode: step.gatherMode ?? null,
    categories: Object.fromEntries(
      Object.entries(step.lhr?.categories ?? {}).map(([id, category]) => [id, category.score]),
    ),
  }));
}

async function runPuppeteerAudit({ targetUrl, runId, iterationDir, headless, channel, executablePath, actions, durationSeconds }) {
  const auditDir = path.join(iterationDir, 'puppeteer');
  const logsDir = path.join(auditDir, 'logs');
  const screenshotsDir = path.join(auditDir, 'screenshots');
  mkdirSync(logsDir, { recursive: true });
  mkdirSync(screenshotsDir, { recursive: true });

  const eventsPath = path.join(logsDir, 'puppeteer-events.jsonl');
  const flowHtmlPath = path.join(auditDir, 'lighthouse-flow.html');
  const flowJsonPath = path.join(auditDir, 'lighthouse-flow.json');
  const summaryPath = path.join(auditDir, 'puppeteer-summary.json');
  const startedAt = new Date();
  let browser;
  let page;
  let observer;
  let ok = true;
  let failure = null;
  let flowSummary = [];

  try {
    const puppeteer = await import('puppeteer-core');
    const { startFlow, desktopConfig } = await import('lighthouse');
    const launchOptions = {
      headless,
      args: ['--disable-dev-shm-usage'],
      timeout: 30_000,
    };
    if (executablePath) launchOptions.executablePath = executablePath;
    else launchOptions.channel = channel || 'chrome';

    browser = await puppeteer.default.launch(launchOptions);
    page = await browser.newPage();
    await page.setViewport({ width: 1440, height: 900 });
    observer = installPuppeteerObserver(page, runId, eventsPath);

    const flow = await startFlow(page, {
      config: desktopConfig,
      flags: { screenEmulation: { disabled: true } },
    });

    await flow.navigate(targetUrl);
    await page.screenshot({ path: path.join(screenshotsDir, '00-navigation.png'), fullPage: true });
    await flow.startTimespan();
    for (let index = 0; index < actions.length; index += 1) {
      await runPuppeteerAction(page, actions[index], observer, screenshotsDir, index + 1);
    }
    if (durationSeconds > 0) await delay(durationSeconds * 1000);
    await flow.endTimespan();
    await flow.snapshot();
    await page.screenshot({ path: path.join(screenshotsDir, 'final.png'), fullPage: true });

    const flowResult = await flow.createFlowResult();
    flowSummary = summarizeFlowResult(flowResult);
    writeFileSync(flowHtmlPath, await flow.generateReport());
    writeFileSync(flowJsonPath, JSON.stringify(flowResult, null, 2) + '\n');
    observer.record('puppeteer.observe_finished', 'info', { final_url: page.url() });
  } catch (error) {
    ok = false;
    failure = errorMessage(error);
    if (observer) observer.record('puppeteer.observe_failed', 'error', { error: failure });
    if (page) {
      await page.screenshot({ path: path.join(screenshotsDir, 'failure.png'), fullPage: true }).catch(() => undefined);
    }
  } finally {
    if (browser) await browser.close().catch(() => undefined);
  }

  const summary = {
    schema_version: 1,
    kind: 'puppeteer_lighthouse_flow',
    ok,
    run_id: runId,
    started_at: startedAt.toISOString(),
    finished_at: new Date().toISOString(),
    target_url: targetUrl,
    final_url: typeof page?.url === 'function' ? page.url() : null,
    error: failure,
    event_counts: observer?.eventCounts ?? {},
    error_count: observer?.recentErrors?.length ?? 0,
    recent_errors: observer?.recentErrors?.slice(-25) ?? [],
    lighthouse_steps: flowSummary,
    artifacts: {
      puppeteer_events_jsonl: relativePath(eventsPath),
      puppeteer_summary_json: relativePath(summaryPath),
      lighthouse_flow_html: relativePath(flowHtmlPath),
      lighthouse_flow_json: relativePath(flowJsonPath),
      screenshots_dir: relativePath(screenshotsDir),
    },
  };
  writeFileSync(summaryPath, JSON.stringify(summary, null, 2) + '\n');
  return summary;
}

function collectStepFindings(step) {
  const findings = [];
  const label = step.label ?? step.name ?? step.kind;
  if (!step.ok) {
    findings.push(`${label} failed: ${step.error ?? step.stderr ?? 'no error message'}`);
  }

  if (step.kind === 'mcp_tool' && step.name === 'check_local_services') {
    for (const service of step.output?.services ?? []) {
      if (!service.ok) findings.push(`local service unhealthy: ${service.name} ${service.url} (${service.error})`);
    }
  }

  if (step.kind === 'mcp_tool' && step.name === 'observe_chrome_page') {
    const observed = step.output?.result;
    if (observed?.ok === false) findings.push(`MCP Chrome observer failed: ${observed.error}`);
    if ((observed?.error_count ?? 0) > 0) findings.push(`MCP Chrome observer captured ${observed.error_count} browser errors`);
  }

  if (step.kind === 'puppeteer_lighthouse_flow') {
    if ((step.error_count ?? 0) > 0) findings.push(`Puppeteer captured ${step.error_count} browser errors`);
    for (const flowStep of step.lighthouse_steps ?? []) {
      for (const [category, score] of Object.entries(flowStep.categories ?? {})) {
        if (category === 'performance' && String(flowStep.name ?? '').startsWith('Snapshot report')) {
          continue;
        }
        if (typeof score === 'number' && score < 0.9) {
          findings.push(`Lighthouse ${flowStep.name} ${category} score ${score}`);
        }
      }
    }
  }

  return findings;
}

function collectIterationFindings(iteration) {
  return iteration.steps.flatMap(collectStepFindings);
}

function buildThink(iterationNumber, previousFindings, options) {
  if (iterationNumber === 1) {
    return [
      `Target local app URL is ${options.targetUrl}.`,
      'StormLead constraints require synthetic local/dev proof only.',
      'Use MCP for local state and confirmed command tools, Playwright-backed Chrome observation for browser evidence, and Puppeteer/Lighthouse for Chrome-native performance/accessibility flow evidence.',
      'Smallest action is to collect evidence first, then generate runner prompts from facts rather than guessing fixes.',
    ];
  }
  return [
    `Previous iteration had ${previousFindings.length} finding(s).`,
    'The next iteration should narrow the highest-confidence blocker with local browser/service evidence before editing app code.',
    'Repeated failures should become runner prompts, focused tests, or durable docs only after verification.',
  ];
}

function buildDecide(findings, runDir) {
  if (!findings.length) {
    return [
      'No failing local evidence was captured in this iteration.',
      'Next best improvement is to convert any manually valuable flow into a deterministic Playwright test or keep evidence under testing/runs.',
    ];
  }
  return [
    `Captured ${findings.length} finding(s); create focused runner prompts under ${relativePath(path.join(runDir, 'runner-prompts'))}.`,
    'Send read-only investigation first when source/log context is unclear; send a fix runner only for the smallest verified app/test gap.',
    'Rerun this loop or the narrow failing proof after any fix.',
  ];
}

function writeIterationMarkdown(iteration, filePath) {
  const lines = [
    `# Self-Learning Iteration ${iteration.number}`,
    '',
    '## THINK',
    markdownList(iteration.think),
    '',
    '## ACT',
    markdownList(iteration.steps.map((step) => `${step.kind}:${step.label ?? step.name} -> ${step.ok ? 'ok' : 'failed'}`)),
    '',
    '## OBSERVE',
    markdownList(iteration.observations),
    '',
    '## DECIDE',
    markdownList(iteration.decide),
    '',
    '## Findings',
    markdownList(iteration.findings),
    '',
  ];
  writeFileSync(filePath, lines.join('\n'));
}

function observationsFromSteps(steps) {
  return steps.map((step) => {
    if (step.kind === 'mcp_tool' && step.name === 'check_local_services') {
      const services = (step.output?.services ?? []).map((service) => `${service.name}:${service.ok ? 'ok' : 'fail'}`).join(', ');
      return `MCP service check ${step.ok ? 'completed' : 'failed'} (${services || step.error || 'no services returned'}).`;
    }
    if (step.kind === 'mcp_tool' && step.name === 'observe_chrome_page') {
      const observed = step.output?.result;
      return `MCP Chrome observer ${observed?.ok ? 'captured' : 'failed'} evidence at ${observed?.artifacts?.run_dir ?? 'no run dir'}.`;
    }
    if (step.kind === 'puppeteer_lighthouse_flow') {
      return `Puppeteer/Lighthouse ${step.ok ? 'captured' : 'failed'} flow evidence at ${step.artifacts?.puppeteer_summary_json}.`;
    }
    if (step.kind === 'command') {
      return `${step.label} ${step.ok ? 'passed' : 'failed'}${step.exit_code === null ? '' : ` with exit ${step.exit_code}`}.`;
    }
    return `${step.kind}:${step.label ?? step.name} ${step.ok ? 'ok' : 'failed'}.`;
  });
}

function buildRunnerPrompt({ title, mode, runId, runDir, targetUrl, findings, promptFocus }) {
  return [
    `# ${title}`,
    '',
    `Mode: ${mode}`,
    `StormLead run: ${runId}`,
    `Evidence folder: ${relativePath(runDir)}`,
    `Target URL: ${targetUrl}`,
    '',
    '## Hard Limits',
    '- Read `AGENTS.md` first.',
    '- Use local/dev services and synthetic evidence only.',
    '- Do not contact real homeowners, buyers, ad platforms, payment processors, SMS/email/phone providers, or public webhooks.',
    '- Do not commit, push, amend, rewrite history, or run destructive git commands.',
    '- Keep generated evidence under ignored `testing/` paths.',
    '',
    '## Observed Findings',
    markdownList(findings),
    '',
    '## Task',
    promptFocus,
    '',
    '## Return',
    '- What you inspected, with file paths and line numbers where relevant.',
    '- The smallest verified change or test gap, if any.',
    '- Exact validation command output or the exact blocker.',
    '',
  ].join('\n');
}

function writeRunnerPrompts({ runId, runDir, targetUrl, findings }) {
  const promptDir = path.join(runDir, 'runner-prompts');
  mkdirSync(promptDir, { recursive: true });
  const prompts = [];
  const effectiveFindings = findings.length ? findings : ['No failing evidence captured; look for the next highest-value deterministic browser regression.'];

  const specs = [
    {
      file: '01-readonly-investigator.md',
      title: 'Read-Only Evidence Investigator',
      mode: 'read-only',
      promptFocus: 'Investigate the evidence and source code. Do not edit files. Return facts, likely root cause, and the narrowest proof command to run next.',
    },
    {
      file: '02-minimal-fix-runner.md',
      title: 'Minimal Fix Runner',
      mode: 'workspace-write',
      promptFocus: 'Make the smallest safe app or test change for the highest-confidence local-only finding. Rerun the narrowest failing validation. Stop if the evidence is insufficient.',
    },
    {
      file: '03-regression-runner.md',
      title: 'Regression Test Runner',
      mode: 'workspace-write',
      promptFocus: 'Convert stable behavior or a reproduced bug into deterministic Playwright coverage with evidence artifacts. Do not weaken existing assertions.',
    },
  ];

  for (const spec of specs) {
    const prompt = buildRunnerPrompt({
      title: spec.title,
      mode: spec.mode,
      runId,
      runDir,
      targetUrl,
      findings: effectiveFindings,
      promptFocus: spec.promptFocus,
    });
    const filePath = path.join(promptDir, spec.file);
    writeFileSync(filePath, prompt);
    prompts.push(relativePath(filePath));
  }
  return prompts;
}

async function dispatchCodexPrompts(promptFiles, maxRunners, timeoutSeconds) {
  const results = [];
  for (const promptFile of promptFiles.slice(0, maxRunners)) {
    const prompt = await fs.readFile(path.join(repoRoot, promptFile), 'utf8');
    results.push(await runCommand(
      `dispatch ${promptFile}`,
      commandName('npm'),
      ['run', 'codex:exec', '--', prompt],
      timeoutSeconds,
    ));
  }
  return results;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const targetUrl = assertLoopbackHttpUrl(args.url ?? process.env.STORMLEAD_ADMIN_URL ?? 'http://127.0.0.1:8003/admin');
  const runId = `${safeRunId(args.run_id)}-self-learning-loop`;
  const runDir = path.join(runsDir, runId);
  const logsDir = path.join(runDir, 'logs');
  mkdirSync(logsDir, { recursive: true });

  const options = {
    targetUrl,
    maxIterations: parseInteger(args.max_iterations, 1, 1, 3),
    includeObserver: parseBoolean(args.include_observer, true),
    includePuppeteer: parseBoolean(args.include_puppeteer, true),
    includeSmoke: parseBoolean(args.include_smoke, false),
    includeV1: parseBoolean(args.include_v1, false),
    includeWorkflowKpis: parseBoolean(args.include_workflow_kpis, true),
    playwrightProject: String(args.playwright_project ?? 'none'),
    observerDurationSeconds: parseInteger(args.observer_duration_seconds, 2, 0, 45),
    puppeteerDurationSeconds: parseInteger(args.puppeteer_duration_seconds, 1, 0, 45),
    headless: parseBoolean(args.headless, true),
    channel: args.channel ?? process.env.STORMLEAD_CHROME_CHANNEL ?? 'chrome',
    executablePath: args.executable_path ?? process.env.STORMLEAD_CHROME_EXECUTABLE_PATH,
    timeoutSeconds: parseInteger(args.timeout_seconds, 240, 30, 900),
    dispatchCodex: parseBoolean(args.dispatch_codex, false),
    maxRunners: parseInteger(args.max_runners, 1, 1, 3),
    failOnFindings: parseBoolean(args.fail_on_findings, false),
  };
  if (!['none', 'api', 'chromium', 'all'].includes(options.playwrightProject)) {
    throw new Error('--playwright-project must be one of: none, api, chromium, all');
  }

  const actions = args.actions_json ? JSON.parse(String(args.actions_json)) : [];
  if (!Array.isArray(actions)) throw new Error('--actions-json must be a JSON array');

  const startedAt = new Date();
  const iterations = [];
  let previousFindings = [];

  for (let number = 1; number <= options.maxIterations; number += 1) {
    const iterationDir = path.join(runDir, 'iterations', String(number).padStart(2, '0'));
    mkdirSync(iterationDir, { recursive: true });
    const steps = [];
    const think = buildThink(number, previousFindings, options);

    await withMcp(async (client) => {
      const health = await runMcpTool(client, 'check_local_services');
      steps.push(health);
      steps.push(await runMcpTool(client, 'list_evidence_runs', { limit: 5 }));
      if (options.includeWorkflowKpis && serviceOk(health, 'ping-post ready')) {
        steps.push(await runMcpTool(client, 'get_workflow_kpis'));
      }
      if (options.includeObserver) {
        steps.push(await runMcpTool(client, 'observe_chrome_page', {
          confirm_synthetic_local: true,
          url: options.targetUrl,
          duration_seconds: options.observerDurationSeconds,
          headless: options.headless,
          channel: options.channel,
          actions: [{ type: 'screenshot', name: `iteration-${number}-mcp-observed`, full_page: true }],
        }));
      }
      if (options.includeSmoke) {
        steps.push(await runMcpTool(client, 'run_local_smoke', {
          confirm_synthetic_local: true,
          timeout_seconds: Math.min(options.timeoutSeconds, 600),
        }));
      }
      if (options.includeV1) {
        steps.push(await runMcpTool(client, 'run_v1_simulation', {
          confirm_synthetic_local: true,
          timeout_seconds: Math.min(options.timeoutSeconds, 600),
        }));
      }
    });

    if (options.playwrightProject !== 'none') {
      const playwrightArgs = ['run', 'test:playwright', '--'];
      if (options.playwrightProject !== 'all') playwrightArgs.push(`--project=${options.playwrightProject}`);
      playwrightArgs.push('--reporter=line');
      steps.push(await runCommand(
        `Playwright ${options.playwrightProject}`,
        commandName('npm'),
        playwrightArgs,
        options.timeoutSeconds,
      ));
    }

    if (options.includePuppeteer) {
      const puppeteerSummary = await runPuppeteerAudit({
        targetUrl: options.targetUrl,
        runId: `${runId}-iteration-${number}`,
        iterationDir,
        headless: options.headless,
        channel: options.channel,
        executablePath: options.executablePath,
        actions,
        durationSeconds: options.puppeteerDurationSeconds,
      });
      steps.push(puppeteerSummary);
    }

    const findings = collectIterationFindings({ steps });
    const decide = buildDecide(findings, runDir);
    const iteration = {
      number,
      think,
      steps,
      observations: observationsFromSteps(steps),
      findings,
      decide,
      artifacts: {
        iteration_dir: relativePath(iterationDir),
        markdown: relativePath(path.join(iterationDir, 'iteration.md')),
      },
    };
    writeIterationMarkdown(iteration, path.join(iterationDir, 'iteration.md'));
    iterations.push(iteration);
    previousFindings = findings;
  }

  const allFindings = iterations.flatMap((iteration) => iteration.findings.map((finding) => `iteration ${iteration.number}: ${finding}`));
  const runnerPrompts = writeRunnerPrompts({ runId, runDir, targetUrl, findings: allFindings });
  const dispatchResults = options.dispatchCodex
    ? await dispatchCodexPrompts(runnerPrompts, options.maxRunners, options.timeoutSeconds)
    : [];

  const summary = {
    schema_version: 1,
    run_id: runId,
    status: allFindings.length ? 'findings' : 'clean',
    ok: true,
    started_at: startedAt.toISOString(),
    finished_at: new Date().toISOString(),
    target_url: targetUrl,
    options: {
      max_iterations: options.maxIterations,
      include_observer: options.includeObserver,
      include_puppeteer: options.includePuppeteer,
      include_smoke: options.includeSmoke,
      include_v1: options.includeV1,
      playwright_project: options.playwrightProject,
      dispatch_codex: options.dispatchCodex,
    },
    research_sources: RESEARCH_SOURCES,
    findings: allFindings,
    artifacts: {
      run_dir: relativePath(runDir),
      summary_json: relativePath(path.join(runDir, 'self-learning-summary.json')),
      learning_markdown: relativePath(path.join(runDir, 'self-learning-loop.md')),
      runner_prompts: runnerPrompts,
    },
    iterations,
    dispatch_results: dispatchResults,
  };

  writeFileSync(path.join(runDir, 'self-learning-summary.json'), JSON.stringify(summary, null, 2) + '\n');
  writeFileSync(
    path.join(runDir, 'self-learning-loop.md'),
    [
      '# StormLead Self-Learning Loop',
      '',
      `Run ID: ${runId}`,
      `Target URL: ${targetUrl}`,
      `Status: ${summary.status}`,
      '',
      '## Web Research Used',
      ...RESEARCH_SOURCES.map((source) => `- ${source.name}: ${source.url} - ${source.note}`),
      '',
      '## Findings',
      markdownList(allFindings),
      '',
      '## Runner Prompts',
      markdownList(runnerPrompts.map((prompt) => `\`${prompt}\``)),
      '',
      '## Iterations',
      ...iterations.map((iteration) => `- Iteration ${iteration.number}: \`${iteration.artifacts.markdown}\``),
      '',
    ].join('\n'),
  );

  console.log(JSON.stringify(summary, null, 2));
  if (options.failOnFindings && allFindings.length) process.exitCode = 1;
}

main().catch((error) => {
  console.error(errorMessage(error));
  process.exit(1);
});
