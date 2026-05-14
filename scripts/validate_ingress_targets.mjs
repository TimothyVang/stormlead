#!/usr/bin/env node

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const repoRoot = path.resolve(fileURLToPath(new URL('..', import.meta.url)));
const composePath = path.join(repoRoot, 'infra', 'compose', 'dev', 'docker-compose.yml');
const caddyPath = path.join(repoRoot, 'infra', 'caddy', 'Caddyfile');

function parseComposeServices(text) {
  const services = new Set();
  let inServices = false;

  for (const line of text.split(/\r?\n/)) {
    if (/^services:\s*$/.test(line)) {
      inServices = true;
      continue;
    }
    if (!inServices) continue;
    if (/^[A-Za-z0-9_.-]+:\s*$/.test(line)) break;

    const service = line.match(/^  ([A-Za-z0-9_.-]+):\s*(?:#.*)?$/);
    if (service) services.add(service[1]);
  }

  return services;
}

function parseCaddyReverseProxyTargets(text) {
  const targets = new Set();

  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed.startsWith('reverse_proxy ')) continue;

    for (const token of trimmed.split(/\s+/).slice(1)) {
      if (token === '{') break;
      const target = token.match(/^([A-Za-z0-9_.-]+):\d+$/);
      if (target) targets.add(target[1]);
    }
  }

  return targets;
}

const composeServices = parseComposeServices(readFileSync(composePath, 'utf8'));
const caddyText = readFileSync(caddyPath, 'utf8');
const caddyTargets = parseCaddyReverseProxyTargets(caddyText);
const missingTargets = [...caddyTargets].filter((target) => !composeServices.has(target));
const missingHeaderSnippets = [
  "Permissions-Policy \"geolocation=(self), camera=(), microphone=()\"",
  "script-src 'self' 'unsafe-inline' {$FORMBRICKS_CSP_SCRIPT_SRC:}",
  "connect-src 'self' {$FORMBRICKS_CSP_CONNECT_SRC:}",
].filter((snippet) => !caddyText.includes(snippet));

if (missingTargets.length > 0) {
  console.error(
    `Caddy reverse_proxy targets missing from dev Compose services: ${missingTargets.join(', ')}`,
  );
  process.exitCode = 1;
} else if (missingHeaderSnippets.length > 0) {
  console.error(
    `Caddy public security headers missing required snippets: ${missingHeaderSnippets.join(', ')}`,
  );
  process.exitCode = 1;
} else {
  console.log(
    `ingress targets valid: ${caddyTargets.size} Caddy target(s) declared in dev Compose; public security headers valid`,
  );
}
