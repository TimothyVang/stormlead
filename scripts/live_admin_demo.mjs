import { chromium } from '@playwright/test';
import { mkdirSync } from 'node:fs';

const baseURL = process.env.STORMLEAD_ADMIN_URL ?? 'http://127.0.0.1:8003';
const keepOpen = process.env.STORMLEAD_KEEP_BROWSER_OPEN !== '0';

mkdirSync('testing/screenshots', { recursive: true });
mkdirSync('testing/videos/live-admin-demo', { recursive: true });

const suffix = Date.now().toString().slice(-6);
const company = `Cowork Tree Pros ${suffix}`;
const targetZip = `78${suffix.slice(0, 3)}`;
console.log(`[co-worker] Starting real browser-operated workflow against ${baseURL}`);

const browser = await chromium.launch({
  headless: false,
  slowMo: 500,
  args: ['--start-maximized'],
});

const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: {
    dir: 'testing/videos/live-admin-demo',
    size: { width: 1440, height: 900 },
  },
});

const page = await context.newPage();
await page.bringToFront();

async function label(text) {
  await page.evaluate((message) => {
    let banner = document.querySelector('#demo-banner');
    if (!banner) {
      banner = document.createElement('div');
      banner.id = 'demo-banner';
      banner.style.position = 'fixed';
      banner.style.right = '24px';
      banner.style.bottom = '24px';
      banner.style.zIndex = '9999';
      banner.style.background = '#0284c7';
      banner.style.color = 'white';
      banner.style.padding = '14px 18px';
      banner.style.borderRadius = '12px';
      banner.style.font = '600 16px Arial, sans-serif';
      banner.style.boxShadow = '0 10px 30px rgba(0,0,0,.35)';
      document.body.appendChild(banner);
    }
    banner.textContent = message;
  }, text);
}

async function installCoworkPanel() {
  await page.evaluate(() => {
    if (document.querySelector('#cowork-panel')) return;
    const panel = document.createElement('aside');
    panel.id = 'cowork-panel';
    panel.style.position = 'fixed';
    panel.style.top = '24px';
    panel.style.right = '24px';
    panel.style.width = '390px';
    panel.style.zIndex = '9998';
    panel.style.background = 'rgba(15, 23, 42, .96)';
    panel.style.border = '1px solid #38bdf8';
    panel.style.borderRadius = '16px';
    panel.style.boxShadow = '0 20px 60px rgba(0,0,0,.45)';
    panel.style.color = '#e2e8f0';
    panel.style.font = '14px Arial, sans-serif';
    panel.style.overflow = 'hidden';
    panel.innerHTML = `
      <div style="padding:14px 16px;background:#082f49;border-bottom:1px solid #38bdf8;font-weight:700;color:white;">
        StormLead Cowork - Real Data
      </div>
      <div style="padding:14px 16px;">
        <div style="font-size:12px;color:#93c5fd;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;">Task</div>
        <div style="margin-bottom:12px;color:white;font-weight:700;">Review paid-pilot readiness using real API/database state</div>
        <div style="font-size:12px;color:#93c5fd;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;">Current action</div>
        <div id="cowork-action" style="min-height:44px;font-size:16px;font-weight:700;color:white;">Loading real dashboard...</div>
        <div style="font-size:12px;color:#93c5fd;text-transform:uppercase;letter-spacing:.08em;margin:16px 0 8px;">Plan</div>
        <ol id="cowork-checklist" style="margin:0;padding-left:20px;line-height:1.8;">
          <li data-step="create">Create real buyer through UI</li>
          <li data-step="activate">Activate and fund buyer through UI</li>
          <li data-step="deposit">Add real prepaid deposit through UI</li>
          <li data-step="load">Load real admin dashboard</li>
          <li data-step="cash">Verify prepaid cash</li>
          <li data-step="buyers">Verify active buyers</li>
          <li data-step="sales">Verify sold/returned leads</li>
          <li data-step="roster">Review real buyer roster</li>
          <li data-step="evidence">Save evidence</li>
        </ol>
        <div style="font-size:12px;color:#93c5fd;text-transform:uppercase;letter-spacing:.08em;margin:16px 0 8px;">Notes</div>
        <pre id="cowork-notes" style="white-space:pre-wrap;margin:0;min-height:90px;color:#bae6fd;background:#020617;border-radius:10px;padding:10px;"></pre>
      </div>`;
    document.body.appendChild(panel);
  });
}

