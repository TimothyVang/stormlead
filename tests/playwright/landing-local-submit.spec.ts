import { test, expect, buyerWebhookUrl } from './fixtures';
import { LANDING, PING_POST, operatorHeaders } from './helpers/api';
import { waitForLeadStatus, waitForTimelineEvent } from './helpers/wait';

test.describe('Landing Local Submit UI', () => {
  test('submits synthetic homeowner lead through the browser and sells to a funded buyer', async ({
    page,
    context,
    request,
    apiClient,
    phone,
    email,
    seed,
  }) => {
    const zip = `78${String(seed % 1000).padStart(3, '0')}`;
    const buyer = await apiClient.createBuyer({
      name: `Playwright Landing UI ${seed}`,
      company: `Playwright Landing UI Co ${seed}`,
      contact_email: `buyer-landing-ui-${seed}@example-stormlead-test.com`,
      contact_phone_e164: `+1512${Date.now().toString().slice(-7)}`,
      webhook_url: buyerWebhookUrl('/buyer-landing-ui'),
      webhook_secret: `playwright-landing-ui-secret-${seed}`,
      bid_per_lead_t1_t2: 250.0,
      bid_per_lead_t3: 250.0,
      bid_per_call: 100.0,
      filter_expression: 'true',
      services: ['tree_removal'],
      target_zips: [zip],
      deposit_balance: 5000,
      daily_cap: 100,
    });
    expect([200, 201]).toContain(buyer.status);
    const updatedBuyer = await apiClient.updateBuyer(buyer.body.buyer_id, {
      status: 'active',
      sales_stage: 'funded',
    });
    expect(updatedBuyer.status).toBe(200);

    await context.grantPermissions(['geolocation'], { origin: LANDING });
    await context.setGeolocation({ latitude: 30.4515, longitude: -91.1871, accuracy: 25 });
    await page.goto(`${LANDING}/?utm_source=playwright_landing_ui&utm_campaign=local_landing_ui_${seed}&gclid=test-gclid-${seed}`);
    await expect(page.getByTestId('local-lead-form')).toBeVisible();

    await page.locator('[data-testid="local-lead-form"] input[name="name"]').fill('Playwright Local Homeowner');
    await page.locator('[data-testid="local-lead-form"] input[name="phone"]').fill(phone(70));
    await page.locator('[data-testid="local-lead-form"] input[name="email"]').fill(email('landing-ui'));
    await page.locator('[data-testid="local-lead-form"] input[name="address_line1"]').fill('777 Browser Proof Ln');
    await page.locator('[data-testid="local-lead-form"] input[name="city"]').fill('Austin');
    await page.locator('[data-testid="local-lead-form"] input[name="state"]').fill('TX');
    await page.locator('[data-testid="local-lead-form"] input[name="zip"]').fill(zip);
    await page.getByTestId('capture-location').click();
    await expect(page.getByTestId('location-status')).toContainText('GPS captured');
    const jpegBytes = Buffer.from('ffd8ffe000104a464946000101', 'hex');
    const pngBytes = Buffer.from('89504e470d0a1a0a0000000d49484452', 'hex');
    await page.getByTestId('damage-photos').setInputFiles([
      { name: 'wide-damage.jpg', mimeType: 'image/jpeg', buffer: jpegBytes },
      { name: 'close-damage.png', mimeType: 'image/png', buffer: pngBytes },
    ]);
    await expect(page.getByTestId('photo-status')).toContainText('2 of 2');
    await page
      .locator('[data-testid="local-lead-form"] textarea[name="consent_text"]')
      .fill('I agree to be contacted regarding storm damage repair services. This is synthetic local QA data.');
    await page.getByTestId('consent-ack').check();
    await expect(page.getByTestId('local-lead-submit')).toBeEnabled();
    await page.getByTestId('local-lead-submit').click();

    const result = page.getByTestId('local-lead-result');
    await expect(result).toHaveClass(/ok/, { timeout: 30_000 });
    await expect(result).toContainText('accepted');
    const leadId = await result.getAttribute('data-lead-id');
    expect(leadId).toMatch(/^[0-9a-f-]{36}$/);

    await waitForTimelineEvent(request, leadId!, 'lead.qualified', { timeoutMs: 90_000 });
    const auction = await request.post(`${PING_POST}/v1/auction`, {
      headers: operatorHeaders(),
      data: { lead_id: leadId },
    });
    expect(auction.status()).toBe(200);
    const timeline = await waitForLeadStatus(request, leadId!, 'sold', { timeoutMs: 60_000 });
    expect(timeline.current_state).toBe('sold');
  });
});
