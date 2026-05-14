import type { APIRequestContext, Page } from '@playwright/test';
import { randomInt } from 'node:crypto';

export const FORM_RECEIVER = process.env.FORM_RECEIVER_URL ?? 'http://127.0.0.1:8002';
export const PING_POST     = process.env.PING_POST_URL     ?? 'http://127.0.0.1:8003';
export const LANDING       = process.env.LANDING_URL       ?? 'http://127.0.0.1:8005';
export const BUYER_PORTAL  = process.env.BUYER_PORTAL_URL  ?? 'http://127.0.0.1:8004';
export const OPERATOR_TOKEN = process.env.STORMLEAD_OPERATOR_TOKEN ?? 'local-operator-token-change-me';
const PHONE_MID_COUNT = 700;
const PHONE_SUFFIX_COUNT = 9000;
const PHONE_SPACE = PHONE_MID_COUNT * PHONE_SUFFIX_COUNT;

type RequestOptions = { data?: unknown; headers?: Record<string, string> };

export function operatorHeaders(headers: Record<string, string> = {}): Record<string, string> {
  if (!OPERATOR_TOKEN) return headers;
  return { ...headers, Authorization: `Bearer ${OPERATOR_TOKEN}` };
}

export async function installOperatorToken(page: Page): Promise<void> {
  await page.addInitScript((token) => {
    window.localStorage.setItem('stormlead_operator_token', token);
  }, OPERATOR_TOKEN);
}

function withOperatorHeaders(options: RequestOptions = {}): RequestOptions {
  return {
    ...options,
    headers: operatorHeaders(options.headers),
  };
}

export function runSeed(): number {
  return randomInt(0, PHONE_SPACE);
}

export function syntheticPhone(seed: number, offset: number): string {
  const phoneIndex = (seed + offset * 7919) % PHONE_SPACE;
  const mid = (200 + Math.floor(phoneIndex / PHONE_SUFFIX_COUNT)).toString().padStart(3, '0');
  const suffix = (1000 + (phoneIndex % PHONE_SUFFIX_COUNT)).toString().padStart(4, '0');
  return `+1512${mid}${suffix}`;
}

export function syntheticEmail(scenario: string, seed: number): string {
  return `playwright-${scenario}-${seed}@example-stormlead-test.com`;
}

export class StormLeadApiClient {
  constructor(private readonly req: APIRequestContext) {}

  // POST /v1/buyers — full required payload
  async createBuyer(data: {
    name: string;
    company: string;
    contact_email: string;
    contact_phone_e164: string;
    webhook_url: string;
    webhook_secret: string;
    bid_per_lead_t1_t2: number;
    bid_per_lead_t3: number;
    bid_per_call: number;
    filter_expression: string;
    services?: string[];
    target_zips?: string[];
    deposit_balance?: number;
    daily_cap?: number;
  }) {
    const res = await this.req.post(`${PING_POST}/v1/buyers`, withOperatorHeaders({ data }));
    return { status: res.status(), body: await res.json() };
  }

  // PATCH /v1/buyers/{buyer_id} — partial update; pass {status: "active"} to activate
  async updateBuyer(buyerId: string, data: Record<string, unknown>) {
    const res = await this.req.patch(`${PING_POST}/v1/buyers/${buyerId}`, withOperatorHeaders({ data }));
    return { status: res.status(), body: await res.json() };
  }

  // POST /v1/buyers/{buyer_id}/deposits — amount_cents is integer cents
  async addDeposit(buyerId: string, amountCents: number, externalReference?: string) {
    const res = await this.req.post(`${PING_POST}/v1/buyers/${buyerId}/deposits`, withOperatorHeaders({
      data: { amount_cents: amountCents, external_reference: externalReference ?? null },
    }));
    return { status: res.status(), body: await res.json() };
  }

  async getBuyer(buyerId: string) {
    const res = await this.req.get(`${PING_POST}/v1/buyers/${buyerId}`);
    return { status: res.status(), body: await res.json() };
  }

  async rotateBuyerApiKey(buyerId: string) {
    const res = await this.req.post(`${PING_POST}/v1/buyers/${buyerId}/api-key/rotate`, withOperatorHeaders());
    return { status: res.status(), body: await res.json() };
  }

  async listBuyers() {
    const res = await this.req.get(`${PING_POST}/v1/buyers`, withOperatorHeaders());
    return { status: res.status(), body: await res.json() };
  }

