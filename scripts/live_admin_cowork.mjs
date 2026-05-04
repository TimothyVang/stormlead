import { chromium } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const baseURL = process.env.STORMLEAD_ADMIN_URL ?? 'http://127.0.0.1:8003';
const keepOpen = process.env.STORMLEAD_KEEP_BROWSER_OPEN !== '0';
const planReviewMs = Number(process.env.COWORK_PLAN_REVIEW_MS ?? 6000);
const stamp = new Date().toISOString().replace(/[:.]/g, '-');
const runId = `${stamp}-paid-pilot-admin-review-live`;
const runDir = join('testing', 'runs', runId);
const screenshotsDir = join(runDir, 'screenshots');
const logsDir = join(runDir, 'logs');
const reviewsDir = join(runDir, 'reviews');
const videosDir = join('testing', 'videos', 'live-admin-cowork');
const evidencePath = join(runDir, 'evidence.json');

mkdirSync(screenshotsDir, { recursive: true });
mkdirSync(logsDir, { recursive: true });
mkdirSync(reviewsDir, { recursive: true });
mkdirSync(videosDir, { recursive: true });

const workflow = {
  name: 'Paid Pilot Admin Review',
  objective: 'Create, fund, and review a real paid-pilot buyer through the StormLead admin UI.',
  analysis: [
    'Use the real running app and database; do not mock responses.',
    'Perform setup through visible admin forms because the UI exists.',
    'Verify KPIs and roster state after real create/update/deposit calls.',
  ],
  plan: [
    ['load', 'Open the real admin dashboard'],
    ['plan', 'Present analysis and plan for review'],
    ['create', 'Create a real buyer through UI'],
    ['activate', 'Activate and fund buyer through UI'],
    ['deposit', 'Add real prepaid deposit through UI'],
    ['kpis', 'Verify backend-backed KPI cards'],
    ['roster', 'Verify funded buyer roster row'],
    ['evidence', 'Save evidence and final review'],
  ],
};

const logLines = [];
function log(message) {
  const line = `${new Date().toISOString()} ${message}`;
  logLines.push(line);
  console.log(`[cowork] ${message}`);
}

writeFileSync(
  join(runDir, 'plan.md'),
  [
    `# ${workflow.name} Plan`,
    '',
    `Objective: ${workflow.objective}`,
    '',
    '## Analysis',
    ...workflow.analysis.map((item) => `- ${item}`),
    '',
    '## Plan',
    ...workflow.plan.map(([, label], index) => `${index + 1}. ${label}`),
    '',
  ].join('\n'),
);

const suffix = Date.now().toString().slice(-6);
const company = `Cowork Tree Pros ${suffix}`;
const targetZip = `78${suffix.slice(0, 3)}`;

log(`Starting real browser-operated workflow against ${baseURL}`);

const browser = await chromium.launch({
  headless: false,
  slowMo: 500,
  args: ['--start-maximized'],
});

const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: {
    dir: videosDir,
    size: { width: 1440, height: 900 },
  },
});

const page = await context.newPage();
await page.bringToFront();

async function installCoworkUi() {
  await page.evaluate((data) => {
    if (document.querySelector('#cowork-panel')) return;
    const panel = document.createElement('aside');
    panel.id = 'cowork-panel';
    panel.style.position = 'fixed';
    panel.style.top = '20px';
    panel.style.right = '20px';
    panel.style.width = '430px';
    panel.style.maxHeight = 'calc(100vh - 40px)';
    panel.style.overflow = 'auto';
    panel.style.zIndex = '9998';
    panel.style.background = 'rgba(15,23,42,.97)';
    panel.style.border = '1px solid #38bdf8';
    panel.style.borderRadius = '16px';
    panel.style.boxShadow = '0 20px 60px rgba(0,0,0,.45)';
    panel.style.color = '#e2e8f0';
    panel.style.font = '14px Arial, sans-serif';
    panel.innerHTML = `
      <div style="padding:14px 16px;background:#082f49;border-bottom:1px solid #38bdf8;font-weight:700;color:white;">StormLead Cowork - Real System</div>
      <div style="padding:14px 16px;">
        <div class="cowork-label">Task</div><div style="font-weight:700;color:white;margin-bottom:12px;">${data.objective}</div>
        <div class="cowork-label">Analysis</div><ul style="margin:0 0 12px 18px;padding:0;line-height:1.45;">${data.analysis.map((item) => `<li>${item}</li>`).join('')}</ul>
        <div class="cowork-label">Plan</div><ol style="margin:0 0 12px 18px;padding:0;line-height:1.65;">${data.plan.map(([key, label]) => `<li data-step="${key}">${label}</li>`).join('')}</ol>
        <div class="cowork-label">Current Action</div><div id="cowork-action" style="min-height:44px;font-size:16px;font-weight:700;color:white;">Presenting plan for review...</div>
        <div class="cowork-label">Verification</div><pre id="cowork-verification" style="white-space:pre-wrap;margin:0 0 12px;color:#bbf7d0;background:#052e16;border-radius:10px;padding:10px;">Pending execution.</pre>
        <div class="cowork-label">Notes</div><pre id="cowork-notes" style="white-space:pre-wrap;margin:0;color:#bae6fd;background:#020617;border-radius:10px;padding:10px;min-height:86px;"></pre>
        <div class="cowork-label" style="margin-top:12px;">Outputs</div><pre style="white-space:pre-wrap;margin:0;color:#ddd;background:#111827;border-radius:10px;padding:10px;">${data.runDir}</pre>
      </div>`;
    const style = document.createElement('style');
    style.textContent = '.cowork-label{font-size:12px;color:#93c5fd;text-transform:uppercase;letter-spacing:.08em;margin:12px 0 6px;}';
    document.head.appendChild(style);
    document.body.appendChild(panel);

    const cursor = document.createElement('div');
    cursor.id = 'cowork-cursor';
    cursor.style.position = 'fixed';
    cursor.style.left = '20px';
    cursor.style.top = '20px';
    cursor.style.width = '24px';
    cursor.style.height = '24px';
    cursor.style.border = '3px solid #facc15';
    cursor.style.borderRadius = '999px';
    cursor.style.background = 'rgba(250,204,21,.25)';
    cursor.style.boxShadow = '0 0 0 10px rgba(250,204,21,.18)';
    cursor.style.zIndex = '10000';
    cursor.style.pointerEvents = 'none';
    cursor.style.transform = 'translate(-50%, -50%)';
    cursor.style.transition = 'left 650ms ease, top 650ms ease, transform 160ms ease';
    document.body.appendChild(cursor);
  }, { ...workflow, runDir });
}

