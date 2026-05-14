import { once } from 'node:events';
import { createServer, type IncomingMessage } from 'node:http';
import { test as base, expect } from '@playwright/test';
import { StormLeadApiClient, runSeed, syntheticPhone, syntheticEmail } from '../helpers/api';
import { resolveWebhookSecret } from '../helpers/webhook';

export interface BuyerWebhookEvent {
  url: string;
  mode: string;
  body: Record<string, unknown>;
  receivedAt: string;
}

const buyerWebhookEvents: BuyerWebhookEvent[] = [];
let buyerWebhookPort = 0;
let buyerWebhookBase = '';

export function clearBuyerWebhookEvents(): void {
  buyerWebhookEvents.length = 0;
}

export function getBuyerWebhookEvents(): BuyerWebhookEvent[] {
  return [...buyerWebhookEvents];
}

export function buyerWebhookUrl(path: string): string {
  if (!buyerWebhookBase) throw new Error('buyer webhook listener is not ready');
  return `${buyerWebhookBase}${path.startsWith('/') ? path : `/${path}`}`;
}

function headerValue(value: IncomingMessage['headers'][string]): string {
  if (Array.isArray(value)) return value.join(',');
  return value ?? '';
}

function isAllowedBuyerWebhookRemoteAddress(remoteAddress: string | undefined): boolean {
  const address = (remoteAddress ?? '').replace(/^::ffff:/, '');
  if (address === '127.0.0.1' || address === '::1') return true;

  const octets = address.split('.').map((value) => Number.parseInt(value, 10));
  if (octets.length !== 4 || octets.some((value) => Number.isNaN(value))) return false;
  const [first, second, third] = octets;
  return (first === 172 && second >= 16 && second <= 31) || (first === 192 && second === 168 && third === 65);
}

function localBuyerWebhookHosts(): Set<string> {
  const hosts = new Set([
    `127.0.0.1:${buyerWebhookPort}`,
    `localhost:${buyerWebhookPort}`,
    `host.docker.internal:${buyerWebhookPort}`,
  ]);
  try {
    hosts.add(new URL(buyerWebhookBase).host.toLowerCase());
  } catch {
    // The base is validated by construction; keep the request guard closed if not set yet.
  }
  return hosts;
}

function isAllowedBuyerWebhookRequest(req: IncomingMessage): boolean {
  const host = headerValue(req.headers.host).toLowerCase();
  return localBuyerWebhookHosts().has(host) && isAllowedBuyerWebhookRemoteAddress(req.socket.remoteAddress);
}

export interface StormLeadFixtures {
  apiClient: StormLeadApiClient;
  testRunId: string;
  seed: number;
  phone: (offset: number) => string;
  email: (scenario: string) => string;
  webhookSecret: string;
  buyerWebhookServer: void;
}

async function readRequestBody(req: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  const raw = Buffer.concat(chunks).toString('utf8');
  if (!raw) {
    throw new Error('empty buyer webhook request body');
  }
  return JSON.parse(raw) as Record<string, unknown>;
}

export const test = base.extend<StormLeadFixtures>({
  apiClient: async ({ request }, use) => {
    await use(new StormLeadApiClient(request));
  },

  testRunId: async ({}, use) => {
    await use(`pw-${Date.now()}`);
  },

  seed: async ({}, use) => {
    await use(runSeed());
  },

  phone: async ({ seed }, use) => {
    await use((offset: number) => syntheticPhone(seed, offset));
  },

  email: async ({ seed }, use) => {
    await use((scenario: string) => syntheticEmail(scenario, seed));
  },

  webhookSecret: async ({}, use) => {
    await use(resolveWebhookSecret());
  },

  buyerWebhookServer: [async ({}, use) => {
    const server = createServer(async (req, res) => {
      if (req.method !== 'POST' || !req.url?.startsWith('/buyer-')) {
        res.writeHead(404, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ error: 'not_found' }));
        return;
      }

      if (!isAllowedBuyerWebhookRequest(req)) {
        res.writeHead(403, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ error: 'non_local_buyer_webhook_request' }));
        return;
      }

      let body: Record<string, unknown>;
      try {
        body = await readRequestBody(req);
      } catch (error) {
        res.writeHead(400, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ error: error instanceof Error ? error.message : 'invalid_json' }));
        return;
      }
      const mode = headerValue(req.headers['x-stormlead-mode']);
      buyerWebhookEvents.push({
        url: req.url ?? '',
        mode,
        body,
        receivedAt: new Date().toISOString(),
      });

      if (mode === 'ping' && req.url.includes('reject-ping')) {
        res.writeHead(200, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ accept: false }));
        return;
      }

      if (mode === 'post' && req.url.includes('fail-post')) {
        res.writeHead(500, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ accepted: false, error: 'synthetic_post_failure' }));
        return;
      }

      res.writeHead(200, { 'content-type': 'application/json' });
      if (mode === 'ping') {
        res.end(JSON.stringify({ accept: true, bid_cents: 30_000 }));
      } else {
        res.end(JSON.stringify({ accepted: true }));
      }
    });

    const requestedPort = Number.parseInt(process.env.PLAYWRIGHT_BUYER_LISTENER_PORT ?? '0', 10);
    server.listen(
      Number.isNaN(requestedPort) ? 0 : requestedPort,
      process.env.PLAYWRIGHT_BUYER_LISTENER_HOST ?? '0.0.0.0',
    );
    await once(server, 'listening');
    const address = server.address();
    if (!address || typeof address === 'string') throw new Error('buyer webhook listener did not expose a TCP port');
    buyerWebhookPort = address.port;
    buyerWebhookBase = (
      process.env.PLAYWRIGHT_BUYER_WEBHOOK_BASE ?? `http://host.docker.internal:${buyerWebhookPort}`
    ).replace(/\/$/, '');
    await use(undefined);
    await new Promise<void>((resolve, reject) => {
      server.close((error) => (error ? reject(error) : resolve()));
    });
  }, { scope: 'worker', auto: true }],
});

export { expect };
