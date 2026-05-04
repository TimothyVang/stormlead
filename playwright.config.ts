import { defineConfig, devices } from '@playwright/test';

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