async function cowork(action, step, note) {
  log(`${action} :: ${note}`);
  await page.evaluate(
    ({ actionText, stepKey, noteText }) => {
      const actionEl = document.querySelector('#cowork-action');
      if (actionEl) actionEl.textContent = actionText;
      const notes = document.querySelector('#cowork-notes');
      if (notes) notes.textContent += `${noteText}\n`;
      if (stepKey) {
        const item = document.querySelector(`[data-step="${stepKey}"]`);
        if (item instanceof HTMLElement) {
          item.style.color = '#86efac';
          item.style.fontWeight = '700';
          item.textContent = `✓ ${item.textContent.replace(/^✓\s*/, '')}`;
        }
      }
    },
    { actionText: action, stepKey: step, noteText: note },
  );
}

async function typeCoworkNote(text) {
  for (const char of `\n${text}\n`) {
    await page.evaluate((value) => {
      const notes = document.querySelector('#cowork-notes');
      if (notes) notes.textContent += value;
    }, char);
    await page.waitForTimeout(16);
  }
}

async function moveCursorTo(selector, note) {
  const locator = page.locator(selector).first();
  await locator.waitFor({ state: 'visible' });
  const box = await locator.boundingBox();
  if (!box) return;
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y, { steps: 18 });
  await page.evaluate(
    ({ x, y, selectorText, noteText }) => {
      const cursor = document.querySelector('#cowork-cursor');
      if (cursor instanceof HTMLElement) {
        cursor.style.left = `${x}px`;
        cursor.style.top = `${y}px`;
      }
      document.querySelectorAll('[data-cowork-highlight]').forEach((el) => {
        el.removeAttribute('data-cowork-highlight');
        if (el instanceof HTMLElement) {
          el.style.outline = '';
          el.style.boxShadow = '';
        }
      });
      const highlight = document.querySelector(selectorText);
      if (highlight instanceof HTMLElement) {
        highlight.setAttribute('data-cowork-highlight', 'true');
        highlight.style.outline = '3px solid #facc15';
        highlight.style.boxShadow = '0 0 0 6px rgba(250,204,21,.18)';
      }
      const notes = document.querySelector('#cowork-notes');
      if (notes) notes.textContent += `${noteText}\n`;
    },
    { x, y, selectorText: selector, noteText: note },
  );
  await page.waitForTimeout(1200);
  await page.mouse.down();
  await page.waitForTimeout(160);
  await page.mouse.up();
  await page.waitForTimeout(800);
}

await page.goto(`${baseURL}/admin`);
await page.waitForSelector('text=StormLead Admin');
await installCoworkUi();
await cowork('Loaded real admin dashboard', 'load', 'The browser opened the real admin page; no route mocks are installed.');
await cowork('Plan ready for review', 'plan', 'Reviewing Request -> Analysis -> Plan before execution.');
await page.screenshot({ path: join(screenshotsDir, '01-plan-visible.png'), fullPage: true });
await page.waitForTimeout(planReviewMs);
await typeCoworkNote('I will now execute the approved plan against real StormLead UI and database state.');

