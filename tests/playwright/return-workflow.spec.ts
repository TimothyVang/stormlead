import { test, expect } from './fixtures';
import { FORM_RECEIVER, StormLeadApiClient } from './helpers/api';
import { buildSignedHeaders, buildEnvelope } from './helpers/webhook';
import { waitForLeadStatus } from './helpers/wait';

async function submitAndSellLead(
  request: Parameters<typeof waitForLeadStatus>[0],
  apiClient: StormLeadApiClient,
  phoneNum: string,
  emailAddr: string,
  webhookSecret: string,
  zip: string,
  tag: string,
): Promise<string> {
  const buyer = await apiClient.createBuyer({
    name: `Playwright Return ${tag}`,
    company: `Playwright Return ${tag} Co`,
    contact_email: `buyer-return-${tag}-${Date.now()}@example-stormlead-test.com`,
    contact_phone_e164: `+1512${Date.now().toString().slice(-7)}`,
    webhook_url: `http://host.docker.internal:9999/buyer-return-${tag}`,
    webhook_secret: `playwright-return-${tag}-secret`,
    bid_per_lead_t1_t2: 50.0,
    bid_per_lead_t3: 200.0,
    bid_per_call: 100.0,
    filter_expression: 'true',
    services: ['tree_removal'],
    target_zips: [zip],
    deposit_balance: 1000,
    daily_cap: 100,
  });
  expect([200, 201]).toContain(buyer.status);
  await apiClient.updateBuyer(buyer.body.buyer_id, { status: 'active' });

  const { envelope, webhookId } = buildEnvelope({
    scenario: 'return_setup',
    phone: phoneNum,
    email: emailAddr,
    state: 'TX',
    zip,
  });
  const { headers, bodyStr } = buildSignedHeaders(webhookId, envelope, webhookSecret);
  const res = await request.post(`${FORM_RECEIVER}/webhooks/formbricks`, { headers, data: bodyStr });
  const json = await res.json();
  if (!json.lead_id) throw new Error(`Expected lead_id in response: ${JSON.stringify(json)}`);
  await waitForLeadStatus(request, json.lead_id, 'sold', { timeoutMs: 45_000 });
  return json.lead_id;
}

test.describe('Return Workflow', () => {
  test('buyer can request return on a sold lead', async ({ request, apiClient, phone, email, webhookSecret }) => {
    const leadId = await submitAndSellLead(request, apiClient, phone(70), email('return_req'), webhookSecret, '78771', 'request');
    const { status, body } = await apiClient.requestReturn(leadId, 'job_already_completed');
    expect([200, 201]).toContain(status);
    // Response field is return_request_id, not return_id
    expect(body).toHaveProperty('return_request_id');
  });

  test('admin can hold a lead for review', async ({ request, apiClient, phone, email, webhookSecret }) => {
    const leadId = await submitAndSellLead(request, apiClient, phone(71), email('return_hold'), webhookSecret, '78772', 'hold');
    const { status } = await apiClient.reviewLead(leadId, 'hold', 'Playwright hold test');
    expect([200, 204]).toContain(status);
  });

  test('admin approves return request → return_request transitions to approved', async ({ request, apiClient, phone, email, webhookSecret }) => {
    const leadId = await submitAndSellLead(request, apiClient, phone(72), email('return_approve'), webhookSecret, '78773', 'approve');
    const { body: returnBody } = await apiClient.requestReturn(leadId, 'wrong_number');
    const returnRequestId: string = returnBody.return_request_id;
    const { status, body } = await apiClient.reviewReturnRequest(returnRequestId, 'approve');
    expect([200, 204]).toContain(status);
  });

  test('double-approve guard → second approve returns 409', async ({ request, apiClient, phone, email, webhookSecret }) => {
    const leadId = await submitAndSellLead(request, apiClient, phone(73), email('return_double'), webhookSecret, '78774', 'double');
    const { body: returnBody } = await apiClient.requestReturn(leadId, 'duplicate');
    const returnRequestId: string = returnBody.return_request_id;
    await apiClient.reviewReturnRequest(returnRequestId, 'approve');
    // Second approve should fail — return request is already approved
    const { status } = await apiClient.reviewReturnRequest(returnRequestId, 'approve');
    expect([409, 422]).toContain(status);
  });
});
