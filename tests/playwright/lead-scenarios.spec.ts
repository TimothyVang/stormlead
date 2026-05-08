import { test, expect } from './fixtures';
import { FORM_RECEIVER } from './helpers/api';
import { buildSignedHeaders, buildEnvelope } from './helpers/webhook';
import { waitForLeadStatus, waitForTimelineEvent } from './helpers/wait';

test.describe('Lead Lifecycle Scenarios', () => {
  test('qualified_sold — lead reaches sold after auction', async ({ request, apiClient, phone, email, webhookSecret }) => {
    const zip = '78761';
    const buyer = await apiClient.createBuyer({
      name: 'Playwright Qualified Sold',
      company: 'Playwright Qualified Sold Co',
      contact_email: `buyer-qualified-sold-${Date.now()}@example-stormlead-test.com`,
      contact_phone_e164: `+1512${Date.now().toString().slice(-7)}`,
      webhook_url: 'http://host.docker.internal:9999/buyer-qualified-sold',
      webhook_secret: 'playwright-qualified-sold-secret',
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
      scenario: 'qualified_sold',
      phone: phone(0),
      email: email('qualified_sold'),
      state: 'TX',
      zip,
    });
    const { headers, bodyStr } = buildSignedHeaders(webhookId, envelope, webhookSecret);

    const postRes = await request.post(`${FORM_RECEIVER}/webhooks/formbricks`, {
      headers,
      data: bodyStr,
    });
    expect(postRes.status()).toBe(200);
    const accepted = await postRes.json();
    expect(accepted.status).toBe('accepted');
    const leadId: string = accepted.lead_id;

    // current_state comes from the timeline endpoint (only lead status source)
    const timeline = await waitForLeadStatus(request, leadId, 'sold', { timeoutMs: 45_000 });
    expect(timeline.current_state).toBe('sold');
    // The timeline response also includes the lead summary
    expect(timeline.lead).toBeDefined();
  });

  test('unsold_no_buyer — lead reaches unsold when no buyer covers the zip', async ({ request, phone, email, webhookSecret }) => {
    const { envelope, webhookId } = buildEnvelope({
      scenario: 'unsold_no_buyer',
      phone: phone(10),
      email: email('unsold'),
      state: 'AK',
      zip: '99501',
    });
    const { headers, bodyStr } = buildSignedHeaders(webhookId, envelope, webhookSecret);
    const postRes = await request.post(`${FORM_RECEIVER}/webhooks/formbricks`, { headers, data: bodyStr });
    expect(postRes.status()).toBe(200);
    const { lead_id: leadId } = await postRes.json();
    const timeline = await waitForTimelineEvent(request, leadId, 'lead.unsold', { timeoutMs: 45_000 });
    expect(timeline.events.some((event) => event.event_type === 'lead.unsold')).toBeTruthy();
  });

  test('rejected_low_quality — lead reaches rejected for low-quality signal', async ({ request, phone, email, webhookSecret }) => {
    const { envelope, webhookId } = buildEnvelope({
      scenario: 'rejected_low_quality',
      phone: phone(20),
      email: email('rejected'),
      state: 'TX',
      zip: '78702',
    });
    // Near-zero dwell signals bot traffic
    (envelope as Record<string, any>).data.data.dwell_ms = 500;
    const { headers, bodyStr } = buildSignedHeaders(webhookId, envelope, webhookSecret);
    const postRes = await request.post(`${FORM_RECEIVER}/webhooks/formbricks`, { headers, data: bodyStr });
    expect(postRes.status()).toBe(200);
    const { lead_id: leadId } = await postRes.json();
    const timeline = await waitForTimelineEvent(request, leadId, 'lead.rejected', { timeoutMs: 45_000 });
    expect(timeline.events.some((event) => event.event_type === 'lead.rejected')).toBeTruthy();
  });

  test('duplicate_capture — second submission with same phone returns accepted-duplicate', async ({ request, phone, email, webhookSecret }) => {
    const sharedPhone = phone(30);
    const sharedEmail = email('duplicate');

    const id1 = `pw-dup-1-${Date.now()}`;
    const id2 = `pw-dup-2-${Date.now() + 1}`;
    const base = { scenario: 'duplicate_capture', phone: sharedPhone, email: sharedEmail, state: 'TX', zip: '78701' };

    const { envelope: env1 } = buildEnvelope({ ...base, webhookId: id1 });
    const { headers: h1, bodyStr: s1 } = buildSignedHeaders(id1, env1, webhookSecret);
    const res1 = await request.post(`${FORM_RECEIVER}/webhooks/formbricks`, { headers: h1, data: s1 });
    expect(res1.status()).toBe(200);

    await new Promise((r) => setTimeout(r, 2000));

    const { envelope: env2 } = buildEnvelope({ ...base, webhookId: id2 });
    const { headers: h2, bodyStr: s2 } = buildSignedHeaders(id2, env2, webhookSecret);
    const res2 = await request.post(`${FORM_RECEIVER}/webhooks/formbricks`, { headers: h2, data: s2 });
    expect(res2.status()).toBe(200);
    expect((await res2.json()).status).toBe('accepted-duplicate');
  });

  test('suppressed_opt_out — opted-out contact returns suppressed', async ({ request, phone, email, webhookSecret }) => {
    const suppressedPhone = phone(40);
    const suppressedEmail = email('suppressed');

    const optOutRes = await request.post(`${FORM_RECEIVER}/v1/privacy/opt-out`, {
      data: { phone: suppressedPhone, email: suppressedEmail },
    });
    expect([200, 204]).toContain(optOutRes.status());

    const { envelope, webhookId } = buildEnvelope({
      scenario: 'suppressed_opt_out',
      phone: suppressedPhone,
      email: suppressedEmail,
      state: 'TX',
      zip: '78701',
    });
    const { headers, bodyStr } = buildSignedHeaders(webhookId, envelope, webhookSecret);
    const postRes = await request.post(`${FORM_RECEIVER}/webhooks/formbricks`, { headers, data: bodyStr });
    expect(postRes.status()).toBe(200);
    expect((await postRes.json()).status).toBe('suppressed');
  });

  test('idempotency — same webhook-id twice is handled without duplicate lead', async ({ request, phone, email, webhookSecret }) => {
    const sharedWebhookId = `pw-idempotent-${Date.now()}`;
    const { envelope } = buildEnvelope({
      scenario: 'idempotent',
      phone: phone(50),
      email: email('idempotent'),
      state: 'TX',
      zip: '78701',
      webhookId: sharedWebhookId,
    });
    const { headers, bodyStr } = buildSignedHeaders(sharedWebhookId, envelope, webhookSecret);

    const res1 = await request.post(`${FORM_RECEIVER}/webhooks/formbricks`, { headers, data: bodyStr });
    expect(res1.status()).toBe(200);

    const res2 = await request.post(`${FORM_RECEIVER}/webhooks/formbricks`, { headers, data: bodyStr });
    expect([200, 409]).toContain(res2.status());
  });
});
