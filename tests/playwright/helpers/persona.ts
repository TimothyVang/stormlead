import { expect, type APIRequestContext, type Page } from '@playwright/test';
import { buyerWebhookUrl, getBuyerWebhookEvents, type BuyerWebhookEvent } from '../fixtures';
import { FORM_RECEIVER, LANDING, type StormLeadApiClient } from './api';
import { buildEnvelope, buildSignedHeaders } from './webhook';

interface BuyerOverrides {
  webhookPath?: string;
  payload?: Record<string, unknown>;
}

interface LandingLead {
  name: string;
  phone: string;
  email: string;
  address: string;
  city: string;
  state: string;
  zip: string;
  campaign: string;
  source?: string;
}

interface WebhookLead {
  scenario: string;
  phone: string;
  email: string;
  state: string;
  zip: string;
  campaignId?: string;
}

interface SubmitLandingLeadOptions {
  expectOk?: boolean;
}

export type BuyerWebhookExpectation = 'none' | 'ping-only' | 'ping-and-post';

export function testZip(prefix: string, seed: number): string {
  return `${prefix}${String(seed % 1000).padStart(3, '0')}`;
}

export function buyerWebhookEvents(path: string, mode?: string): BuyerWebhookEvent[] {
  return getBuyerWebhookEvents().filter((event) => event.url === path && (!mode || event.mode === mode));
}

export async function expectBuyerWebhookPair(path: string) {
  await expect.poll(
    () => {
      const events = buyerWebhookEvents(path);
      const pingIndex = events.findIndex((event) => event.mode === 'ping');
      const postIndex = events.findIndex((event) => event.mode === 'post');
      return pingIndex >= 0 && postIndex > pingIndex;
    },
    { timeout: 45_000, message: `expected buyer ping before post at ${path}` },
  ).toBeTruthy();

  const events = buyerWebhookEvents(path);
  const pingIndex = events.findIndex((event) => event.mode === 'ping');
  const postIndex = events.findIndex((event) => event.mode === 'post');
  return { ping: events[pingIndex], post: events[postIndex] };
}

export function expectBuyerWebhookDelivery(events: BuyerWebhookEvent[], path: string, expected: BuyerWebhookExpectation, leadId?: string): void {
  const leadEvents = leadId ? events.filter((event) => event.body.lead_id === leadId) : events;
  if (expected === 'none') {
    expect(path ? leadEvents.filter((event) => event.url === path) : leadEvents).toHaveLength(0);
    return;
  }

  const pathEvents = leadEvents.filter((event) => event.url === path);
  expect(pathEvents.some((event) => event.mode === 'ping')).toBeTruthy();
  if (expected === 'ping-only') {
    expect(pathEvents.filter((event) => event.mode === 'post')).toHaveLength(0);
  } else {
    expect(pathEvents.some((event) => event.mode === 'post')).toBeTruthy();
  }
}

export async function createActiveBuyer(
  apiClient: StormLeadApiClient,
  seed: number,
  tag: string,
  zip: string,
  overrides: BuyerOverrides = {},
) {
  const webhookPath = overrides.webhookPath ?? `/buyer-persona-${tag}-${seed}`;
  const created = await apiClient.createBuyer({
    name: `Persona Buyer ${tag} ${seed}`,
    company: `Persona ${tag} Pros ${seed}`,
    contact_email: `buyer-persona-${tag}-${seed}@example-stormlead-test.com`,
    contact_phone_e164: `+1512${Date.now().toString().slice(-7)}`,
    webhook_url: buyerWebhookUrl(webhookPath),
    webhook_secret: `persona-secret-${tag}-${seed}`,
    bid_per_lead_t1_t2: 250.0,
    bid_per_lead_t3: 250.0,
    bid_per_call: 100.0,
    filter_expression: "lead.state == 'TX'",
    services: ['tree_removal'],
    target_zips: [zip],
    deposit_balance: 1000,
    daily_cap: 100,
    ...overrides.payload,
  });
  expect([200, 201]).toContain(created.status);

  const updated = await apiClient.updateBuyer(created.body.buyer_id, { status: 'active', sales_stage: 'funded' });
  expect(updated.status).toBe(200);
  return { buyer: updated.body, webhookPath };
}

export async function submitLandingLead(
  page: Page,
  lead: LandingLead,
  options: SubmitLandingLeadOptions = {},
) {
  await page.context().grantPermissions(['geolocation'], { origin: LANDING });
  await page.context().setGeolocation({ latitude: 30.2672, longitude: -97.7431, accuracy: 25 });
  await page.goto(`${LANDING}/?utm_source=${lead.source ?? 'local_persona_suite'}&utm_campaign=${lead.campaign}`);
  await expect(page.getByTestId('local-lead-form')).toBeVisible();
  await page.locator('[data-testid="local-lead-form"] input[name="name"]').fill(lead.name);
  await page.locator('[data-testid="local-lead-form"] input[name="phone"]').fill(lead.phone);
  await page.locator('[data-testid="local-lead-form"] input[name="email"]').fill(lead.email);
  await page.locator('[data-testid="local-lead-form"] select[name="requested_service"]').selectOption('tree_removal');
  await page.locator('[data-testid="local-lead-form"] input[name="address_line1"]').fill(lead.address);
  await page.locator('[data-testid="local-lead-form"] input[name="city"]').fill(lead.city);
  await page.locator('[data-testid="local-lead-form"] input[name="state"]').fill(lead.state);
  await page.locator('[data-testid="local-lead-form"] input[name="zip"]').fill(lead.zip);
  await page.locator('[data-testid="local-lead-form"] textarea[name="consent_text"]').fill('I agree to be contacted regarding storm damage repair services. This is synthetic local QA data.');
  await page.getByTestId('capture-location').click();
  await expect(page.getByTestId('location-status')).toContainText('GPS captured');
  await page.getByTestId('damage-photos').setInputFiles([
    {
      name: 'wide-persona-proof.jpg',
      mimeType: 'image/jpeg',
      buffer: Buffer.from('ffd8ffe000104a464946000101', 'hex'),
    },
    {
      name: 'close-persona-proof.png',
      mimeType: 'image/png',
      buffer: Buffer.from('89504e470d0a1a0a0000000d49484452', 'hex'),
    },
  ]);
  await expect(page.getByTestId('photo-status')).toContainText('2 of 2');
  await page.getByTestId('consent-ack').check();
  await expect(page.getByTestId('local-lead-submit')).toBeEnabled();
  await page.getByTestId('local-lead-submit').click();

  const result = page.getByTestId('local-lead-result');
  if (options.expectOk ?? true) {
    await expect(result).toHaveClass(/ok/, { timeout: 30_000 });
  } else {
    await expect(result).toBeVisible({ timeout: 30_000 });
  }
  return {
    leadId: (await result.getAttribute('data-lead-id')) ?? '',
    status: (await result.getAttribute('data-status')) ?? '',
    text: (await result.textContent()) ?? '',
  };
}

export async function submitWebhookLead(request: APIRequestContext, webhookSecret: string, lead: WebhookLead) {
  const { envelope, webhookId } = buildEnvelope({
    scenario: lead.scenario,
    phone: lead.phone,
    email: lead.email,
    state: lead.state,
    zip: lead.zip,
    campaignId: lead.campaignId ?? `local_${lead.scenario}`,
  });
  const { headers, bodyStr } = buildSignedHeaders(webhookId, envelope, webhookSecret);
  const response = await request.post(`${FORM_RECEIVER}/webhooks/formbricks`, { headers, data: bodyStr });
  expect(response.status()).toBe(200);
  return response.json();
}
