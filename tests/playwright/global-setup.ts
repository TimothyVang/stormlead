import { request } from '@playwright/test';
import { FORM_RECEIVER, PING_POST, LANDING, BUYER_PORTAL } from './helpers/api';

const HEALTH_ATTEMPTS = 5;
const HEALTH_RETRY_DELAY_MS = 1_500;
const LOCAL_TEST_HOSTS = new Set(['127.0.0.1', 'localhost']);

function assertLoopbackUrl(label: string, rawUrl: string): void {
  const url = new URL(rawUrl);
  if (url.protocol !== 'http:') {
    throw new Error(`[global-setup] ${label} must use local HTTP, got ${rawUrl}`);
  }
  if (!LOCAL_TEST_HOSTS.has(url.hostname) && !url.hostname.endsWith('.localhost')) {
    throw new Error(`[global-setup] ${label} must stay on loopback/local host, got ${rawUrl}`);
  }
}

async function ping(baseUrl: string, label: string, required: boolean): Promise<void> {
  let lastError = 'not attempted';
  for (let attempt = 1; attempt <= HEALTH_ATTEMPTS; attempt += 1) {
    const ctx = await request.newContext();
    try {
      const res = await ctx.get(`${baseUrl}/healthz`, { timeout: 5000 });
      if (!res.ok()) {
        lastError = `healthz returned ${res.status()}`;
      } else {
        await ctx.dispose();
        console.log(`[global-setup] ${label}: ok`);
        return;
      }
    } catch (e) {
      lastError = e instanceof Error ? e.message : String(e);
    }
    await ctx.dispose();
    if (attempt < HEALTH_ATTEMPTS) {
      await new Promise((resolve) => setTimeout(resolve, HEALTH_RETRY_DELAY_MS));
    }
  }

  const msg = `[global-setup] ${label} unreachable after ${HEALTH_ATTEMPTS} attempts: ${lastError}`;
  if (required) throw new Error(msg);
  console.warn(msg);
}

export default async function globalSetup() {
  assertLoopbackUrl('FORM_RECEIVER', FORM_RECEIVER);
  assertLoopbackUrl('PING_POST', PING_POST);
  assertLoopbackUrl('LANDING', LANDING);
  assertLoopbackUrl('BUYER_PORTAL', BUYER_PORTAL);
  await ping(FORM_RECEIVER, 'form-receiver (8002)', true);
  await ping(PING_POST, 'ping-post (8003)', true);
  await ping(LANDING, 'landing', true);
  await ping(BUYER_PORTAL, 'buyer-portal (8004)', true);
}