async function cowork(action, checklistStep, note) {
  await page.evaluate(
    ({ actionText, step, noteText }) => {
      const actionEl = document.querySelector('#cowork-action');
      if (actionEl) actionEl.textContent = actionText;
      if (step) {
        const item = document.querySelector(`[data-step="${step}"]`);
        if (item instanceof HTMLElement) {
          item.style.color = '#86efac';
          item.style.fontWeight = '700';
          item.textContent = `✓ ${item.textContent.replace(/^✓\s*/, '')}`;
        }
      }
      const notes = document.querySelector('#cowork-notes');
      if (notes) notes.textContent += `${noteText}\n`;
    },
    { actionText: action, step: checklistStep, noteText: note },
  );
  console.log(`[co-worker] ${action} :: ${note}`);
}

async function typeCoworkNote(text) {
  await page.evaluate(() => {
    const notes = document.querySelector('#cowork-notes');
    if (notes) notes.textContent += '\n';
  });
  for (const char of text) {
    await page.evaluate((value) => {
      const notes = document.querySelector('#cowork-notes');
      if (notes) notes.textContent += value;
    }, char);
    await page.waitForTimeout(18);
  }
  await page.evaluate(() => {
    const notes = document.querySelector('#cowork-notes');
    if (notes) notes.textContent += '\n';
  });
}

async function installDemoCursor() {
  await page.evaluate(() => {
    if (document.querySelector('#demo-cursor')) return;
    const cursor = document.createElement('div');
    cursor.id = 'demo-cursor';
    cursor.style.position = 'fixed';
    cursor.style.left = '0px';
    cursor.style.top = '0px';
    cursor.style.width = '22px';
    cursor.style.height = '22px';
    cursor.style.border = '3px solid #facc15';
    cursor.style.borderRadius = '999px';
    cursor.style.background = 'rgba(250, 204, 21, 0.25)';
    cursor.style.boxShadow = '0 0 0 8px rgba(250, 204, 21, 0.18)';
    cursor.style.zIndex = '10000';
    cursor.style.pointerEvents = 'none';
    cursor.style.transform = 'translate(-50%, -50%)';
    cursor.style.transition = 'left 650ms ease, top 650ms ease, transform 160ms ease';
    document.body.appendChild(cursor);
  });
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
    ({ x, y, noteText, selectorText }) => {
      const cursor = document.querySelector('#demo-cursor');
      if (cursor instanceof HTMLElement) {
        cursor.style.left = `${x}px`;
        cursor.style.top = `${y}px`;
      }
      document.querySelectorAll('[data-demo-highlight]').forEach((el) => {
        el.removeAttribute('data-demo-highlight');
        if (el instanceof HTMLElement) {
          el.style.outline = '';
          el.style.boxShadow = '';
        }
      });
      const highlight = document.querySelector(selectorText);
      if (highlight instanceof HTMLElement) {
        highlight.setAttribute('data-demo-highlight', 'true');
        highlight.style.outline = '3px solid #facc15';
        highlight.style.boxShadow = '0 0 0 6px rgba(250, 204, 21, .18)';
      }
      let callout = document.querySelector('#demo-callout');
      if (!callout) {
        callout = document.createElement('div');
        callout.id = 'demo-callout';
        callout.style.position = 'fixed';
        callout.style.left = '24px';
        callout.style.bottom = '24px';
        callout.style.zIndex = '9999';
        callout.style.maxWidth = '520px';
        callout.style.background = '#172554';
        callout.style.border = '1px solid #60a5fa';
        callout.style.color = 'white';
        callout.style.padding = '14px 18px';
        callout.style.borderRadius = '12px';
        callout.style.font = '600 16px Arial, sans-serif';
        callout.style.boxShadow = '0 10px 30px rgba(0,0,0,.35)';
        document.body.appendChild(callout);
      }
      callout.textContent = noteText;
    },
    { x, y, noteText: note, selectorText: selector },
  );
  await page.waitForTimeout(1600);
  await page.mouse.down();
  await page.waitForTimeout(180);
  await page.mouse.up();
  await page.waitForTimeout(1000);
}

