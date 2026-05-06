#!/usr/bin/env node

import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

const repoRoot = path.resolve(fileURLToPath(new URL('../..', import.meta.url)));
const expectedTools = [
  'check_local_services',
  'get_admin_kpis',
  'get_workflow_kpis',
  'get_launch_readiness',
  'get_lead_timeline',
  'get_evidence_manifest',
  'list_buyers_redacted',
  'list_evidence_runs',
  'list_recent_workflow_runs',
  'observe_chrome_page',
  'run_chrome_observer_functional_test',
  'run_local_smoke',
  'run_v1_simulation',
].sort();
const commandTools = new Set([
  'observe_chrome_page',
  'run_chrome_observer_functional_test',
  'run_local_smoke',
  'run_v1_simulation',
]);

function textContent(result) {
  return (result.content || [])
    .filter((item) => item.type === 'text')
    .map((item) => item.text)
    .join('\n');
}

function assertToolAnnotations(tool) {
  assert.equal(tool.annotations?.destructiveHint, false, `${tool.name} should be non-destructive`);
  assert.equal(tool.annotations?.openWorldHint, false, `${tool.name} should not be open-world`);
  assert.equal(tool.annotations?.readOnlyHint, !commandTools.has(tool.name), `${tool.name} readOnlyHint mismatch`);
}

const nonLocal = spawnSync(process.execPath, ['tools/mcp/stormlead-local-ops.mjs'], {
  cwd: repoRoot,
  env: { ...process.env, STORMLEAD_ADMIN_URL: 'https://example.com' },
  encoding: 'utf8',
  timeout: 5000,
});
assert.notEqual(nonLocal.status, 0, 'non-local MCP URL override should fail');
assert.match(`${nonLocal.stdout}\n${nonLocal.stderr}`, /loopback hostname/, 'non-local MCP URL override should explain loopback requirement');

const client = new Client({ name: 'stormlead-local-ops-smoke', version: '0.1.0' });
const transport = new StdioClientTransport({
  command: process.execPath,
  args: ['tools/mcp/stormlead-local-ops.mjs'],
  cwd: repoRoot,
  stderr: 'pipe',
});

try {
  await client.connect(transport);
  const listed = await client.listTools();
  const toolNames = listed.tools.map((tool) => tool.name).sort();
  assert.deepEqual(toolNames, expectedTools, 'MCP tool inventory changed; update docs and smoke expectations together');
  for (const tool of listed.tools) {
    assertToolAnnotations(tool);
  }
  const evidence = await client.callTool({ name: 'list_evidence_runs', arguments: { limit: 1 } });
  assert(Array.isArray(evidence.content), 'list_evidence_runs should return MCP content');
  const simulationRefusal = await client.callTool({ name: 'run_v1_simulation', arguments: { confirm_synthetic_local: false } });
  assert.match(textContent(simulationRefusal), /Refusing to run/, 'run_v1_simulation should require synthetic confirmation');
  const smokeRefusal = await client.callTool({ name: 'run_local_smoke', arguments: { confirm_synthetic_local: false } });
  assert.match(textContent(smokeRefusal), /Refusing to run/, 'run_local_smoke should require synthetic confirmation');
  const observeRefusal = await client.callTool({ name: 'observe_chrome_page', arguments: { confirm_synthetic_local: false } });
  assert.match(textContent(observeRefusal), /Refusing to run/, 'observe_chrome_page should require synthetic confirmation');
  const observerFunctionalRefusal = await client.callTool({ name: 'run_chrome_observer_functional_test', arguments: { confirm_synthetic_local: false } });
  assert.match(textContent(observerFunctionalRefusal), /Refusing to run/, 'run_chrome_observer_functional_test should require synthetic confirmation');
  const traversal = await client.callTool({ name: 'get_evidence_manifest', arguments: { run_id: '../outside' } });
  assert.equal(traversal.isError, true, 'get_evidence_manifest should reject path traversal');
  assert.match(textContent(traversal), /run_id|testing\/runs|path/i, 'path traversal rejection should explain the invalid run_id');
  console.log(`stormlead local ops MCP ok (${toolNames.length} tools)`);
} finally {
  await client.close();
}
