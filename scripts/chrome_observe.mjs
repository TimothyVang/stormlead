#!/usr/bin/env node

import { chromium } from '@playwright/test';
import { appendFileSync, mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const MAX_TEXT_LENGTH = Number(process.env.STORMLEAD_BROWSER_LOG_MAX_TEXT ?? 4000);
const MAX_BODY_LENGTH = Number(process.env.STORMLEAD_BROWSER_LOG_MAX_BODY ?? 8000);

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

function truncate(value, maxLength = MAX_TEXT_LENGTH) {
  const text = String(value ?? '');
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...[truncated ${text.length - maxLength} chars]`;
}

function errorMessage(error) {
  return error instanceof Error ? error.message : String(error);
}

function assertLoopbackHttpUrl(value) {
  const url = new URL(value);
  const hostname = url.hostname.toLowerCase();
  const isLoopback = hostname === 'localhost'
    || hostname === '::1'
    || hostname === '[::1]'
    || hostname.startsWith('127.');
  if (!['http:', 'https:'].includes(url.protocol) || !isLoopback) {
    throw new Error(`Chrome observer only accepts loopback HTTP(S) URLs: ${value}`);
  }
  return url.toString();
}

function safeRunId(value) {
  if (!value) return new Date().toISOString().replace(/[:.]/g, '-');
  return String(value).replace(/[^A-Za-z0-9_.-]/g, '-').slice(0, 120);
}

function relativePath(value) {
  return path.relative(repoRoot, value).replaceAll(path.sep, '/');
}

function isReadableResponseBody(response) {
  const resourceType = response.request().resourceType();
  if (!['document', 'fetch', 'xhr'].includes(resourceType)) return false;
  const contentType = response.headers()['content-type'] ?? '';
  return /json|text|html|plain|problem\+json/i.test(contentType);
}

function isObservedNetworkResource(resourceType) {
  return ['document', 'fetch', 'xhr', 'websocket'].includes(resourceType);
}

function installObserver(page, runId, eventsPath) {
  const eventCounts = {};
  const recentErrors = [];

  function record(type, severity, data = {}) {
    const event = {
      schema_version: 1,
      at: new Date().toISOString(),
      run_id: runId,
      type,
      severity,
      page_url: page.url(),
      data,
    };
    eventCounts[type] = (eventCounts[type] ?? 0) + 1;
    if (severity === 'error') recentErrors.push(event);
    appendFileSync(eventsPath, JSON.stringify(event) + '\n');
  }

  page.on('console', (message) => {
    const level = message.type();
    record('browser.console', level === 'error' ? 'error' : level === 'warning' ? 'warning' : 'info', {
      level,
      text: truncate(message.text()),
      location: message.location(),
    });
  });
  page.on('pageerror', (error) => record('browser.page_error', 'error', { message: errorMessage(error) }));
  page.on('request', (request) => {
    if (!isObservedNetworkResource(request.resourceType())) return;
    record('browser.request', 'info', {
      method: request.method(),
      url: request.url(),
      resource_type: request.resourceType(),
    });
  });
  page.on('requestfailed', (request) => record('browser.request_failed', 'error', {
    method: request.method(),
    url: request.url(),
    resource_type: request.resourceType(),
    failure: request.failure()?.errorText ?? null,
  }));
  page.on('response', (response) => {
    void (async () => {
      if (response.status() < 400) {
        if (isObservedNetworkResource(response.request().resourceType())) {
          record('browser.response', 'info', {
            method: response.request().method(),
            url: response.url(),
            status: response.status(),
            resource_type: response.request().resourceType(),
            content_type: response.headers()['content-type'] ?? null,
          });
        }
        return;
      }
      const data = {
        method: response.request().method(),
        url: response.url(),
        status: response.status(),
        status_text: response.statusText(),
        resource_type: response.request().resourceType(),
        content_type: response.headers()['content-type'] ?? null,
      };
      if (isReadableResponseBody(response)) {
        try {
          data.body_preview = truncate(await response.text(), MAX_BODY_LENGTH);
        } catch (error) {
          data.body_error = errorMessage(error);
        }
      }
      record('browser.http_error', 'error', data);
    })();
  });
  page.on('websocket', (socket) => {
    record('browser.websocket_open', 'info', { url: socket.url() });
    socket.on('framesent', (frame) => record('browser.websocket_frame_sent', 'info', {
      url: socket.url(),
      payload: truncate(frame.payload),
    }));
    socket.on('framereceived', (frame) => record('browser.websocket_frame_received', 'info', {
      url: socket.url(),
      payload: truncate(frame.payload),
    }));
    socket.on('close', () => record('browser.websocket_close', 'info', { url: socket.url() }));
  });
  page.on('crash', () => record('browser.page_crash', 'error', { message: 'Page crashed' }));
  page.on('framenavigated', (frame) => {
    if (frame === page.mainFrame()) record('browser.navigation', 'info', { url: frame.url() });
  });

  return { eventCounts, recentErrors, record };
}

async function runAction(page, action, observer, screenshotsDir, index) {
  const type = action?.type;
  observer.record('observer.action_started', 'info', { index, action });
  switch (type) {
    case 'click':
      await page.locator(action.selector).first().click({ timeout: action.timeout_ms ?? 30_000 });
      break;
    case 'fill':
      await page.locator(action.selector).first().fill(String(action.value ?? ''), { timeout: action.timeout_ms ?? 30_000 });
      break;
    case 'press':
      await page.locator(action.selector).first().press(String(action.key ?? 'Enter'), { timeout: action.timeout_ms ?? 30_000 });
      break;
    case 'wait':
      await page.waitForTimeout(Math.max(0, Math.min(Number(action.ms ?? 1000), 60_000)));
      break;
    case 'wait_for_selector':
      await page.locator(action.selector).first().waitFor({ state: action.state ?? 'visible', timeout: action.timeout_ms ?? 30_000 });
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
      await page.screenshot({ path: screenshotPath, fullPage: action.full_page !== false, timeout: 5000 });
      observer.record('observer.screenshot', 'info', { path: relativePath(screenshotPath) });
      break;
    }
    default:
      throw new Error(`Unsupported observer action type: ${type}`);
  }
  observer.record('observer.action_finished', 'info', { index, action });
}

const args = parseArgs(process.argv.slice(2));
const targetUrl = assertLoopbackHttpUrl(args.url ?? process.env.STORMLEAD_ADMIN_URL ?? 'http://127.0.0.1:8003/admin');
const durationSeconds = Math.max(0, Math.min(Number(args.duration_seconds ?? 10), 120));
const headless = parseBoolean(args.headless, true);
const slowMo = Number(args.slow_mo_ms ?? process.env.STORMLEAD_PLAYWRIGHT_SLOW_MO_MS ?? 0);
const channel = args.channel ?? process.env.STORMLEAD_CHROME_CHANNEL;
const executablePath = args.executable_path ?? process.env.STORMLEAD_CHROME_EXECUTABLE_PATH;
const actions = args.actions_json ? JSON.parse(String(args.actions_json)) : [];
if (!Array.isArray(actions)) throw new Error('--actions-json must be a JSON array');

const runId = `${safeRunId(args.run_id)}-chrome-observe`;
const runDir = path.join(repoRoot, 'testing', 'runs', runId);
const logsDir = path.join(runDir, 'logs');
const screenshotsDir = path.join(runDir, 'screenshots');
const eventsPath = path.join(logsDir, 'chrome-events.jsonl');
const summaryPath = path.join(logsDir, 'chrome-summary.json');
mkdirSync(logsDir, { recursive: true });
mkdirSync(screenshotsDir, { recursive: true });

let browser;
let page;
let observer;
let ok = true;
let failure = null;
const startedAt = new Date().toISOString();

try {
  const launchOptions = {
    headless,
    slowMo: Number.isFinite(slowMo) ? slowMo : 0,
  };
  if (executablePath) launchOptions.executablePath = String(executablePath);
  else if (channel) launchOptions.channel = String(channel);

  browser = await chromium.launch(launchOptions);
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  page = await context.newPage();
  observer = installObserver(page, runId, eventsPath);
  observer.record('observer.started', 'info', {
    target_url: targetUrl,
    headless,
    channel: channel ?? null,
    executable_path: executablePath ?? null,
  });

  await page.goto(targetUrl, { waitUntil: 'commit', timeout: 20_000 });
  await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => undefined);
  await page.screenshot({ path: path.join(screenshotsDir, '00-initial.png'), fullPage: true, timeout: 5000 });

  for (let index = 0; index < actions.length; index += 1) {
    await runAction(page, actions[index], observer, screenshotsDir, index + 1);
  }

  if (durationSeconds > 0) await page.waitForTimeout(durationSeconds * 1000);
  await page.screenshot({ path: path.join(screenshotsDir, 'final.png'), fullPage: true, timeout: 5000 });
  observer.record('observer.finished', 'info', { final_url: page.url() });
} catch (error) {
  ok = false;
  failure = errorMessage(error);
  if (observer) observer.record('observer.failed', 'error', { error: failure });
  if (page) {
    await page.screenshot({ path: path.join(screenshotsDir, 'failure.png'), fullPage: true, timeout: 5000 }).catch(() => undefined);
  }
} finally {
  if (browser) await browser.close().catch(() => undefined);
}

const summary = {
  schema_version: 1,
  ok,
  run_id: runId,
  started_at: startedAt,
  finished_at: new Date().toISOString(),
  target_url: targetUrl,
  final_url: page?.url?.() ?? null,
  error: failure,
  event_counts: observer?.eventCounts ?? {},
  error_count: observer?.recentErrors?.length ?? 0,
  recent_errors: observer?.recentErrors?.slice(-25) ?? [],
  artifacts: {
    run_dir: relativePath(runDir),
    chrome_events_jsonl: relativePath(eventsPath),
    chrome_summary_json: relativePath(summaryPath),
    screenshots_dir: relativePath(screenshotsDir),
  },
};

writeFileSync(summaryPath, JSON.stringify(summary, null, 2) + '\n');
console.log(JSON.stringify(summary, null, 2));
if (!ok) process.exitCode = 1;
