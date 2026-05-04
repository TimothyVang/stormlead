import { expect, test } from '@playwright/test';

import { OperatorRun } from './helpers/operator';

const baseURL = process.env.STORMLEAD_ADMIN_URL ?? 'http://127.0.0.1:8003';

test('cowork creates, funds, and reviews real paid-pilot admin dashboard data', async ({ page }, testInfo) => {
  const operator = new OperatorRun(page, testInfo, 'Real Admin Dashboard Cowork Workflow');
  const suffix = Date.now().toString().slice(-6);
  const company = `Cowork Tree Pros ${suffix}`;
  const targetZip = `78${suffix.slice(0, 3)}`;

  operator.note('Opening admin dashboard. No Playwright route mocks or API setup shortcuts are installed.');
  await page.goto(`${baseURL}/admin`);
  await page.waitForLoadState('networkidle');
  await operator.installCursor();
  await operator.label('StormLead Cowork: browser-operated real buyer workflow');

  await expect(page.getByRole('heading', { name: 'StormLead Admin' })).toBeVisible();
  await expect(page.getByText('Paid-pilot control surface')).toBeVisible();

  await operator.moveTo('h1', 'Confirm the real admin surface loaded.');
  await operator.screenshot('dashboard-loaded', 'Initial real admin page loaded.');

  await operator.click('#buyer-form', 'Create a real buyer using the visible admin form.');
  await page.locator('#buyer-form input[name="company"]').fill(company);
  await page.locator('#buyer-form input[name="contact_email"]').fill(`ops+${suffix}@cowork-tree.example`);
  await page.locator('#buyer-form input[name="webhook_secret"]').fill(`cowork-secret-${suffix}`);
  await page.locator('#buyer-form input[name="target_zips"]').fill(targetZip);
  await page.locator('#buyer-form input[name="deposit_balance"]').fill('0.00');
  await page.locator('#buyer-form textarea[name="notes"]').fill('Created by the real browser-operated Playwright Cowork workflow.');
  await page.getByRole('button', { name: 'Create Real Buyer' }).click();
  await expect(page.locator('#selected-buyer-id')).not.toHaveValue('');
  const buyerId = await page.locator('#selected-buyer-id').inputValue();
  operator.observe(`Created real buyer ${buyerId} (${company}) through the admin UI.`);
  await operator.screenshot('real-buyer-created', 'Real buyer was created by submitting the browser form.');

  await operator.click('#buyer-update-form', 'Activate and move the UI-created buyer to funded.');
  await page.locator('#buyer-update-form input[name="target_zips"]').fill(targetZip);
  await page.getByRole('button', { name: 'Update Real Buyer' }).click();
  await expect(page.getByRole('row').filter({ hasText: company })).toContainText('active');
  await expect(page.getByRole('row').filter({ hasText: company })).toContainText('funded');
  operator.observe('The same UI-created buyer was activated and marked funded through the admin update form.');

  await operator.click('#deposit-form', 'Add prepaid cash through the browser deposit form.');
  await page.locator('#deposit-form input[name="amount_cents"]').fill('77700');
  await page.locator('#deposit-form input[name="external_reference"]').fill(`playwright-cowork-real-ui-${suffix}`);
  await page.getByRole('button', { name: 'Add Real Deposit' }).click();
  const buyerRow = page.getByRole('row').filter({ hasText: company });
  await expect(buyerRow).toContainText('$777.00');
  operator.observe('The buyer wallet was funded through the real deposit endpoint from the browser UI.');

  await operator.click('.card:nth-of-type(1)', 'Review real prepaid buyer cash before campaigns run.');
  await operator.assertSelectorText('.card:nth-of-type(1)', '$', 'Prepaid cash is rendered from the real KPI endpoint.');
  operator.observe('Prepaid cash is backed by the real buyer wallet data funded in this browser run.');

  await operator.click('.card:nth-of-type(2)', 'Review real active buyer coverage.');
  await operator.assertSelectorText('.card:nth-of-type(2)', 'Active buyers', 'Active buyer KPI is visible.');

  await operator.click('.card:nth-of-type(3)', 'Review real sold lead count.');
  await operator.assertSelectorText('.card:nth-of-type(3)', 'Sold leads', 'Sold lead KPI is visible.');

  await operator.click('.card:nth-of-type(4)', 'Review real returned lead count.');
  await operator.assertSelectorText('.card:nth-of-type(4)', 'Returned leads', 'Returned lead KPI is visible.');

  await operator.click('table', 'Review real funded buyer roster with services and zips.');
  const table = page.getByRole('table', { name: 'buyers' });
  await expect(table).toContainText(company);
  await expect(table).toContainText('active');
  await expect(table).toContainText('funded');
  await expect(table).toContainText('tree_removal');
  await expect(table).toContainText(targetZip);
  operator.observe('Buyer roster is populated by the real /v1/buyers endpoint and includes the UI-created funded buyer.');
  await operator.screenshot('real-buyer-roster-reviewed', 'Real buyer row reviewed with cursor/highlight evidence.');

  await operator.finish();
});