  async getWallet(buyerId: string) {
    const res = await this.req.get(`${PING_POST}/v1/buyers/${buyerId}/wallet`, withOperatorHeaders());
    return { status: res.status(), body: await res.json() };
  }

  async getBuyerDailyReport(buyerId: string) {
    const res = await this.req.get(`${PING_POST}/v1/buyers/${buyerId}/daily-report`, withOperatorHeaders());
    return { status: res.status(), body: await res.json() };
  }

  // GET /v1/admin/leads/{lead_id}/timeline — also contains current_state and lead summary
  async getTimeline(leadId: string) {
    const res = await this.req.get(`${PING_POST}/v1/admin/leads/${leadId}/timeline`, withOperatorHeaders());
    return { status: res.status(), body: await res.json() };
  }

  // POST /v1/admin/leads/{lead_id}/review — action: "hold" | "approve" | "review"
  async reviewLead(leadId: string, action: 'hold' | 'approve' | 'review', notes?: string) {
    const res = await this.req.post(`${PING_POST}/v1/admin/leads/${leadId}/review`, withOperatorHeaders({
      data: { action, notes: notes ?? null, operator: 'playwright-test' },
    }));
    return { status: res.status(), body: await res.json() };
  }

  // POST /v1/leads/{lead_id}/return — returns { return_request_id, ... }
  async requestReturn(leadId: string, reason: string, notes?: string) {
    const res = await this.req.post(`${PING_POST}/v1/leads/${leadId}/return`, withOperatorHeaders({
      data: { reason, notes: notes ?? null, evidence: {}, requested_by: 'playwright-test' },
    }));
    return { status: res.status(), body: await res.json() };
  }

  // POST /v1/return-requests/{id}/review — action: "approve" | "reject" | "hold"
  async reviewReturnRequest(returnRequestId: string, action: 'approve' | 'reject' | 'hold', notes?: string) {
    const res = await this.req.post(`${PING_POST}/v1/return-requests/${returnRequestId}/review`, withOperatorHeaders({
      data: { action, notes: notes ?? null, operator: 'playwright-test' },
    }));
    return { status: res.status(), body: await res.json() };
  }

  // GET /v1/admin/kpis — returns { prepaid_cash_cents, active_buyers, sold_leads, returned_leads, lead_revenue_cents }
  async getKPIs() {
    const res = await this.req.get(`${PING_POST}/v1/admin/kpis`, withOperatorHeaders());
    return { status: res.status(), body: await res.json() };
  }

  // GET /v1/admin/launch-readiness — returns { readiness_label, local_simulation_ready, checks, metrics, ... }
  async getLaunchReadiness() {
    const res = await this.req.get(`${PING_POST}/v1/admin/launch-readiness`, withOperatorHeaders());
    return { status: res.status(), body: await res.json() };
  }

  // GET /v1/admin/workflow-kpis
  async getWorkflowKPIs() {
    const res = await this.req.get(`${PING_POST}/v1/admin/workflow-kpis`, withOperatorHeaders());
    return { status: res.status(), body: await res.json() };
  }

  async getAutopilotKPIs() {
    const res = await this.req.get(`${PING_POST}/v1/admin/autopilot/kpis`, withOperatorHeaders());
    return { status: res.status(), body: await res.json() };
  }

  async getAutopilotExceptions(params?: { kind?: string; lead_id?: string; buyer_id?: string; limit?: number }) {
    const url = new URL(`${PING_POST}/v1/admin/autopilot/exceptions`);
    if (params?.kind) url.searchParams.set('kind', params.kind);
    if (params?.lead_id) url.searchParams.set('lead_id', params.lead_id);
    if (params?.buyer_id) url.searchParams.set('buyer_id', params.buyer_id);
    if (params?.limit) url.searchParams.set('limit', String(params.limit));
    const res = await this.req.get(url.toString(), withOperatorHeaders());
    return { status: res.status(), body: await res.json() };
  }

  async getNormalizedKPIs(params?: { market_state?: string; market_zip?: string }) {
    const url = new URL(`${PING_POST}/v1/kpis/normalized`);
    if (params?.market_state) url.searchParams.set('market_state', params.market_state);
    if (params?.market_zip) url.searchParams.set('market_zip', params.market_zip);
    const res = await this.req.get(url.toString(), withOperatorHeaders());
    return { status: res.status(), body: await res.json() };
  }

  async healthz(baseUrl: string) {
    const res = await this.req.get(`${baseUrl}/healthz`);
    return res.status();
  }
}
