import { once } from 'node:events';
import { createServer, type IncomingMessage } from 'node:http';
import { test as base, expect } from '@playwright/test';
import { StormLeadApiClient, runSeed, syntheticPhone, syntheticEmail } from '../helpers/api';
import { resolveWebhookSecret } from '../helpers/webhook';

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
  if (!raw) return {};
  try {
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return {};
  }
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

      await readRequestBody(req);
      const mode = req.headers['x-stormlead-mode'];
      res.writeHead(200, { 'content-type': 'application/json' });
      if (mode === 'ping') {
        res.end(JSON.stringify({ accept: true, bid_cents: 5000 }));
      } else {
        res.end(JSON.stringify({ accepted: true }));
      }
    });

    server.listen(9999, '127.0.0.1');
    await once(server, 'listening');
    await use(undefined);
    await new Promise<void>((resolve, reject) => {
      server.close((error) => (error ? reject(error) : resolve()));
    });
  }, { scope: 'worker', auto: true }],
});

export { expect };
