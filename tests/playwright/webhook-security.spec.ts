import { test, expect } from './fixtures';
import { FORM_RECEIVER } from './helpers/api';
import {
  buildEnvelope,
  buildSignedHeaders,
  buildExpiredHeaders,
  buildWrongSignatureHeaders,
  buildMissingHeadersRequest,
} from './helpers/webhook';

test.describe('Webhook Security Guards', () => {
  test('wrong signature → 401', async ({ request, phone, email, webhookSecret }) => {
    const { envelope, webhookId } = buildEnvelope({
      scenario: 'sec_wrong_sig',
      phone: phone(60),
      email: email('sec_wrong'),
      state: 'TX',
      zip: '78701',
    });
    const { headers, bodyStr } = buildWrongSignatureHeaders(webhookId, envelope, webhookSecret);
    const res = await request.post(`${FORM_RECEIVER}/webhooks/formbricks`, { headers, data: bodyStr });
    expect(res.status()).toBe(401);
  });

  test('expired timestamp → 409 replay attack', async ({ request, phone, email, webhookSecret }) => {
    const { envelope, webhookId } = buildEnvelope({
      scenario: 'sec_replay',
      phone: phone(61),
      email: email('sec_replay'),
      state: 'TX',
      zip: '78701',
    });
    const { headers, bodyStr } = buildExpiredHeaders(webhookId, envelope, webhookSecret);
    const res = await request.post(`${FORM_RECEIVER}/webhooks/formbricks`, { headers, data: bodyStr });
    expect(res.status()).toBe(409);
  });

  test('missing webhook headers → 400', async ({ request, phone, email }) => {
    const { envelope } = buildEnvelope({
      scenario: 'sec_no_headers',
      phone: phone(62),
      email: email('sec_missing'),
      state: 'TX',
      zip: '78701',
    });
    const { headers, body } = buildMissingHeadersRequest(envelope);
    const res = await request.post(`${FORM_RECEIVER}/webhooks/formbricks`, { headers, data: body });
    expect(res.status()).toBe(400);
  });

  test('valid signature passes security guard', async ({ request, phone, email, webhookSecret }) => {
    const { envelope, webhookId } = buildEnvelope({
      scenario: 'sec_valid',
      phone: phone(63),
      email: email('sec_valid'),
      state: 'TX',
      zip: '78701',
    });
    const { headers, bodyStr } = buildSignedHeaders(webhookId, envelope, webhookSecret);
    const res = await request.post(`${FORM_RECEIVER}/webhooks/formbricks`, { headers, data: bodyStr });
    expect(res.status()).toBe(200);
  });
});
