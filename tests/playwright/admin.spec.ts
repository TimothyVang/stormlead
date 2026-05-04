import { expect, test } from '@playwright/test';
import { copyFileSync, mkdirSync } from 'node:fs';
import { basename, join } from 'node:path';

const baseURL = process.env.STORMLEAD_ADMIN_URL ?? 'http://127.0.0.1:8765';

test.afterEach(async ({ page }, testInfo) => {
  const video = page.video();
  if (!video) return;

  const videoPath = await video.path();
  mkdirSync('testing/videos', { recursive: true });
  const target = join('testing/videos', `${testInfo.status}-${basename(videoPath)}`);
  copyFileSync(videoPath, target);
  console.log(`Saved video: ${target}`);
});

test('admin dashboard renders paid-pilot buyer data', async ({ page }) => {
  console.log('StormLead browser smoke: starting mocked paid-pilot admin review');

  await page.route('**/v1/admin/kpis', async (route) => {
    console.log('Mocking /v1/admin/kpis with prepaid cash, buyers, sales, and returns');
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        prepaid_cash_cents: 125000,
        active_buyers: 3,
        sold_leads: 8,
        returned_leads: 1,
        lead_revenue_cents: 64000,
      }),
    });
  });

  await page.route('**/v1/buyers', async (route) => {
    console.log('Mocking /v1/buyers with a funded tree-removal buyer');
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        buyers: [
          {
            company: 'Austin Tree Pros',
            status: 'active',
            sales_stage: 'funded',
            deposit_balance_cents: 50000,
            services: ['tree_removal'],
            target_zips: ['78701', '78702'],
          },
        ],
      }),
    });
  });

  await page.goto(`${baseURL}/admin`);
  console.log(`Opened ${baseURL}/admin`);

  await expect(page.getByRole('heading', { name: 'StormLead Admin' })).toBeVisible();
  await expect(page.getByText('Paid-pilot control surface')).toBeVisible();
  await expect(page.getByText('$1250.00')).toBeVisible();
  await expect(page.getByRole('table', { name: 'buyers' })).toContainText('Austin Tree Pros');
  await expect(page.getByRole('table', { name: 'buyers' })).toContainText('tree_removal');

  await page.screenshot({
    path: 'testing/screenshots/admin-paid-pilot-dashboard.png',
    fullPage: true,
  });
  console.log('Saved screenshot: testing/screenshots/admin-paid-pilot-dashboard.png');
});