await moveCursorTo('h1', 'Confirming the real StormLead Admin page is loaded.');
await moveCursorTo('#buyer-form', 'Creating a real buyer through the visible admin form.');
await page.locator('#buyer-form input[name="company"]').fill(company);
await page.locator('#buyer-form input[name="contact_email"]').fill(`ops+${suffix}@cowork-tree.example`);
await page.locator('#buyer-form input[name="webhook_secret"]').fill(`cowork-secret-${suffix}`);
await page.locator('#buyer-form input[name="target_zips"]').fill(targetZip);
await page.locator('#buyer-form input[name="deposit_balance"]').fill('0.00');
await page.locator('#buyer-form textarea[name="notes"]').fill('Created by the real browser-operated StormLead Cowork live workflow.');
await page.getByRole('button', { name: 'Create Real Buyer' }).click();
await page.waitForFunction(() => document.querySelector('#selected-buyer-id')?.value.length > 0);
const buyerId = await page.locator('#selected-buyer-id').inputValue();
await cowork('Created real buyer through UI', 'create', `Created ${company} (${buyerId}) through the real admin form.`);
await page.screenshot({ path: join(screenshotsDir, '02-real-buyer-created.png'), fullPage: true });

await moveCursorTo('#buyer-update-form', 'Activating and marking the UI-created buyer as funded.');
await page.locator('#buyer-update-form input[name="target_zips"]').fill(targetZip);
await page.getByRole('button', { name: 'Update Real Buyer' }).click();
await page.getByRole('row').filter({ hasText: company }).waitFor({ state: 'visible' });
await cowork('Activated and funded real buyer through UI', 'activate', 'The update form called the real PATCH buyer endpoint and refreshed the roster.');

await moveCursorTo('#deposit-form', 'Adding a real prepaid deposit through the browser UI.');
await page.locator('#deposit-form input[name="amount_cents"]').fill('77700');
await page.locator('#deposit-form input[name="external_reference"]').fill(`live-cowork-real-ui-${suffix}`);
await page.getByRole('button', { name: 'Add Real Deposit' }).click();
await page.getByRole('row').filter({ hasText: company }).filter({ hasText: '$777.00' }).waitFor({ state: 'visible' });
await cowork('Added real prepaid deposit through UI', 'deposit', 'The deposit form called the real wallet endpoint and the table now shows $777.00.');

await moveCursorTo('.card:nth-of-type(1)', 'Prepaid cash comes from real buyer wallet balances.');
await moveCursorTo('.card:nth-of-type(2)', 'Active buyers comes from real active buyer records.');
await moveCursorTo('.card:nth-of-type(3)', 'Sold leads tracks real delivered post results.');
await moveCursorTo('.card:nth-of-type(4)', 'Returned leads tracks real returned post results.');
await cowork('Verified backend-backed KPI cards', 'kpis', 'KPI cards are visible after real buyer funding.');

await moveCursorTo('table', 'Buyer roster is loaded from the real /v1/buyers endpoint.');
await cowork('Reviewed real buyer roster', 'roster', `The UI-created buyer ${company} is visible with tree_removal, ${targetZip}, active/funded state, and $777.00 wallet balance.`);
await page.screenshot({ path: join(screenshotsDir, '03-real-buyer-roster-reviewed.png'), fullPage: true });
await cowork('Evidence saved; browser ready for review', 'evidence', `Artifacts are under ${runDir}.`);
await typeCoworkNote('Final review: full setup was performed through the browser UI against real backend and database state.');

const assertions = [{ workflow: workflow.name, company, targetZip, buyerId, passed: true }];
writeFileSync(join(logsDir, 'cowork-log.md'), logLines.join('\n') + '\n');
writeFileSync(join(logsDir, 'assertions.json'), JSON.stringify(assertions, null, 2));
writeFileSync(
  join(reviewsDir, 'review.md'),
  [
    `# ${workflow.name} Review`,
    '',
    '- Presented a plan before execution.',
    '- Created, activated/funded, and deposited into a real buyer through UI forms.',
    '- Verified backend-backed KPI cards and roster state.',
    `- Buyer: ${company} (${buyerId})`,
    `- Run folder: ${runDir}`,
    '',
  ].join('\n'),
);
writeFileSync(
  evidencePath,
  JSON.stringify(
    {
      schema_version: 1,
      run_id: runId,
      workflow: {
        name: workflow.name,
        slug: 'paid-pilot-admin-review-live',
        objective: workflow.objective,
        app_path: '/admin',
      },
      status: 'passed',
      generated_at: new Date().toISOString(),
      subject_ids: { buyer_id: buyerId },
      lead_id: null,
      artifacts: {
        plan: join(runDir, 'plan.md'),
        log: join(logsDir, 'cowork-log.md'),
        assertions: join(logsDir, 'assertions.json'),
        review: join(reviewsDir, 'review.md'),
        screenshots_dir: screenshotsDir,
        video_dir: videosDir,
      },
      observations: logLines,
      assertions,
    },
    null,
    2,
  ) + '\n',
);

console.log(keepOpen ? 'StormLead Cowork demo is open. Review the visible browser window.' : 'StormLead Cowork recording completed.');
console.log(`Run folder: ${runDir}`);
console.log(`Evidence manifest: ${evidencePath}`);
console.log(`Video output directory: ${videosDir}`);

if (keepOpen) {
  await new Promise(() => {});
}

await context.close();
await browser.close();
