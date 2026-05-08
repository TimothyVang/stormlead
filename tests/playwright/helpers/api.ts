import type { APIRequestContext } from '@playwright/test';

export const FORM_RECEIVER = process.env.FORM_RECEIVER_URL ?? 'http://127.0.0.1:8002';
export const PING_POST     = process.env.PING_POST_URL     ?? 'http://127.0.0.1:8003';
export const LANDING       = process.env.LANDING_URL       ?? 'http://127.0.0.1:8005';
export const BUYER_PORTAL  = process.env.BUYER_PORTAL_URL  ?? 'http://127.0.0.1:8004';
const OPERATOR_TOKEN = process.env.STORMLEAD_OPERATOR_TOKEN;

type RequestOptions = { data?: unknown; headers?: Record<string, string> };

function withOperatorHeaders(options: RequestOptions = {}): RequestOptions {
  if (!OPERATOR_TOKEN) return options;
  return {
    ...options,
    headers: { ...(options.headers ?? {}), Authorization: `Bearer ${OPERATOR_TOKEN}` },
  };
}

export function runSeed(): number {
  return Date.now() % 10_000_000;
}

export function syntheticPhone(seed: number, offset: number): string {
  const mid = (200 + (seed % 700)).toString().padStart(3, '0');
  const suffix = (1000 + ((seed * 97 + offset) % 9000)).toString().padStart(4, '0');
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

  async listBuyers() {
    const res = await this.req.get(`${PING_POST}/v1/buyers`, withOperatorHeaders());
    return { status: res.status(), body: await res.json() };
  }

  async getWallet(buyerId: string) {
    const res = await this.req.get(`${PING_POST}/v1/buyers/${buyerId}/wallet`);
    return { status: res.status(), body: await res.json() };
  }

  async getBuyerDailyReport(buyerId: string) {
    const res = await this.req.get(`${PING_POST}/v1/buyers/${buyerId}/daily-report`);
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
    const res = await this.req.post(`${PING_POST}/v1/leads/${leadId}/return`, {
      data: { reason, notes: notes ?? null, evidence: {}, requested_by: 'playwright-test' },
    });
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

  async healthz(baseUrl: string) {
    const res = await this.req.get(`${baseUrl}/healthz`);
    return res.status();
  }
}
