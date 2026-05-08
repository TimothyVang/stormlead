import { createHmac } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

export const FORM_RECEIVER = process.env.FORM_RECEIVER_URL ?? 'http://127.0.0.1:8002';
export const LANDING = process.env.LANDING_URL ?? 'http://127.0.0.1:8005';

const DEFAULT_WEBHOOK_SECRET = 'whsec_change-me';

function envFileValue(fileName: string, key: string): string | undefined {
  try {
    const lines = readFileSync(resolve(process.cwd(), fileName), 'utf8').split(/\r?\n/);
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const separator = trimmed.indexOf('=');
      if (separator === -1) continue;
      if (trimmed.slice(0, separator).trim() !== key) continue;
      const value = trimmed.slice(separator + 1).trim();
      return value.replace(/^(['"])(.*)\1$/, '$2');
    }
  } catch {
    return undefined;
  }
  return undefined;
}

export function resolveWebhookSecret(): string {
  return (
    process.env.FORMBRICKS_WEBHOOK_SECRET ??
    envFileValue('.env', 'FORMBRICKS_WEBHOOK_SECRET') ??
    envFileValue('.env.example', 'FORMBRICKS_WEBHOOK_SECRET') ??
    DEFAULT_WEBHOOK_SECRET
  );
}

export function decodeSecret(secret: string): Buffer {
  const raw = secret.replace(/^whsec_/, '');
  // Python base64.b64decode(validate=False) silently drops non-base64 chars (e.g. '-').
  // Strip them here so Node and Python produce the same HMAC key.
  const cleaned = raw.replace(/[^A-Za-z0-9+/]/g, '');
  const padded = cleaned + '='.repeat((4 - (cleaned.length % 4)) % 4);
  return Buffer.from(padded, 'base64');
}

// Must match signatures.py:82 — signed payload is "{id}.{ts}." + body (trailing dot after timestamp)
export function signWebhook(
  webhookId: string,
  timestampUnix: number,
  bodyBytes: Buffer,
  secret: string,
): string {
  const rawSecret = decodeSecret(secret);
  const ts = String(timestampUnix);
  const signed = Buffer.concat([Buffer.from(`${webhookId}.${ts}.`), bodyBytes]);
  const sig = createHmac('sha256', rawSecret).update(signed).digest('base64');
  return `v1,${sig}`;
}

export function buildSignedHeaders(
  webhookId: string,
  body: object,
  secret: string,
  nowUnix?: number,
): { headers: Record<string, string>; bodyStr: string } {
  // Sign the exact JSON string — Playwright sends this as-is, preserving HMAC
  const bodyStr = JSON.stringify(body);
  const bodyBytes = Buffer.from(bodyStr);
  const ts = nowUnix ?? Math.floor(Date.now() / 1000);
  return {
    headers: {
      'content-type': 'application/json',
      'webhook-id': webhookId,
      'webhook-timestamp': String(ts),
      'webhook-signature': signWebhook(webhookId, ts, bodyBytes, secret),
    },
    bodyStr,
  };
}

// 600s in past — outside ±300s replay window → triggers 409
export function buildExpiredHeaders(webhookId: string, body: object, secret: string) {
  const staleTs = Math.floor(Date.now() / 1000) - 600;
  return buildSignedHeaders(webhookId, body, secret, staleTs);
}

export function buildWrongSignatureHeaders(webhookId: string, body: object, secret: string) {
  const wrongSecret = 'whsec_' + Buffer.from('wrong-secret-key-32bytes-padded!!').toString('base64');
  return buildSignedHeaders(webhookId, body, wrongSecret);
}

export function buildMissingHeadersRequest(body: object): { headers: Record<string, string>; body: string } {
  return { headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) };
}

export interface EnvelopeParams {
  scenario: string;
  phone: string;
  email: string;
  state: string;
  zip: string;
  campaignId?: string;
  webhookId?: string;
  service?: string;
}

export function buildEnvelope(p: EnvelopeParams): { envelope: object; webhookId: string } {
  const webhookId = p.webhookId ?? `pw-${p.scenario}-${Date.now()}`;
  const envelope = {
    event: 'responseFinished',
    webhookId,
    data: {
      id: `resp-${p.scenario}-${Date.now()}`,
      surveyId: 'survey_playwright_test',
      data: {
        name: `Playwright ${p.scenario}`,
        phone: p.phone,
        email: p.email,
        address_line1: '999 Playwright Test Ln',
        city: 'Testville',
        state: p.state,
        zip: p.zip,
        consent_text: 'I agree to be contacted regarding storm damage repair services.',
        requested_service: p.service ?? 'tree_removal',
        campaign_source: 'local_playwright_test',
        campaign_id: p.campaignId ?? `local_${p.scenario}`,
        dwell_ms: 9000,
      },
      ttc: { name: 1500, phone: 2200, consent_text: 4500 },
      meta: {
        url: `${LANDING}/${p.scenario}`,
        userAgent: 'Playwright/Test',
      },
      finished: true,
    },
  };
  return { envelope, webhookId };
}
