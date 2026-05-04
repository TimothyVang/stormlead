#!/usr/bin/env node

import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

const repoRoot = path.resolve(fileURLToPath(new URL('../..', import.meta.url)));

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
  for (const required of [
    'check_local_services',
    'get_launch_readiness',
    'list_evidence_runs',
    'run_v1_simulation',
  ]) {
    assert(toolNames.includes(required), `missing MCP tool: ${required}`);
  }
  const evidence = await client.callTool({ name: 'list_evidence_runs', arguments: { limit: 1 } });
  assert(Array.isArray(evidence.content), 'list_evidence_runs should return MCP content');
  console.log(`stormlead local ops MCP ok (${toolNames.length} tools)`);
} finally {
  await client.close();
}
