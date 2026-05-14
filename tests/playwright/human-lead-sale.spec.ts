import { test, expect, buyerWebhookUrl, clearBuyerWebhookEvents } from './fixtures';
import { installOperatorToken, LANDING, operatorHeaders, PING_POST } from './helpers/api';
import { expectBuyerWebhookPair } from './helpers/persona';
import { waitForLeadStatus } from './helpers/wait';

test.describe('Human lead acquisition and sale workflow', () => {
  test('human-like homeowner submit is acquired, sold, and delivered with ping/post privacy boundaries', async ({
    page,
    context,
    request,
    phone,
    email,
    seed,
  }) => {
    clearBuyerWebhookEvents();

    const zip = `78${String(seed % 1000).padStart(3, '0')}`;
    const buyerPath = `/buyer-human-sale-${seed}`;
    const buyerCompany = `Human Workflow Tree Pros ${seed}`;
    const homeowner = {
      name: `Human Workflow Homeowner ${seed}`,
      phone: phone(90),
      email: email('human-sale'),
      address: `${100 + (seed % 800)} Human Workflow Oak Ln`,
      city: 'Austin',
      state: 'TX',
      zip,
      consent: 'I agree to be contacted regarding storm damage repair services. This is synthetic local QA data.',
    };

    await test.step('buyer operator creates, activates, and funds a synthetic buyer in the browser UI', async () => {
      await installOperatorToken(page);
      await page.goto(`${PING_POST}/admin`);
      await expect(page.getByRole('heading', { name: 'StormLead Admin' })).toBeVisible();

      await page.locator('#buyer-form input[name="name"]').fill(`Human Workflow Buyer ${seed}`);
      await page.locator('#buyer-form input[name="company"]').fill(buyerCompany);
      await page.locator('#buyer-form input[name="contact_email"]').fill(`buyer-human-sale-${seed}@example-stormlead-test.com`);
      await page.locator('#buyer-form input[name="contact_phone_e164"]').fill(`+1512${Date.now().toString().slice(-7)}`);
      await page.locator('#buyer-form input[name="webhook_url"]').fill(buyerWebhookUrl(buyerPath));
      await page.locator('#buyer-form input[name="webhook_secret"]').fill(`human-workflow-secret-${seed}`);
      await page.locator('#buyer-form input[name="bid_per_lead_t1_t2"]').fill('250.00');
      await page.locator('#buyer-form input[name="bid_per_lead_t3"]').fill('250.00');
      await page.locator('#buyer-form input[name="filter_expression"]').fill("lead.state == 'TX'");
      await page.locator('#buyer-form input[name="target_zips"]').fill(zip);
      await page.locator('#buyer-form input[name="deposit_balance"]').fill('0.00');

      const createResponse = page.waitForResponse(
        (response) => response.url().includes('/v1/buyers') && response.request().method() === 'POST',
      );
      await page.getByRole('button', { name: 'Create Real Buyer' }).click();
      expect([200, 201]).toContain((await createResponse).status());
      await expect(page.locator('#selected-buyer-id')).not.toHaveValue('', { timeout: 30_000 });

      await page.locator('#deposit-form input[name="amount_cents"]').fill('500000');
      await page.locator('#deposit-form input[name="external_reference"]').fill(`human-workflow-${seed}`);
      const depositResponse = page.waitForResponse(
        (response) => response.url().includes('/deposits') && response.request().method() === 'POST',
      );
      await page.getByRole('button', { name: 'Add Real Deposit' }).click();
      expect((await depositResponse).status()).toBe(200);

      await page.locator('#buyer-update-form input[name="target_zips"]').fill(zip);
      const updateResponse = page.waitForResponse(
        (response) => response.url().includes('/v1/buyers/') && response.request().method() === 'PATCH',
      );
      await page.getByRole('button', { name: 'Update Real Buyer' }).click();
      expect((await updateResponse).status()).toBe(200);
      await expect(page.getByRole('table', { name: 'buyers' })).toContainText(buyerCompany, { timeout: 60_000 });
    });

    let leadId = '';
    await test.step('homeowner fills the local landing page like a real lead', async () => {
      await context.grantPermissions(['geolocation'], { origin: LANDING });
      await context.setGeolocation({ latitude: 30.2672, longitude: -97.7431, accuracy: 25 });
      await page.goto(`${LANDING}/?utm_source=local_human_workflow&utm_campaign=local_lead_sale_${seed}`);
      await expect(page.getByTestId('local-lead-form')).toBeVisible();

      await page.locator('[data-testid="local-lead-form"] input[name="name"]').fill(homeowner.name);
      await page.locator('[data-testid="local-lead-form"] input[name="phone"]').fill(homeowner.phone);
      await page.locator('[data-testid="local-lead-form"] input[name="email"]').fill(homeowner.email);
      await page.locator('[data-testid="local-lead-form"] select[name="requested_service"]').selectOption('tree_removal');
      await page.locator('[data-testid="local-lead-form"] input[name="address_line1"]').fill(homeowner.address);
      await page.locator('[data-testid="local-lead-form"] input[name="city"]').fill(homeowner.city);
      await page.locator('[data-testid="local-lead-form"] input[name="state"]').fill(homeowner.state);
      await page.locator('[data-testid="local-lead-form"] input[name="zip"]').fill(homeowner.zip);
      await page.getByTestId('capture-location').click();
      await expect(page.getByTestId('location-status')).toContainText('GPS captured');
      await page.getByTestId('damage-photos').setInputFiles([
        {
          name: 'wide-human-workflow.jpg',
          mimeType: 'image/jpeg',
          buffer: Buffer.from('ffd8ffe000104a464946000101', 'hex'),
        },
        {
          name: 'close-human-workflow.png',
          mimeType: 'image/png',
          buffer: Buffer.from('89504e470d0a1a0a0000000d49484452', 'hex'),
        },
      ]);
      await expect(page.getByTestId('photo-status')).toContainText('2 of 2');
      await page.locator('[data-testid="local-lead-form"] textarea[name="consent_text"]').fill(homeowner.consent);
      await page.getByTestId('consent-ack').check();
      await expect(page.getByTestId('local-lead-submit')).toBeEnabled();
      await page.getByTestId('local-lead-submit').click();

      const result = page.getByTestId('local-lead-result');
      await expect(result).toHaveClass(/ok/, { timeout: 30_000 });
      await expect(result).toContainText('accepted');
      leadId = (await result.getAttribute('data-lead-id')) ?? '';
      expect(leadId).toMatch(/^[0-9a-f-]{36}$/);
    });

    await test.step('lead is qualified, auctioned, sold, and visible in the lead timeline', async () => {
      const timeline = await waitForLeadStatus(request, leadId, 'sold', { timeoutMs: 60_000 });
      expect(timeline.current_state).toBe('sold');
      expect(timeline.lead).toBeDefined();
      expect(timeline.events.some((event: any) => event.event_type === 'lead.sold')).toBeTruthy();
    });

    await test.step('buyer receives privacy-safe ping before full sold lead post', async () => {
      const { ping, post } = await expectBuyerWebhookPair(buyerPath);
      expect(ping.body).toMatchObject({ state: homeowner.state, city: homeowner.city, zip: homeowner.zip });
      expect(ping.body).not.toHaveProperty('name');
      expect(ping.body).not.toHaveProperty('phone');
      expect(ping.body).not.toHaveProperty('email');
      expect(ping.body).not.toHaveProperty('address');

      expect(post.body).toMatchObject({
        lead_id: leadId,
        name: homeowner.name,
        phone: homeowner.phone,
        email: homeowner.email,
        address: {
          line1: homeowner.address,
          city: homeowner.city,
          state: homeowner.state,
          zip: homeowner.zip,
        },
        consent: {
          text: homeowner.consent,
        },
      });
    });

    await test.step('paid launch remains locked while local synthetic flow is allowed', async () => {
      const readiness = await request.get(`${PING_POST}/v1/admin/launch-readiness`, {
        headers: operatorHeaders(),
      });
      expect(readiness.status()).toBe(200);
      const body = await readiness.json();
      expect(typeof body.local_simulation_ready).toBe('boolean');
      expect(body).toHaveProperty('ready_for_paid_launch', false);
    });
  });
});
