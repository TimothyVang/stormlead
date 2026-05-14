import { test, expect, buyerWebhookUrl } from './fixtures';
import { BUYER_PORTAL, OPERATOR_TOKEN, type StormLeadApiClient } from './helpers/api';

function buyerPayload(seed: number) {
  const phoneSuffix = String(1_000_000 + (seed % 9_000_000)).slice(-7);
  return {
    name: `Playwright Wallet UI ${seed}`,
    company: `Playwright Wallet UI Co ${seed}`,
    contact_email: `buyer-wallet-ui-${seed}@example-stormlead-test.com`,
    contact_phone_e164: `+1512${phoneSuffix}`,
    webhook_url: buyerWebhookUrl('/webhook-sink'),
    webhook_secret: `playwright-wallet-ui-secret-${seed}`,
    bid_per_lead_t1_t2: 45.0,
    bid_per_lead_t3: 25.0,
    bid_per_call: 15.0,
    filter_expression: 'true',
    services: ['tree_removal'],
    target_zips: ['78710'],
    deposit_balance: 0,
    daily_cap: 10,
  };
}

async function issueBuyerApiKey(apiClient: StormLeadApiClient, buyerId: string): Promise<string> {
  const { status, body } = await apiClient.rotateBuyerApiKey(buyerId);
  expect(status).toBe(200);
  expect(body.api_key).toMatch(/^buyer_/);
  return body.api_key as string;
}

test.describe('Buyer Wallet UI', () => {
  test('adds synthetic wallet credit from buyer portal', async ({ page, apiClient, seed }) => {
    const { body: buyer } = await apiClient.createBuyer(buyerPayload(seed));
    await apiClient.updateBuyer(buyer.buyer_id, { status: 'active' });

    await page.goto(`${BUYER_PORTAL}/login`);
    await page.getByLabel('Buyer ID').fill(buyer.buyer_id);
    await page.getByLabel('Buyer API Key').fill(OPERATOR_TOKEN);
    await page.getByRole('button', { name: 'Open Wallet' }).click();

    await expect(page).toHaveURL(/\/buyer-portal\/wallet/);
    await expect(page.getByTestId('wallet-balance')).toContainText('$0.00');

    await page.getByTestId('wallet-deposit-amount').fill('12345');
    await page.locator('input[name="external_reference"]').fill(`playwright-wallet-ui-${seed}`);
    await page.getByTestId('wallet-deposit-submit').click();

    await expect(page.getByTestId('wallet-deposit-result')).toHaveAttribute('data-status', 'ok');
    await expect(page.getByTestId('wallet-balance')).toContainText('$123.45');

    const { body: wallet } = await apiClient.getWallet(buyer.buyer_id);
    expect(wallet.deposit_balance_cents).toBeGreaterThanOrEqual(12345);
  });

  test('rejects invalid synthetic wallet credit amounts in portal', async ({ page, apiClient, seed }) => {
    const { body: buyer } = await apiClient.createBuyer(buyerPayload(seed + 1));
    const buyerApiKey = await issueBuyerApiKey(apiClient, buyer.buyer_id);

    await page.goto(`${BUYER_PORTAL}/login`);
    await page.getByLabel('Buyer ID').fill(buyer.buyer_id);
    await page.getByLabel('Buyer API Key').fill(buyerApiKey);
    await page.getByRole('button', { name: 'Open Wallet' }).click();

    for (const invalidAmount of ['0', '-1', 'abc']) {
      await page.getByTestId('wallet-deposit-amount').fill(invalidAmount);
      await page.getByTestId('wallet-deposit-submit').click();
      await expect(page.getByTestId('wallet-deposit-result')).toHaveAttribute('data-status', 'error');
      await expect(page.getByTestId('wallet-deposit-result')).toContainText('positive integer');
    }

    const { body: wallet } = await apiClient.getWallet(buyer.buyer_id);
    expect(wallet.deposit_balance_cents).toBe(0);
  });

  test('rejects cross-buyer API key reuse in browser login', async ({ page, apiClient, seed }) => {
    const { body: buyerA } = await apiClient.createBuyer(buyerPayload(seed + 2));
    const { body: buyerB } = await apiClient.createBuyer(buyerPayload(seed + 3));
    const buyerAApiKey = await issueBuyerApiKey(apiClient, buyerA.buyer_id);
    const buyerBApiKey = await issueBuyerApiKey(apiClient, buyerB.buyer_id);

    await page.goto(`${BUYER_PORTAL}/login`);
    await page.getByLabel('Buyer ID').fill(buyerB.buyer_id);
    await page.getByLabel('Buyer API Key').fill(buyerAApiKey);
    await page.getByRole('button', { name: 'Open Wallet' }).click();

    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByText('Buyer ID or API key was rejected by StormLead.')).toBeVisible();
    const rejectedCookies = await page.context().cookies(BUYER_PORTAL);
    expect(rejectedCookies.find((cookie) => cookie.name === 'buyer_id')).toBeUndefined();
    expect(rejectedCookies.find((cookie) => cookie.name === 'buyer_api_key')).toBeUndefined();

    await page.getByLabel('Buyer ID').fill(buyerB.buyer_id);
    await page.getByLabel('Buyer API Key').fill(buyerBApiKey);
    await page.getByRole('button', { name: 'Open Wallet' }).click();

    await expect(page).toHaveURL(/\/buyer-portal\/wallet/);
    await expect(page.getByTestId('wallet-balance')).toBeVisible();
  });
});
