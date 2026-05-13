import { expect, test, buyerWebhookUrl } from './fixtures';
import { FORM_RECEIVER } from './helpers/api';
import { buildEnvelope, buildSignedHeaders } from './helpers/webhook';
import { waitForLeadStatus, waitForTimelineEvent } from './helpers/wait';

function buyerPayload(seed: number, tag: string, zip: string, depositBalance = 1000) {
  return {
    name: `Autopilot ${tag} ${seed}`,
    company: `Autopilot ${tag} Co ${seed}`,
    contact_email: `autopilot-${tag}-${seed}@example-stormlead-test.com`,
    contact_phone_e164: `+1512${String(300 + (seed % 600)).padStart(3, '0')}${String(1000 + (seed % 9000)).padStart(4, '0')}`,
    webhook_url: buyerWebhookUrl(`/buyer-autopilot-${tag}-${seed}`),
    webhook_secret: `autopilot-${tag}-${seed}-secret!!`,
    bid_per_lead_t1_t2: 50.0,
    bid_per_lead_t3: 200.0,
    bid_per_call: 100.0,
    filter_expression: "lead.state == 'TX'",
    services: ['tree_removal'],
    target_zips: [zip],
    deposit_balance: depositBalance,
    daily_cap: 100,
  };
}

async function createAutopilotReadyBuyer(apiClient: any, seed: number, tag: string, zip: string) {
  const created = await apiClient.createBuyer(buyerPayload(seed, tag, zip));
  expect([200, 201]).toContain(created.status);
  const updated = await apiClient.updateBuyer(created.body.buyer_id, {
    status: 'active',
    sales_stage: 'funded',
    notes: 'Terms accepted for local paid-pilot autopilot proof.',
  });
  expect(updated.status).toBe(200);
  expect(updated.body.onboarding_readiness.autopilot_ready).toBe(true);
  return updated.body;
}

async function submitSyntheticLead(request: any, webhookSecret: string, tag: string, zip: string, phone: string, email: string) {
  const { envelope, webhookId } = buildEnvelope({
    scenario: `paid_pilot_autopilot_${tag}`,
    phone,
    email,
    state: 'TX',
    zip,
  });
  const { headers, bodyStr } = buildSignedHeaders(webhookId, envelope, webhookSecret);
  const res = await request.post(`${FORM_RECEIVER}/webhooks/formbricks`, { headers, data: bodyStr });
  expect(res.status()).toBe(200);
  const body = await res.json();
  expect(body.lead_id).toBeTruthy();
  return body.lead_id as string;
}

