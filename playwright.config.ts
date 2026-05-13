import { defineConfig, devices } from '@playwright/test';

const visibleSlowMoMs = Number(process.env.STORMLEAD_PLAYWRIGHT_SLOW_MO_MS ?? 150);
const LOCAL_TEST_HOSTS = new Set(['127.0.0.1', 'localhost']);

function localHttpUrl(label: string, rawUrl: string): string {
  const url = new URL(rawUrl);
  if (url.protocol !== 'http:' || (!LOCAL_TEST_HOSTS.has(url.hostname) && !url.hostname.endsWith('.localhost'))) {
    throw new Error(`${label} must stay on local HTTP, got ${rawUrl}`);
  }
  return rawUrl;
}

export default defineConfig({
  testDir: './tests/playwright',
  outputDir: './testing/playwright-artifacts',
  timeout: 120_000,
  workers: 1,
  globalSetup: './tests/playwright/global-setup.ts',
  reporter: [
    ['line'],
    ['html', { outputFolder: './testing/playwright-report', open: 'never' }],
    ['json', { outputFile: './testing/logs/playwright-results.json' }],
  ],
  use: {
    baseURL: localHttpUrl('STORMLEAD_ADMIN_URL', process.env.STORMLEAD_ADMIN_URL ?? 'http://127.0.0.1:8003'),
  },
  projects: [
    {
      name: 'api',
      testMatch: [
        '**/lead-scenarios.spec.ts',
        '**/webhook-security.spec.ts',
        '**/buyer-lifecycle.spec.ts',
        '**/return-workflow.spec.ts',
        '**/kpi-readiness.spec.ts',
        '**/paid-pilot-autopilot.spec.ts',
      ],
      use: {
        headless: true,
        video: 'off',
        trace: 'off',
        screenshot: 'off',
      },
    },
    {
      name: 'chromium',
      testMatch: [
        '**/admin.spec.ts',
        '**/buyer-wallet-ui.spec.ts',
        '**/landing-local-submit.spec.ts',
        '**/human-lead-sale.spec.ts',
        '**/human-persona-workflows.spec.ts',
        '**/role-experience.spec.ts',
        '**/operator-review.spec.ts',
      ],
      dependencies: ['api'],
      use: {
        ...devices['Desktop Chrome'],
        headless: false,
        launchOptions: {
          slowMo: Number.isFinite(visibleSlowMoMs) ? visibleSlowMoMs : 150,
        },
        screenshot: 'on',
        trace: 'on',
        video: 'on',
      },
    },
  ],
});
