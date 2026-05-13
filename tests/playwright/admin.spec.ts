import { expect, test } from '@playwright/test';
import { existsSync, readFileSync } from 'node:fs';

import { CoworkRun } from './helpers/cowork';
import { paidPilotAdminReviewWorkflow } from './workflows/paid-pilot-admin-review.workflow';

const baseURL = process.env.STORMLEAD_ADMIN_URL ?? 'http://127.0.0.1:8003';

test('admin timeline rejects invalid lead IDs without browser errors', async ({ page }) => {
  const pageErrors: string[] = [];
  const consoleErrors: string[] = [];
  const invalidTimelineResponses: number[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('response', (response) => {
    if (response.url().includes('/v1/admin/leads/not-a-uuid/timeline')) {
      invalidTimelineResponses.push(response.status());
    }
  });

  await page.goto(`${baseURL}/admin`);
  await page.waitForLoadState('networkidle');
  await page.locator('#timeline-lead-id').fill('not-a-uuid');
  await page.getByRole('button', { name: 'Load Timeline' }).click();

  await expect(page.locator('#timeline-summary')).toContainText('valid UUID');
  await expect(page.locator('#timeline-summary')).toHaveAttribute('role', 'alert');
  await expect(page.locator('#timeline-lead-id')).toHaveAttribute('aria-invalid', 'true');
  await expect(page.locator('#workflow-status')).toContainText('valid UUID');
  await expect(page.locator('#timeline')).toBeEmpty();
  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
  expect(invalidTimelineResponses).toEqual([]);
});

test('admin renders paid-pilot autopilot KPIs and exception queue', async ({ page }) => {
  const pageErrors: string[] = [];
  const consoleErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });

  await page.goto(`${baseURL}/admin`);
  await page.waitForLoadState('networkidle');

  await expect(page.getByRole('heading', { name: '99% Autopilot' })).toBeVisible();
  await expect(page.getByRole('table', { name: 'autopilot exception queue' })).toBeVisible();
  await expect(page.locator('#autopilot-label')).toContainText('STP');
  await expect(page.locator('#autopilot-kpis')).toContainText('Straight-through rate');
  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test('cowork creates, funds, and reviews real paid-pilot admin dashboard data', async ({ page }, testInfo) => {
  const cowork = new CoworkRun(page, testInfo, paidPilotAdminReviewWorkflow);
  const suffix = Date.now().toString().slice(-6);
  const company = `Cowork Tree Pros ${suffix}`;
  const targetZip = `78${suffix.slice(0, 3)}`;

  cowork.note('Opening admin dashboard. No Playwright route mocks or API setup shortcuts are installed.');
  await page.goto(`${baseURL}/admin`);
  await page.waitForLoadState('networkidle');
  await cowork.installCursor();
  await cowork.installPanel();
  await cowork.presentPlan();

  await expect(page.getByRole('heading', { name: 'StormLead Admin' })).toBeVisible();
  await expect(page.getByText('Paid-pilot control surface')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Agentic Workflow KPIs' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Lead Workflow Timeline' })).toBeVisible();
  await expect(page.getByRole('table', { name: 'workflow runs' })).toBeVisible();

  await cowork.update('Loaded real admin dashboard', 'load', 'The real admin shell and API-backed widgets are visible.');
  await cowork.moveTo('h1', 'Confirm the real admin surface loaded.');
  await cowork.screenshot('dashboard-loaded', 'Initial real admin page loaded.');

  await cowork.click('#buyer-form', 'Create a real buyer using the visible admin form.');
  await page.locator('#buyer-form input[name="company"]').fill(company);
  await page.locator('#buyer-form input[name="contact_email"]').fill(`ops+${suffix}@cowork-tree.example`);
  await page.locator('#buyer-form input[name="webhook_secret"]').fill(`cowork-secret-${suffix}`);
  await page.locator('#buyer-form input[name="target_zips"]').fill(targetZip);
  await page.locator('#buyer-form input[name="deposit_balance"]').fill('0.00');
  await page.locator('#buyer-form textarea[name="notes"]').fill('Created by the real browser-operated Playwright Cowork workflow.');
  await page.getByRole('button', { name: 'Create Real Buyer' }).click();
  await expect(page.locator('#selected-buyer-id')).not.toHaveValue('', { timeout: 30_000 });
  const buyerId = await page.locator('#selected-buyer-id').inputValue();
  cowork.setSubjectId('buyer_id', buyerId);
  await cowork.update('Created real buyer through UI', 'create', `Created ${company} (${buyerId}) by submitting the real admin form.`);
  cowork.observe(`Created real buyer ${buyerId} (${company}) through the admin UI.`);
  await cowork.screenshot('real-buyer-created', 'Real buyer was created by submitting the browser form.');

  await cowork.click('#buyer-update-form', 'Activate and move the UI-created buyer to funded.');
  await page.locator('#buyer-update-form input[name="target_zips"]').fill(targetZip);
  const updateResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes(`/v1/buyers/${buyerId}`) &&
      response.request().method() === 'PATCH' &&
      response.status() === 200,
  );
  await page.getByRole('button', { name: 'Update Real Buyer' }).click();
  const updateResponse = await updateResponsePromise;
  const updatePayload = await updateResponse.json();
  expect(updatePayload.status).toBe('active');
  expect(updatePayload.sales_stage).toBe('funded');
  await expect(page.locator('#workflow-status')).toContainText(`Updated real buyer ${company}: active/funded.`, {
    timeout: 60_000,
  });
  const buyerRow = page.locator(`tr[data-buyer-id="${buyerId}"]`);
  await expect(buyerRow).toContainText('active', { timeout: 60_000 });
  await expect(buyerRow).toContainText('funded', { timeout: 60_000 });
  await cowork.update('Activated and funded real buyer through UI', 'activate', 'The update form called the real PATCH buyer endpoint and refreshed the roster.');
  cowork.observe('The same UI-created buyer was activated and marked funded through the admin update form.');

  await cowork.click('#deposit-form', 'Add prepaid cash through the browser deposit form.');
  await page.locator('#deposit-form input[name="amount_cents"]').fill('77700');
  await page.locator('#deposit-form input[name="external_reference"]').fill(`playwright-cowork-real-ui-${suffix}`);
  const depositResponsePromise = page.waitForResponse(
    (response) =>
      response.url().includes(`/v1/buyers/${buyerId}/deposits`) &&
      response.request().method() === 'POST' &&
      response.status() === 200,
  );
  await page.getByRole('button', { name: 'Add Real Deposit' }).click();
  const depositResponse = await depositResponsePromise;
  const depositPayload = await depositResponse.json();
  expect(depositPayload.deposit_balance_cents).toBe(77700);
  await expect(page.locator('#workflow-status')).toContainText('Deposit recorded. New wallet: $777.00.', {
    timeout: 60_000,
  });
  await expect(buyerRow).toContainText('$777.00', { timeout: 60_000 });
  await cowork.update('Added real prepaid deposit through UI', 'deposit', 'The deposit form called the real wallet endpoint and the table now shows $777.00.');
  cowork.observe('The buyer wallet was funded through the real deposit endpoint from the browser UI.');

  await cowork.click('.card:nth-of-type(1)', 'Review real prepaid buyer cash before campaigns run.');
  await cowork.assertSelectorText('.card:nth-of-type(1)', '$', 'Prepaid cash is rendered from the real KPI endpoint.');
  cowork.observe('Prepaid cash is backed by the real buyer wallet data funded in this browser run.');

  await cowork.click('.card:nth-of-type(2)', 'Review real active buyer coverage.');
  await cowork.assertSelectorText('.card:nth-of-type(2)', 'Active buyers', 'Active buyer KPI is visible.');

  await cowork.click('.card:nth-of-type(3)', 'Review real sold lead count.');
  await cowork.assertSelectorText('.card:nth-of-type(3)', 'Sold leads', 'Sold lead KPI is visible.');

  await cowork.click('.card:nth-of-type(4)', 'Review real returned lead count.');
  await cowork.assertSelectorText('.card:nth-of-type(4)', 'Returned leads', 'Returned lead KPI is visible.');
  await cowork.update('Verified real KPI cards', 'kpis', 'KPI cards are rendered from backend responses after browser-driven buyer funding.');

  await cowork.click('table', 'Review real funded buyer roster with services and zips.');
  const table = page.getByRole('table', { name: 'buyers' });
  await expect(table).toContainText(company);
  await expect(table).toContainText('active');
  await expect(table).toContainText('funded');
  await expect(table).toContainText('tree_removal');
  await expect(table).toContainText(targetZip);
  await cowork.update('Reviewed real funded buyer roster', 'roster', `The UI-created buyer ${company} is visible with tree_removal, ${targetZip}, active/funded state, and $777.00 wallet balance.`);
  cowork.observe('Buyer roster is populated by the real /v1/buyers endpoint and includes the UI-created funded buyer.');
  await cowork.screenshot('real-buyer-roster-reviewed', 'Real buyer row reviewed with cursor/highlight evidence.');

  await cowork.finish();
  expect(existsSync(cowork.evidencePath)).toBeTruthy();
  const evidence = JSON.parse(readFileSync(cowork.evidencePath, 'utf8'));
  expect(evidence.run_id).toBe(cowork.runId);
  expect(evidence.subject_ids.buyer_id).toBe(buyerId);
});