test.describe('Paid Pilot Autopilot', () => {
  test('reports straight-through KPIs after an eligible synthetic lead auto-sells', async ({ request, apiClient, seed, phone, email, webhookSecret }) => {
    const zip = `79${String(seed % 1000).padStart(3, '0')}`;
    await createAutopilotReadyBuyer(apiClient, seed, 'stp', zip);
    const leadId = await submitSyntheticLead(request, webhookSecret, 'stp', zip, phone(210), email('paid-pilot-stp'));

    await waitForLeadStatus(request, leadId, 'sold', { timeoutMs: 45_000 });
    const kpis = await apiClient.getAutopilotKPIs();

    expect(kpis.status).toBe(200);
    expect(kpis.body.policy_version).toBe('paid-pilot-autopilot-v1');
    expect(kpis.body.eligible_workflows).toBeGreaterThanOrEqual(1);
    expect(kpis.body.automated_successes).toBeGreaterThanOrEqual(1);
    expect(kpis.body.metrics.some((metric: any) => metric.key === 'straight_through_rate')).toBe(true);
    expect(kpis.body.buyer_onboarding.autopilot_ready_buyers).toBeGreaterThanOrEqual(1);
  });

  test('keeps no-buyer coverage and low-wallet states in the exception queue', async ({ request, apiClient, seed, phone, email, webhookSecret }) => {
    const lowWalletZip = `76${String(seed % 1000).padStart(3, '0')}`;
    const lowWallet = await apiClient.createBuyer(buyerPayload(seed + 1, 'low-wallet', lowWalletZip, 0));
    expect([200, 201]).toContain(lowWallet.status);
    const lowWalletUpdated = await apiClient.updateBuyer(lowWallet.body.buyer_id, { status: 'active', sales_stage: 'funded', notes: 'Terms accepted but wallet empty.' });
    expect(lowWalletUpdated.status).toBe(200);
    expect(lowWalletUpdated.body.onboarding_readiness.wallet_ready).toBe(false);
    expect(lowWalletUpdated.body.onboarding_readiness.auto_pause_recommended).toBe(true);

    const { envelope, webhookId } = buildEnvelope({
      scenario: 'paid_pilot_autopilot_no_buyer',
      phone: phone(220),
      email: email('paid-pilot-no-buyer'),
      state: 'AK',
      zip: '99501',
    });
    const { headers, bodyStr } = buildSignedHeaders(webhookId, envelope, webhookSecret);
    const res = await request.post(`${FORM_RECEIVER}/webhooks/formbricks`, { headers, data: bodyStr });
    expect(res.status()).toBe(200);
    const { lead_id: leadId } = await res.json();
    await waitForTimelineEvent(request, leadId, 'lead.unsold', { timeoutMs: 45_000 });

    const noBuyerQueue = await apiClient.getAutopilotExceptions({ kind: 'no_buyer_coverage', lead_id: leadId, limit: 100 });
    expect(noBuyerQueue.status).toBe(200);
    expect(noBuyerQueue.body.exceptions.some((item: any) => item.lead_id === leadId && item.reason === 'no_eligible_buyers')).toBe(true);

    const walletQueue = await apiClient.getAutopilotExceptions({ kind: 'buyer_wallet_low', buyer_id: lowWallet.body.buyer_id, limit: 100 });
    expect(walletQueue.status).toBe(200);
    expect(walletQueue.body.exceptions.some((item: any) => item.buyer_id === lowWallet.body.buyer_id && item.reason === 'wallet_below_threshold')).toBe(true);
  });

  test('auto-decides safe return policy reasons and removes them from manual return exceptions', async ({ request, apiClient, seed, phone, email, webhookSecret }) => {
    const zip = `75${String(seed % 1000).padStart(3, '0')}`;
    const buyer = await createAutopilotReadyBuyer(apiClient, seed + 2, 'auto-return', zip);
    const beforeWallet = await apiClient.getWallet(buyer.buyer_id);
    expect(beforeWallet.status).toBe(200);
    const leadId = await submitSyntheticLead(request, webhookSecret, 'auto-return', zip, phone(230), email('paid-pilot-auto-return'));
    await waitForLeadStatus(request, leadId, 'sold', { timeoutMs: 45_000 });

    const returnResult = await apiClient.requestReturn(leadId, 'outside_service_area', 'Policy-safe local proof return.');
    expect(returnResult.status).toBe(200);
    expect(returnResult.body.status).toBe('approved');
    expect(returnResult.body.auto_decided).toBe(true);
    expect(returnResult.body.credited_cents).toBeGreaterThan(0);
    expect(returnResult.body.wallet.deposit_balance_cents).toBeGreaterThan(beforeWallet.body.deposit_balance_cents - returnResult.body.credited_cents);
    await waitForTimelineEvent(request, leadId, 'lead.return_approved', { timeoutMs: 10_000 });

    const queue = await apiClient.getAutopilotExceptions({ kind: 'return_pending', lead_id: leadId, limit: 100 });
    expect(queue.status).toBe(200);
    expect(queue.body.exceptions.some((item: any) => item.return_request_id === returnResult.body.return_request_id)).toBe(false);

    const kpis = await apiClient.getAutopilotKPIs();
    expect(kpis.body.metrics.find((metric: any) => metric.key === 'refund_auto_decision_rate').numerator).toBeGreaterThanOrEqual(1);
  });
});
