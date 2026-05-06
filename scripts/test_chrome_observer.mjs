#!/usr/bin/env node

import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { promises as fs } from 'node:fs';
import { createServer } from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

const execFileAsync = promisify(execFile);
const repoRoot = path.resolve(fileURLToPath(new URL('..', import.meta.url)));

function textContent(result) {
  return (result.content || [])
    .filter((item) => item.type === 'text')
    .map((item) => item.text)
    .join('\n');
}

function eventFile(summary) {
  return path.join(repoRoot, summary.artifacts.chrome_events_jsonl);
}

async function readEvents(summary) {
  const raw = await fs.readFile(eventFile(summary), 'utf8');
  return raw
    .trim()
    .split('\n')
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function assertCapturedFunctionalEvidence(summary, events) {
  const eventTypes = new Set(events.map((event) => event.type));
  const serialized = JSON.stringify(events);

  assert.equal(summary.ok, true, `observer should complete successfully: ${JSON.stringify(summary)}`);
  assert(eventTypes.has('browser.request'), 'expected request events');
  assert(eventTypes.has('browser.response'), 'expected response events');
  assert(eventTypes.has('browser.console'), 'expected console events');
  assert(eventTypes.has('browser.http_error'), 'expected HTTP error events');
  assert.match(serialized, /observer-functional-info/, 'expected info console log');
  assert.match(serialized, /observer-functional-warning/, 'expected warning console log');
  assert.match(serialized, /observer-functional-error/, 'expected error console log');
  assert.match(serialized, /button-clicked/, 'expected action-triggered console log');
  assert.match(serialized, /forced failure for observer/, 'expected failed response body preview');
  assert.match(serialized, /action failure for observer/, 'expected action failed response body preview');
}

function createFunctionalServer() {
  const server = createServer((request, response) => {
    if (request.url === '/api/ok') {
      response.writeHead(200, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ ok: true, source: 'functional-test' }));
      return;
    }

    if (request.url === '/api/fail') {
      response.writeHead(500, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ error: 'forced failure for observer' }));
      return;
    }

    if (request.url === '/api/action-fail') {
      response.writeHead(418, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ error: 'action failure for observer' }));
      return;
    }

    response.writeHead(200, { 'content-type': 'text/html' });
    response.end(`<!doctype html>
      <html lang="en">
        <head><title>Chrome Observer Functional Test</title></head>
        <body>
          <h1>Chrome Observer Functional Test</h1>
          <button id="action" type="button">Trigger browser evidence</button>
          <script>
            console.log('observer-functional-info');
            console.warn('observer-functional-warning');
            console.error('observer-functional-error');
            fetch('/api/ok').then((response) => response.json()).then((body) => console.log('ok-body', body.ok));
            fetch('/api/fail').then((response) => response.text()).then((body) => console.log('fail-body-length', body.length));
            document.querySelector('#action').addEventListener('click', () => {
              console.log('button-clicked');
              fetch('/api/action-fail');
            });
          </script>
        </body>
      </html>`);
  });

  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      resolve({ server, url: `http://127.0.0.1:${address.port}/` });
    });
  });
}

async function runCliFunctional(url) {
  const actions = [
    { type: 'wait_for_selector', selector: '#action' },
    { type: 'click', selector: '#action' },
    { type: 'wait', ms: 500 },
  ];
  const result = await execFileAsync(
    process.execPath,
    [
      'scripts/chrome_observe.mjs',
      '--url', url,
      '--duration-seconds', '0',
      '--headless', 'true',
      '--run-id', `functional-cli-${Date.now()}`,
      '--actions-json', JSON.stringify(actions),
    ],
    { cwd: repoRoot, encoding: 'utf8', timeout: 90_000, maxBuffer: 10 * 1024 * 1024 },
  );
  const summary = JSON.parse(result.stdout);
  const events = await readEvents(summary);
  assertCapturedFunctionalEvidence(summary, events);
  return summary;
}

async function runMcpFunctional(url) {
  const client = new Client({ name: 'chrome-observer-functional-test', version: '0.1.0' });
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: ['tools/mcp/stormlead-local-ops.mjs'],
    cwd: repoRoot,
    stderr: 'pipe',
  });

  try {
    await client.connect(transport);
    const result = await client.callTool({
      name: 'observe_chrome_page',
      arguments: {
        confirm_synthetic_local: true,
        url,
        duration_seconds: 0,
        headless: true,
        run_id: `functional-mcp-${Date.now()}`,
        actions: [
          { type: 'wait_for_selector', selector: '#action' },
          { type: 'click', selector: '#action' },
          { type: 'wait', ms: 500 },
        ],
      },
    });
    const payload = JSON.parse(textContent(result));
    const summary = payload.result;
    const events = await readEvents(summary);
    assertCapturedFunctionalEvidence(summary, events);
    return summary;
  } finally {
    await client.close();
  }
}

const { server, url } = await createFunctionalServer();
try {
  const cliSummary = await runCliFunctional(url);
  const mcpSummary = await runMcpFunctional(url);
  console.log(JSON.stringify({
    ok: true,
    url,
    cli_artifacts: cliSummary.artifacts,
    mcp_artifacts: mcpSummary.artifacts,
  }, null, 2));
} finally {
  await new Promise((resolve) => server.close(resolve));
}
