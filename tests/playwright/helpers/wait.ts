import type { APIRequestContext } from '@playwright/test';
import { PING_POST } from './api';

const OPERATOR_TOKEN = process.env.STORMLEAD_OPERATOR_TOKEN;

type TimelineBody = {
  current_state?: string;
  events?: Array<{ event_type: string; [k: string]: unknown }>;
  lead?: Record<string, unknown>;
};

const TIMELINE_POLL_TIMEOUT_MS = 5_000;

async function readTimeline(
  request: APIRequestContext,
  leadId: string,
): Promise<{ body?: TimelineBody; error?: string }> {
  try {
    const res = await request.get(`${PING_POST}/v1/admin/leads/${leadId}/timeline`, {
      headers: OPERATOR_TOKEN ? { Authorization: `Bearer ${OPERATOR_TOKEN}` } : undefined,
      timeout: TIMELINE_POLL_TIMEOUT_MS,
    });
    if (!res.ok()) return { error: `HTTP ${res.status()}` };
    return { body: (await res.json()) as TimelineBody };
  } catch (error) {
    return { error: error instanceof Error ? error.message : String(error) };
  }
}

// Polls /v1/admin/leads/{lead_id}/timeline which is the only lead-status source.
// current_state comes from the latest LeadStateTransition row.
export async function waitForLeadStatus(
  request: APIRequestContext,
  leadId: string,
  status: string,
  { timeoutMs = 45_000, intervalMs = 800 } = {},
): Promise<{ current_state: string; events: unknown[]; lead: Record<string, unknown> }> {
  const deadline = Date.now() + timeoutMs;
  let lastPollError: string | undefined;
  while (Date.now() < deadline) {
    const { body, error } = await readTimeline(request, leadId);
    if (body?.current_state === status) {
      return body as { current_state: string; events: unknown[]; lead: Record<string, unknown> };
    }
    if (error) lastPollError = error;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  const suffix = lastPollError ? ` Last timeline poll error: ${lastPollError}` : '';
  throw new Error(`Lead ${leadId} did not reach status "${status}" within ${timeoutMs}ms.${suffix}`);
}

export async function waitForTimelineEvent(
  request: APIRequestContext,
  leadId: string,
  eventType: string,
  { timeoutMs = 45_000, intervalMs = 800 } = {},
): Promise<{ events: Array<{ event_type: string; [k: string]: unknown }> }> {
  const deadline = Date.now() + timeoutMs;
  let lastPollError: string | undefined;
  while (Date.now() < deadline) {
    const { body, error } = await readTimeline(request, leadId);
    const events = body?.events ?? [];
    if (events.some((e) => e.event_type === eventType)) {
      return body as { events: Array<{ event_type: string; [k: string]: unknown }> };
    }
    if (error) lastPollError = error;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  const suffix = lastPollError ? ` Last timeline poll error: ${lastPollError}` : '';
  throw new Error(`Lead ${leadId} did not reach event "${eventType}" within ${timeoutMs}ms.${suffix}`);
}
