import { test, expect } from './fixtures';

// Minimal valid buyer payload matching BuyerCreateRequest in ping-post/api.py
function buyerPayload(seed: number, tag: string) {
  return {
    name: `Playwright ${tag} ${seed}`,
    company: `Playwright ${tag} Co ${seed}`,
    contact_email: `buyer-${tag}-${seed}@example-stormlead-test.com`,
    contact_phone_e164: `+1512${String(500 + (seed % 400)).padStart(3, '0')}${String(1000 + (seed % 9000)).padStart(4, '0')}`,
    webhook_url: 'http://localhost:9999/webhook-sink',
    webhook_secret: `playwright-secret-${seed}-padded!!`,
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

test.describe('Buyer Lifecycle', () => {
  test('create buyer → status pending_verification', async ({ apiClient, seed }) => {
    const { status, body } = await apiClient.createBuyer(buyerPayload(seed, 'create'));
    expect([200, 201]).toContain(status);
    expect(body.status).toBe('pending_verification');
    expect(body.buyer_id).toBeTruthy();
  });

  test('activate buyer → status active', async ({ apiClient, seed }) => {
    const { body: created } = await apiClient.createBuyer(buyerPayload(seed + 1, 'activate'));
    const { status, body } = await apiClient.updateBuyer(created.buyer_id, { status: 'active' });
    expect(status).toBe(200);
    expect(body.status).toBe('active');
  });

  test('add deposit → deposit_balance_cents increases', async ({ apiClient, seed }) => {
    const { body: buyer } = await apiClient.createBuyer(buyerPayload(seed + 2, 'wallet'));
    await apiClient.updateBuyer(buyer.buyer_id, { status: 'active' });
    const { status, body: wallet } = await apiClient.addDeposit(buyer.buyer_id, 75000); // $750 in cents
    expect(status).toBe(200);
    expect(wallet.deposit_balance_cents).toBeGreaterThanOrEqual(75000);
  });

  test('list buyers → returns array with at least one buyer', async ({ apiClient }) => {
    const { status, body } = await apiClient.listBuyers();
    expect(status).toBe(200);
    expect(Array.isArray(body.buyers)).toBe(true);
    expect(body.buyers.length).toBeGreaterThanOrEqual(1);
  });

  test('KPI endpoint → returns numeric sold_leads and active_buyers', async ({ apiClient }) => {
    const { status, body } = await apiClient.getKPIs();
    expect(status).toBe(200);
    expect(typeof body.sold_leads).toBe('number');
    expect(typeof body.active_buyers).toBe('number');
    expect(typeof body.prepaid_cash_cents).toBe('number');
  });

  test('workflow KPIs → returns valid response', async ({ apiClient }) => {
    const { status, body } = await apiClient.getWorkflowKPIs();
    expect(status).toBe(200);
    expect(body).toBeDefined();
  });
});
