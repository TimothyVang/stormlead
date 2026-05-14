import { test, expect, clearBuyerWebhookEvents, getBuyerWebhookEvents } from './fixtures';
import { BUYER_PORTAL, FORM_RECEIVER, LANDING, OPERATOR_TOKEN, PING_POST, installOperatorToken } from './helpers/api';
import {
  type BuyerWebhookExpectation,
  createActiveBuyer,
  expectBuyerWebhookDelivery,
  submitLandingLead,
  submitWebhookLead,
  testZip,
} from './helpers/persona';
import { waitForLeadStatus, waitForTimelineEvent } from './helpers/wait';

type FailureCase = {
  name: string;
  zip: string;
  expectedWebhook: BuyerWebhookExpectation;
  setup: (zip: string) => Promise<{ webhookPath: string }>;
};

test.describe('Full human persona workflow suite', () => {
  test.beforeEach(() => {
    clearBuyerWebhookEvents();
  });

  test.beforeEach(async ({ page }) => {
    await installOperatorToken(page);
  });

  test('homeowner browser persona covers validation, duplicate, opt-out suppression, and mobile submit', async ({ page, request, phone, email, seed }) => {
    const base = {
      name: `Persona Homeowner ${seed}`,
      phone: phone(200),
      email: email('persona-homeowner'),
      address: `${seed % 900} Persona Homeowner Ln`,
      city: 'Austin',
      state: 'TX',
      zip: testZip('79', seed),
    };

    await test.step('required field validation blocks an incomplete human form', async () => {
      await page.goto(`${LANDING}/?utm_source=local_persona_suite&utm_campaign=local_validation_${seed}`);
      await page.locator('[data-testid="local-lead-form"] input[name="name"]').fill('');
      await expect(page.getByTestId('local-lead-submit')).toBeDisabled();
      await expect(page.getByTestId('local-lead-result')).toContainText('Ready to submit');
      await expect(page.locator('[data-testid="local-lead-form"] input[name="name"]')).toBeFocused();
    });

    let firstLeadId = '';
    await test.step('human submits once and the second same-contact submit is a duplicate', async () => {
      const first = await submitLandingLead(page, { ...base, campaign: `local_duplicate_${seed}` });
      expect(first.status).toBe('accepted');
      firstLeadId = first.leadId;
      expect(firstLeadId).toMatch(/^[0-9a-f-]{36}$/);

      const second = await submitLandingLead(
        page,
        { ...base, campaign: `local_duplicate_retry_${seed}` },
        { expectOk: false },
      );
      expect(second.status).toBe('error');
      expect(second.text).toContain('duplicate');
      expect(firstLeadId).toMatch(/^[0-9a-f-]{36}$/);
    });

    await test.step('opted-out contact is suppressed when they try to submit again', async () => {
      const suppressed = { ...base, phone: phone(201), email: email('persona-suppressed') };
      const optOut = await request.post(`${FORM_RECEIVER}/v1/privacy/opt-out`, {
        data: { phone: suppressed.phone, email: suppressed.email },
      });
      expect([200, 204]).toContain(optOut.status());

      const result = await submitLandingLead(page, { ...suppressed, campaign: `local_suppressed_${seed}` });
      expect(result.status).toBe('suppressed');
      expect(result.text).toContain('suppressed');
    });

    await test.step('mobile homeowner viewport can submit the same synthetic form', async () => {
      await page.setViewportSize({ width: 390, height: 844 });
      const mobile = await submitLandingLead(page, {
        ...base,
        phone: phone(202),
        email: email('persona-mobile'),
        campaign: `local_mobile_${seed}`,
      });
      expect(mobile.status).toBe('accepted');
      expect(mobile.leadId).toMatch(/^[0-9a-f-]{36}$/);
      await page.setViewportSize({ width: 1280, height: 720 });
    });
  });

  test('buyer portal persona logs in, views delivered lead, and requests a return', async ({ page, request, apiClient, phone, email, webhookSecret, seed }) => {
    const zip = testZip('80', seed);
    const { buyer } = await createActiveBuyer(apiClient, seed, 'portal', zip);
    const lead = await submitWebhookLead(request, webhookSecret, {
      scenario: `portal_${seed}`,
      phone: phone(220),
      email: email('persona-portal'),
      state: 'TX',
      zip,
      campaignId: `local_portal_${seed}`,
    });
    const leadId = lead.lead_id as string;
    await waitForLeadStatus(request, leadId, 'sold', { timeoutMs: 60_000 });

    await test.step('buyer logs into portal and reviews wallet', async () => {
      await page.goto(`${BUYER_PORTAL}/login`);
      await page.getByLabel('Buyer ID').fill(buyer.buyer_id);
      await page.getByLabel('Buyer API Key').fill(OPERATOR_TOKEN);
      await page.getByRole('button', { name: 'Open Wallet' }).click();
      await expect(page).toHaveURL(/\/buyer-portal\/wallet/);
      await expect(page.getByTestId('wallet-balance')).toBeVisible();
    });

    await test.step('buyer views the delivered lead in the portal lead list', async () => {
      await page.goto(`${BUYER_PORTAL}/buyer-portal/leads`);
      await expect(page.getByRole('table', { name: 'delivered leads' })).toContainText(leadId, { timeout: 30_000 });
    });

    await test.step('buyer requests a return through the portal', async () => {
      await page.goto(`${BUYER_PORTAL}/buyer-portal/review`);
      await page.getByLabel('Lead ID').fill(leadId);
      await page.getByLabel('Reason').selectOption('wrong_number');
      await page.getByLabel('Notes').fill('Synthetic buyer says the homeowner phone number was wrong.');
      await page.getByRole('button', { name: 'Submit Return Request' }).click();
      await expect(page.getByText('Submitted')).toBeVisible();
      await expect(page.locator('pre')).toContainText('return_request_id');
      await waitForTimelineEvent(request, leadId, 'lead.return_requested', { timeoutMs: 30_000 });
    });
  });

  test('operator browser persona reviews sold lead timeline and holds then approves it', async ({ page, request, apiClient, phone, email, webhookSecret, seed }) => {
    const zip = testZip('81', seed);
    await createActiveBuyer(apiClient, seed, 'operator', zip);
    const lead = await submitWebhookLead(request, webhookSecret, {
      scenario: `operator_${seed}`,
      phone: phone(230),
      email: email('persona-operator'),
      state: 'TX',
      zip,
      campaignId: `local_operator_${seed}`,
    });
    const leadId = lead.lead_id as string;
    await waitForLeadStatus(request, leadId, 'sold', { timeoutMs: 60_000 });

    await page.goto(`${PING_POST}/admin`);
    await expect(page.getByRole('heading', { name: 'StormLead Admin' })).toBeVisible();
    await page.locator('#timeline-lead-id').fill(leadId);
    await page.getByRole('button', { name: 'Load Timeline' }).click();
    await expect(page.locator('#timeline-summary')).toContainText('Current state: sold', { timeout: 30_000 });

    await page.locator('#review-notes').fill('Synthetic operator hold after reviewing timeline.');
    await page.getByRole('button', { name: 'Hold For Review' }).click();
    await expect(page.locator('#timeline-summary')).toContainText('Hold: yes', { timeout: 30_000 });
    await expect(page.locator('#timeline')).toContainText('admin.review.hold');

    await page.locator('#review-notes').fill('Synthetic operator approves after QA evidence is complete.');
    await page.getByRole('button', { name: 'Approve / Clear Hold' }).click();
    await expect(page.locator('#timeline-summary')).toContainText('Hold: no', { timeout: 30_000 });
    await expect(page.locator('#timeline')).toContainText('admin.review.approve');
  });

  test('buyer failure and safety paths stay unsold or refunded without public webhooks', async ({ page, request, apiClient, phone, email, webhookSecret, seed }) => {
    const cases: FailureCase[] = [
      { name: 'no-buyer', zip: testZip('82', seed), expectedWebhook: 'none', setup: async () => ({ webhookPath: '' }) },
      {
        name: 'insufficient-wallet',
        zip: testZip('83', seed),
        expectedWebhook: 'ping-only',
        setup: async (zip) => createActiveBuyer(apiClient, seed, 'insufficient-wallet', zip, { payload: { deposit_balance: 1 } }),
      },
      {
        name: 'cap-reached',
        zip: testZip('84', seed),
        expectedWebhook: 'none',
        setup: async (zip) => {
          const setup = await createActiveBuyer(apiClient, seed, 'cap-reached', zip, { payload: { daily_cap: 1 } });
          const primerLead = await submitWebhookLead(request, webhookSecret, {
            scenario: `cap-primer_${seed}`,
            phone: phone(238),
            email: email('persona-cap-primer'),
            state: 'TX',
            zip,
            campaignId: `local_cap_primer_${seed}`,
          });
          await waitForLeadStatus(request, primerLead.lead_id as string, 'sold', { timeoutMs: 60_000 });
          clearBuyerWebhookEvents();
          return setup;
        },
      },
      {
        name: 'reject-ping',
        zip: testZip('85', seed),
        expectedWebhook: 'ping-only',
        setup: async (zip) => createActiveBuyer(apiClient, seed, 'reject-ping', zip, { webhookPath: `/buyer-reject-ping-${seed}` }),
      },
      {
        name: 'fail-post',
        zip: testZip('86', seed),
        expectedWebhook: 'ping-and-post',
        setup: async (zip) => createActiveBuyer(apiClient, seed, 'fail-post', zip, { webhookPath: `/buyer-fail-post-${seed}` }),
      },
    ];

    for (const [index, scenario] of cases.entries()) {
      await test.step(`failure path: ${scenario.name}`, async () => {
        const setup = await scenario.setup(scenario.zip);
        const eventCountBeforeLead = getBuyerWebhookEvents().length;
        const lead = await submitWebhookLead(request, webhookSecret, {
          scenario: `${scenario.name}_${seed}`,
          phone: phone(240 + index),
          email: email(`persona-${scenario.name}`),
          state: scenario.name === 'no-buyer' ? 'AK' : 'TX',
          zip: scenario.name === 'no-buyer' ? '99501' : scenario.zip,
          campaignId: scenario.name === 'reject-ping' ? `local_ping_declined_${seed}` : `local_${scenario.name}_${seed}`,
        });
        const leadId = lead.lead_id as string;
        const timeline = await waitForTimelineEvent(request, leadId, 'lead.unsold', { timeoutMs: 90_000 });
        expect(timeline.events.some((event: any) => event.event_type === 'lead.unsold')).toBeTruthy();
        expectBuyerWebhookDelivery(getBuyerWebhookEvents().slice(eventCountBeforeLead), setup.webhookPath, scenario.expectedWebhook, leadId);
      });
    }

    await page.goto(`${PING_POST}/admin`);
    await expect(page.getByRole('heading', { name: 'StormLead Admin' })).toBeVisible();
  });
});
