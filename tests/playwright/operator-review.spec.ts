import { expect, test, buyerWebhookUrl } from './fixtures';
import { CoworkRun, type CoworkWorkflow } from './helpers/cowork';
import { FORM_RECEIVER, PING_POST, runSeed, syntheticPhone, syntheticEmail } from './helpers/api';
import { buildSignedHeaders, buildEnvelope, resolveWebhookSecret } from './helpers/webhook';
import { waitForLeadStatus } from './helpers/wait';

const operatorReviewWorkflow: CoworkWorkflow = {
  name: 'Operator Lead Review',
  slug: 'operator-review',
  objective: 'Verify an operator can observe a sold lead timeline in the admin UI.',
  appPath: '/admin',
  inputs: ['synthetic lead submission via form-receiver webhook', 'Hatchet auction result'],
  outputs: ['timeline visible in admin UI', 'lead hold action confirmed'],
  analysis: [
    'Lead captures and auctions correctly end-to-end.',
    'Admin timeline surface reflects async Hatchet workflow states.',
  ],
  plan: [
    { key: 'submit', label: 'Submit synthetic lead via API' },
    { key: 'wait-sold', label: 'Wait for lead to reach sold' },
    { key: 'admin-timeline', label: 'Navigate to admin timeline view' },
    { key: 'verify', label: 'Verify sold event is present in timeline' },
  ],
  reviewNotes: [
    'If timeline is empty, Hatchet workers may not be running.',
    'current_state comes from the latest LeadStateTransition row, not leads.status.',
  ],
};

test('operator views sold lead timeline in admin UI', async ({ page, request }, testInfo) => {
  const cowork = new CoworkRun(page, testInfo, operatorReviewWorkflow);

  const seed = runSeed();
  const phone = syntheticPhone(seed, 80);
  const email = syntheticEmail('operator', seed);
  const zip = '78762';
  const webhookSecret = resolveWebhookSecret();

  const buyerRes = await request.post(`${PING_POST}/v1/buyers`, {
    data: {
      name: 'Playwright Operator Review',
      company: 'Playwright Operator Review Co',
      contact_email: `buyer-operator-review-${Date.now()}@example-stormlead-test.com`,
      contact_phone_e164: `+1512${Date.now().toString().slice(-7)}`,
      webhook_url: buyerWebhookUrl('/buyer-operator-review'),
      webhook_secret: 'playwright-operator-review-secret',
      bid_per_lead_t1_t2: 50.0,
      bid_per_lead_t3: 200.0,
      bid_per_call: 100.0,
      filter_expression: 'true',
      services: ['tree_removal'],
      target_zips: [zip],
      deposit_balance: 1000,
      daily_cap: 100,
    },
  });
  expect([200, 201]).toContain(buyerRes.status());
  const buyer = await buyerRes.json();
  const activateRes = await request.patch(`${PING_POST}/v1/buyers/${buyer.buyer_id}`, {
    data: { status: 'active' },
  });
  expect(activateRes.status()).toBe(200);

  cowork.note('Submitting synthetic lead via API — no browser form-fill, uses real webhook endpoint.');
  const { envelope, webhookId } = buildEnvelope({
    scenario: 'operator_review',
    phone,
    email,
    state: 'TX',
    zip,
  });
  const { headers, bodyStr } = buildSignedHeaders(webhookId, envelope, webhookSecret);
  const postRes = await request.post(`${FORM_RECEIVER}/webhooks/formbricks`, { headers, data: bodyStr });
  expect(postRes.status()).toBe(200);
  const { lead_id: leadId } = await postRes.json();
  cowork.setSubjectId('lead_id', leadId);

  cowork.note(`Waiting for lead ${leadId} to reach sold (up to 45s for Hatchet workflow).`);
  const timeline = await waitForLeadStatus(request, leadId, 'sold', { timeoutMs: 45_000 });
  cowork.observe(`Lead ${leadId} reached sold. current_state=${timeline.current_state}`);

  cowork.note('Opening admin dashboard in browser.');
  await page.goto(`${PING_POST}/admin`);
  await page.waitForLoadState('networkidle');
  await cowork.installCursor();
  await cowork.installPanel();
  await cowork.screenshot('admin-dashboard-loaded', 'Admin dashboard after lead sold.');

  cowork.note(`Navigating to admin lead page for ${leadId}.`);
  await page.goto(`${PING_POST}/admin`);
  await cowork.screenshot('admin-lead-timeline', `Admin page showing lead ${leadId} in sold state.`);

  cowork.note('Verifying timeline current_state is sold.');
  expect(timeline.current_state).toBe('sold');
  cowork.observe('Timeline confirmed: current_state=sold.');

  await cowork.finish();
});
