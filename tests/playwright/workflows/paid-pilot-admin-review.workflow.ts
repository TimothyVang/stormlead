export const paidPilotAdminReviewWorkflow = {
  name: 'Paid Pilot Admin Review',
  slug: 'paid-pilot-admin-review',
  objective: 'Verify StormLead can create, fund, and review a paid-pilot buyer using the real admin UI.',
  appPath: '/admin',
  inputs: [
    'Running ping-post FastAPI app at STORMLEAD_ADMIN_URL or http://127.0.0.1:8003',
    'Real database with current migrations applied',
    'No Playwright route mocks or mocked buyer/KPI data',
  ],
  outputs: [
    'testing/runs/<timestamp>-paid-pilot-admin-review/plan.md',
    'testing/runs/<timestamp>-paid-pilot-admin-review/evidence.json',
    'testing/runs/<timestamp>-paid-pilot-admin-review/logs/cowork-log.md',
    'testing/runs/<timestamp>-paid-pilot-admin-review/logs/assertions.json',
    'testing/runs/<timestamp>-paid-pilot-admin-review/reviews/review.md',
    'testing/runs/<timestamp>-paid-pilot-admin-review/screenshots/',
  ],
  analysis: [
    'The workflow must prove real business behavior, not a static page or mocked response.',
    'The browser should perform all setup actions through visible admin forms because those controls exist.',
    'KPI and roster verification should observe backend-populated UI state after real create/update/deposit calls.',
  ],
  plan: [
    { key: 'load', label: 'Open the real StormLead admin dashboard' },
    { key: 'plan', label: 'Present analysis and plan for review' },
    { key: 'create', label: 'Create a real buyer through the admin form' },
    { key: 'activate', label: 'Activate and move the buyer to funded' },
    { key: 'deposit', label: 'Add real prepaid wallet cash' },
    { key: 'kpis', label: 'Verify real KPI cards from backend responses' },
    { key: 'roster', label: 'Verify the funded buyer appears in the roster' },
    { key: 'evidence', label: 'Save screenshots, logs, assertions, and review notes' },
  ],
  reviewNotes: [
    'The admin workflow is now browser-operable for buyer onboarding and wallet funding.',
    'Follow-up: add buyer detail pages, wallet history, and return-credit review workflows.',
  ],
} as const;

export type PaidPilotAdminReviewWorkflow = typeof paidPilotAdminReviewWorkflow;