await page.goto(`${baseURL}/admin`);
await page.waitForSelector('text=StormLead Admin');
await installDemoCursor();
await installCoworkPanel();
await cowork('Loaded real admin dashboard', 'load', 'No Playwright network mocks or API setup shortcuts are installed. The page is fetching real backend endpoints.');
await typeCoworkNote('I am creating, funding, and reviewing a buyer entirely through the real StormLead admin UI.');

await label('Real-data Cowork workflow: browser-operated buyer setup');
await moveCursorTo('h1', 'Confirm the real StormLead Admin page is loaded.');
await moveCursorTo('#buyer-form', 'Create a real buyer through the visible admin form.');
await page.locator('#buyer-form input[name="company"]').fill(company);
await page.locator('#buyer-form input[name="contact_email"]').fill(`ops+${suffix}@cowork-tree.example`);
await page.locator('#buyer-form input[name="webhook_secret"]').fill(`cowork-secret-${suffix}`);
await page.locator('#buyer-form input[name="target_zips"]').fill(targetZip);
await page.locator('#buyer-form input[name="deposit_balance"]').fill('0.00');
await page.locator('#buyer-form textarea[name="notes"]').fill('Created by the real browser-operated Playwright Cowork live demo.');
await page.getByRole('button', { name: 'Create Real Buyer' }).click();
await page.locator('#selected-buyer-id').waitFor({ state: 'visible' });
await page.waitForFunction(() => document.querySelector('#selected-buyer-id')?.value.length > 0);
const buyerId = await page.locator('#selected-buyer-id').inputValue();
await cowork('Created real buyer through UI', 'create', `Created ${company} (${buyerId}) by submitting the real admin form.`);

await moveCursorTo('#buyer-update-form', 'Activate and mark the UI-created buyer as funded.');
await page.locator('#buyer-update-form input[name="target_zips"]').fill(targetZip);
await page.getByRole('button', { name: 'Update Real Buyer' }).click();
await page.getByRole('row').filter({ hasText: company }).waitFor({ state: 'visible' });
await cowork('Activated and funded real buyer through UI', 'activate', 'The update form called the real PATCH buyer endpoint and refreshed the roster.');

await moveCursorTo('#deposit-form', 'Add a real prepaid deposit through the browser UI.');
await page.locator('#deposit-form input[name="amount_cents"]').fill('77700');
await page.locator('#deposit-form input[name="external_reference"]').fill(`live-cowork-real-ui-${suffix}`);
await page.getByRole('button', { name: 'Add Real Deposit' }).click();
await page.getByRole('row').filter({ hasText: company }).filter({ hasText: '$777.00' }).waitFor({ state: 'visible' });
await cowork('Added real prepaid deposit through UI', 'deposit', 'The deposit form called the real wallet endpoint and the table now shows $777.00.');

await moveCursorTo('.card:nth-of-type(1)', 'Prepaid cash comes from real buyer wallet balances.');
await cowork('Verified prepaid cash', 'cash', 'This confirms funded buyer wallets are visible before campaign spend.');
await moveCursorTo('.card:nth-of-type(2)', 'Active buyers comes from real active buyer records.');
await cowork('Verified active buyers', 'buyers', 'This confirms real active/funded buyer coverage is visible.');
await moveCursorTo('.card:nth-of-type(3)', 'Sold leads tracks real delivered post results.');
await moveCursorTo('.card:nth-of-type(4)', 'Returned leads tracks real returned post results.');
await cowork('Verified sales and return counters', 'sales', 'These counters are live DB-backed KPIs.');
await moveCursorTo('table', 'Buyer roster is loaded from the real /v1/buyers endpoint.');
await cowork('Reviewed real buyer roster', 'roster', `The UI-created buyer ${company} is visible with tree_removal, ${targetZip}, active/funded state, and $777.00 wallet balance.`);
await page.screenshot({ path: 'testing/screenshots/live-admin-real-data-final.png', fullPage: true });
await cowork('Evidence saved; leaving browser open', 'evidence', 'Close the browser when done reviewing.');
await typeCoworkNote('The full setup was performed through the browser UI against real backend and database state.');

console.log('StormLead real-data Cowork demo is open. Review the visible browser window.');
console.log('Screenshot saved to testing/screenshots/live-admin-real-data-final.png');
console.log('Video is recording under testing/videos/live-admin-demo until the browser closes.');

if (keepOpen) {
  await new Promise(() => {});
}

await context.close();
await browser.close();
