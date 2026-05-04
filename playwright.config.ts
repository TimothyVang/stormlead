import { defineConfig, devices } from '@playwright/test';

const visibleSlowMoMs = Number(process.env.STORMLEAD_PLAYWRIGHT_SLOW_MO_MS ?? 150);

export default defineConfig({
  testDir: './tests/playwright',
  outputDir: './testing/playwright-artifacts',
  timeout: 120_000,
  reporter: [
    ['line'],
    ['html', { outputFolder: './testing/playwright-report', open: 'never' }],
    ['json', { outputFile: './testing/logs/playwright-results.json' }],
  ],
  use: {
    baseURL: process.env.STORMLEAD_ADMIN_URL ?? 'http://127.0.0.1:8003',
    headless: false,
    launchOptions: {
      slowMo: Number.isFinite(visibleSlowMoMs) ? visibleSlowMoMs : 150,
    },
    screenshot: 'on',
    trace: 'on',
    video: 'on',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
