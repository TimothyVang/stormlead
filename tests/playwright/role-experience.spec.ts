import { expect, test } from '@playwright/test';
import { existsSync, readFileSync } from 'node:fs';

import { CoworkRun } from './helpers/cowork';
import {
  roleExperienceRoles,
  roleExperienceWorkflow,
  sampleScenarioNames,
} from './workflows/role-experience.workflow';
import { installOperatorToken, operatorHeaders } from './helpers/api';

const baseURL = process.env.STORMLEAD_ADMIN_URL ?? 'http://127.0.0.1:8003';

test('role-based agentic workflow sample data is visible and reviewable', async ({
  page,
  request,
}, testInfo) => {
  const cowork = new CoworkRun(page, testInfo, roleExperienceWorkflow);
  const reviewStamp = Date.now();
  await installOperatorToken(page);

  cowork.note(
    `Testing roles: ${roleExperienceRoles.map((role) => role.name).join(', ')}`,
  );
  cowork.note(`Expected sample scenarios: ${sampleScenarioNames.join(', ')}`);

  await page.goto(`${baseURL}/admin`);
  await page.waitForLoadState('networkidle');
  await cowork.installCursor();
  await cowork.installPanel();
  await cowork.presentPlan();

  await expect(page.getByRole('heading', { name: 'StormLead Admin' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Agentic Workflow KPIs' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Lead Workflow Timeline' })).toBeVisible();
  await expect(page.getByRole('table', { name: 'workflow runs' })).toBeVisible();
  await expect(page.getByRole('table', { name: 'buyers' })).toBeVisible();
  await cowork.update(
    'Operator/admin surface loaded',
    'operator',
    'The local admin UI exposes KPIs, workflow runs, timeline review controls, readiness, and buyer roster sections.',
  );

  const runsResponse = await request.get(`${baseURL}/v1/admin/workflow-runs/recent?limit=20`, {
    headers: operatorHeaders(),
  });
  expect(runsResponse.ok()).toBeTruthy();
  const runsPayload = await runsResponse.json();
  const runs = Array.isArray(runsPayload.runs) ? runsPayload.runs : [];
  expect(runs.length, 'run scripts/simulate_v1_leads.py before browser proof').toBeGreaterThan(0);
  const leadId = String(runs[0].lead_id);
  cowork.setSubjectId('lead_id', leadId);
  await cowork.update(
    'Homeowner sample lead is visible',
    'homeowner',
    `Recent workflow data includes synthetic homeowner lead ${leadId}; no real homeowner contact is used.`,
  );

  const timelineResponse = await request.get(
    `${baseURL}/v1/admin/leads/${encodeURIComponent(leadId)}/timeline`,
    { headers: operatorHeaders() },
  );
  expect(timelineResponse.ok()).toBeTruthy();
  const timeline = await timelineResponse.json();
  const eventTypes = (timeline.events || []).map((event: { event_type: string }) => event.event_type);
  expect(eventTypes).toContain('lead.captured');
  expect(
    eventTypes.some((eventType: string) =>
      [
        'lead.enriched',
        'lead.qualified',
        'lead.rejected',
        'lead.sold',
        'lead.unsold',
        'lead.nurtured',
      ].includes(eventType),
    ),
    `expected agentic workflow events in ${eventTypes.join(', ')}`,
  ).toBeTruthy();
  await cowork.update(
    'Agentic worker timeline verified',
    'agent',
    `Lead ${leadId} has persisted workflow events: ${eventTypes.join(', ')}.`,
  );

  const selectedRun = page
    .locator(`#workflow-runs tr[data-lead-id="${leadId}"]`)
    .filter({ hasText: String(runs[0].latest_event_type) })
    .first();
  await expect(selectedRun).toBeVisible({ timeout: 30_000 });
  await selectedRun.locator('td').first().click();
  await expect(page.locator('#timeline-summary')).toContainText(leadId, { timeout: 30_000 });
  await cowork.screenshot(
    'homeowner-agent-timeline',
    'Homeowner and agentic workflow evidence appears in the admin timeline.',
  );

  const buyersResponse = await request.get(`${baseURL}/v1/buyers`, { headers: operatorHeaders() });
  expect(buyersResponse.ok()).toBeTruthy();
  const buyersPayload = await buyersResponse.json();
  const buyers = Array.isArray(buyersPayload.buyers) ? buyersPayload.buyers : [];
  const fundedBuyer = buyers.find(
    (buyer: {
      buyer_id: string;
      status: string;
      deposit_balance_cents: number;
      services?: string[];
      target_zips?: string[];
    }) =>
      buyer.status === 'active' &&
      buyer.deposit_balance_cents > 0 &&
      (buyer.services || []).includes('tree_removal') &&
      (buyer.target_zips || []).length > 0,
  );
  expect(fundedBuyer, 'seed or simulate data must include an active funded buyer').toBeTruthy();
  cowork.setSubjectId('buyer_id', fundedBuyer.buyer_id);

  const reportResponse = await request.get(
    `${baseURL}/v1/buyers/${encodeURIComponent(fundedBuyer.buyer_id)}/daily-report`,
    { headers: operatorHeaders() },
  );
  expect(reportResponse.ok()).toBeTruthy();
  const report = await reportResponse.json();
  expect(report.buyer.buyer_id).toBe(fundedBuyer.buyer_id);
  expect(report.delivery).toHaveProperty('delivered_leads');
  expect(report.delivery).toHaveProperty('pending_return_requests');
  await cowork.update(
    'Buyer/contractor report verified',
    'buyer',
    `Buyer ${fundedBuyer.company} has wallet/report data available through the local daily-report API.`,
  );

  const buyerRow = page.locator(`tr[data-buyer-id="${fundedBuyer.buyer_id}"]`);
  await expect(buyerRow).toBeVisible({ timeout: 30_000 });
  await buyerRow.scrollIntoViewIfNeeded();
  await cowork.screenshot(
    'buyer-contractor-roster',
    'Buyer/contractor role evidence is visible in the admin roster.',
  );

  const holdNotes = `Role UX proof hold ${reviewStamp}`;
  await page.locator('#review-notes').fill(holdNotes);
  const holdResponse = page.waitForResponse(
    (response) =>
      response.url().includes(`/v1/admin/leads/${leadId}/review`) &&
      response.request().method() === 'POST' &&
      response.status() === 200,
  );
  await page.getByRole('button', { name: 'Hold For Review' }).click();
  const holdPayload = await (await holdResponse).json();
  expect(holdPayload.action).toBe('hold');
  expect(holdPayload.hold_for_review).toBe(true);
  expect(holdPayload.timeline_event.event_type).toBe('admin.review.hold');
  await expect(page.locator('#workflow-status')).toContainText('Review action recorded', {
    timeout: 30_000,
  });

  const approveNotes = `Role UX proof approve ${reviewStamp}`;
  await page.locator('#review-notes').fill(approveNotes);
  const approveResponse = page.waitForResponse(
    (response) =>
      response.url().includes(`/v1/admin/leads/${leadId}/review`) &&
      response.request().method() === 'POST' &&
      response.status() === 200,
  );
  await page.getByRole('button', { name: 'Approve / Clear Hold' }).click();
  const approvePayload = await (await approveResponse).json();
  expect(approvePayload.action).toBe('approve');
  expect(approvePayload.hold_for_review).toBe(false);
  expect(approvePayload.timeline_event.event_type).toBe('admin.review.approve');
  await expect(page.locator('#workflow-status')).toContainText('Review action recorded', {
    timeout: 30_000,
  });
  await cowork.update(
    'Operator review controls verified',
    'review',
    `Operator held and approved lead ${leadId} through the visible admin timeline controls.`,
  );
  await cowork.screenshot(
    'operator-review-controls',
    'Operator/admin role can hold and approve the selected workflow run.',
  );

  const readinessResponse = await request.get(`${baseURL}/v1/admin/launch-readiness`, {
    headers: operatorHeaders(),
  });
  expect(readinessResponse.ok()).toBeTruthy();
  const readiness = await readinessResponse.json();
  expect(readiness.technical_local_ready).toBeTruthy();
  expect(readiness.commercial_paid_launch_ready).toBeFalsy();
  expect(readiness.checks.commercial_launch_approval_present).toBeFalsy();
  await cowork.update(
    'Business owner readiness verified',
    'business',
    `Readiness label is ${readiness.readiness_label}; technical local proof is available while commercial launch stays blocked.`,
  );
  await cowork.screenshot(
    'business-owner-readiness',
    'Business owner role can inspect readiness, wallet coverage, buyer coverage, and launch lock status.',
  );

  await cowork.finish();
  expect(existsSync(cowork.evidencePath)).toBeTruthy();
  const evidence = JSON.parse(readFileSync(cowork.evidencePath, 'utf8'));
  expect(evidence.run_id).toBe(cowork.runId);
  expect(evidence.subject_ids.lead_id).toBe(leadId);
  expect(evidence.subject_ids.buyer_id).toBe(fundedBuyer.buyer_id);
});
