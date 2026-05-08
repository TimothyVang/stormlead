import { test, expect } from './fixtures';
import { LANDING } from './helpers/api';
import { waitForLeadStatus } from './helpers/wait';

test.describe('Landing Local Submit UI', () => {
  test('submits synthetic homeowner lead through the browser and sells to a funded buyer', async ({
    page,
    request,
    apiClient,
    phone,
    email,
    seed,
  }) => {
    const zip = '78761';
    const buyer = await apiClient.createBuyer({
      name: `Playwright Landing UI ${seed}`,
      company: `Playwright Landing UI Co ${seed}`,
      contact_email: `buyer-landing-ui-${seed}@example-stormlead-test.com`,
      contact_phone_e164: `+1512${Date.now().toString().slice(-7)}`,
      webhook_url: 'http://host.docker.internal:9999/buyer-landing-ui',
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
    await apiClient.updateBuyer(buyer.body.buyer_id, { status: 'active' });

    await page.goto(`${LANDING}/?utm_source=playwright_landing_ui&utm_campaign=local_landing_ui_${seed}`);
    await expect(page.getByTestId('local-lead-form')).toBeVisible();

    await page.locator('[data-testid="local-lead-form"] input[name="name"]').fill('Playwright Local Homeowner');
    await page.locator('[data-testid="local-lead-form"] input[name="phone"]').fill(phone(70));
    await page.locator('[data-testid="local-lead-form"] input[name="email"]').fill(email('landing-ui'));
    await page.locator('[data-testid="local-lead-form"] input[name="address_line1"]').fill('777 Browser Proof Ln');
    await page.locator('[data-testid="local-lead-form"] input[name="city"]').fill('Austin');
    await page.locator('[data-testid="local-lead-form"] input[name="state"]').fill('TX');
    await page.locator('[data-testid="local-lead-form"] input[name="zip"]').fill(zip);
    await page.getByTestId('local-lead-submit').click();

    const result = page.getByTestId('local-lead-result');
    await expect(result).toHaveClass(/ok/, { timeout: 30_000 });
    await expect(result).toContainText('accepted');
    const leadId = await result.getAttribute('data-lead-id');
    expect(leadId).toMatch(/^[0-9a-f-]{36}$/);

    const timeline = await waitForLeadStatus(request, leadId!, 'sold', { timeoutMs: 45_000 });
    expect(timeline.current_state).toBe('sold');
  });
});
