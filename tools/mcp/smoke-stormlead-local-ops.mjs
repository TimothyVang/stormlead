#!/usr/bin/env node

import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
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
  'prepare_tars_exploration',
  'run_tars_exploration',
  'run_chrome_observer_functional_test',
  'run_local_smoke',
  'run_self_learning_loop',
  'run_v1_simulation',
].sort();
const commandTools = new Set([
  'observe_chrome_page',
  'prepare_tars_exploration',
  'run_tars_exploration',
  'run_chrome_observer_functional_test',
  'run_local_smoke',
  'run_self_learning_loop',
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

function readJson(relativePath) {
  return JSON.parse(readFileSync(path.join(repoRoot, relativePath), 'utf8'));
}

function assertExistingArtifact(relativePath, label) {
  assert(existsSync(path.join(repoRoot, relativePath)), `${label} should exist at ${relativePath}`);
}

const nonLocal = spawnSync(process.execPath, ['tools/mcp/stormlead-local-ops.mjs'], {
  cwd: repoRoot,
  env: { ...process.env, STORMLEAD_ADMIN_URL: 'http://127.evil.example' },
  encoding: 'utf8',
  timeout: 5000,
});
assert.notEqual(nonLocal.status, 0, 'non-local MCP URL override should fail');
assert.match(`${nonLocal.stdout}\n${nonLocal.stderr}`, /loopback hostname/, 'non-local MCP URL override should explain loopback requirement');

const nonLocalTars = spawnSync(process.execPath, ['scripts/prepare_tars_exploration.mjs', '--targets', 'admin'], {
  cwd: repoRoot,
  env: { ...process.env, STORMLEAD_ADMIN_URL: 'http://127.0.0.1.evil.example' },
  encoding: 'utf8',
  timeout: 5000,
});
assert.notEqual(nonLocalTars.status, 0, 'TARS generator should reject crafted 127-prefixed hostnames');
assert.match(`${nonLocalTars.stdout}\n${nonLocalTars.stderr}`, /loopback HTTP\(S\)/, 'TARS generator rejection should explain loopback requirement');

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
  const tarsRefusal = await client.callTool({ name: 'prepare_tars_exploration', arguments: { confirm_synthetic_local: false } });
  assert.match(textContent(tarsRefusal), /Refusing to run/, 'prepare_tars_exploration should require synthetic confirmation');
  const tarsRunRefusal = await client.callTool({ name: 'run_tars_exploration', arguments: { confirm_synthetic_local: false } });
  assert.match(textContent(tarsRunRefusal), /Refusing to run/, 'run_tars_exploration should require synthetic confirmation');
  const tarsRunMissingPackage = await client.callTool({
    name: 'run_tars_exploration',
    arguments: { confirm_synthetic_local: true, run_id: `mcp-smoke-missing-${Date.now()}`, targets: ['admin'] },
  });
  assert.equal(tarsRunMissingPackage.isError, true, 'run_tars_exploration should invoke the runner and surface missing package errors');
  assert.match(textContent(tarsRunMissingPackage), /Missing TARS package artifact/, 'run_tars_exploration should report missing prepared package artifacts');
  const tarsRunId = `mcp-smoke-tars-${Date.now()}`;
  const tarsPrepare = await client.callTool({
    name: 'prepare_tars_exploration',
    arguments: { confirm_synthetic_local: true, targets: ['admin'], run_id: tarsRunId },
  });
  const tarsPayload = JSON.parse(textContent(tarsPrepare));
  assert.equal(tarsPayload.local_only, true, 'prepare_tars_exploration response should be local-only');
  assert.equal(tarsPayload.command.ok, true, 'prepare_tars_exploration child command should pass');
  assert.equal(tarsPayload.result.ok, true, 'prepare_tars_exploration result should be ok');
  assert(tarsPayload.result.evidence_manifest, 'prepare_tars_exploration should return evidence_manifest');
  const tarsManifest = readJson(tarsPayload.result.evidence_manifest);
  assert.equal(tarsManifest.local_only, true, 'TARS evidence manifest should be local-only');
  assert.equal(tarsManifest.safety.loopback_only, true, 'TARS evidence manifest should record loopback safety');
  assert.deepEqual(tarsManifest.target_ids, ['admin'], 'TARS evidence manifest should preserve requested targets');
  assertExistingArtifact(tarsManifest.artifacts.brief, 'TARS brief');
  assertExistingArtifact(tarsManifest.artifacts.runner_prompt, 'TARS runner prompt');
  assertExistingArtifact(tarsManifest.artifacts.targets, 'TARS targets manifest');
  assertExistingArtifact(tarsManifest.artifacts.review_template, 'TARS review template');
  assertExistingArtifact(tarsManifest.artifacts.findings_jsonl, 'TARS findings JSONL');
  assertExistingArtifact(tarsManifest.artifacts.screenshots_dir, 'TARS screenshots directory');
  const collision = spawnSync(process.execPath, ['scripts/prepare_tars_exploration.mjs', '--run-id', tarsRunId, '--targets', 'admin'], {
    cwd: repoRoot,
    encoding: 'utf8',
    timeout: 5000,
  });
  assert.notEqual(collision.status, 0, 'TARS generator should refuse to overwrite an existing run directory by default');
  assert.match(`${collision.stdout}\n${collision.stderr}`, /already exists/, 'TARS collision refusal should explain the existing run');
  const observerFunctionalRefusal = await client.callTool({ name: 'run_chrome_observer_functional_test', arguments: { confirm_synthetic_local: false } });
  assert.match(textContent(observerFunctionalRefusal), /Refusing to run/, 'run_chrome_observer_functional_test should require synthetic confirmation');
  const selfLearningRefusal = await client.callTool({ name: 'run_self_learning_loop', arguments: { confirm_synthetic_local: false } });
  assert.match(textContent(selfLearningRefusal), /Refusing to run/, 'run_self_learning_loop should require synthetic confirmation');
  const traversal = await client.callTool({ name: 'get_evidence_manifest', arguments: { run_id: '../outside' } });
  assert.equal(traversal.isError, true, 'get_evidence_manifest should reject path traversal');
  assert.match(textContent(traversal), /run_id|testing\/runs|path/i, 'path traversal rejection should explain the invalid run_id');
  console.log(`stormlead local ops MCP ok (${toolNames.length} tools)`);
} finally {
  await client.close();
}
