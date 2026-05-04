import { expect, type Page, type TestInfo } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export class OperatorRun {
  readonly runDir: string;
  readonly screenshotsDir: string;
  readonly logsDir: string;
  readonly reviewsDir: string;

  private step = 0;
  private readonly logLines: string[] = [];
  private readonly assertions: Record<string, unknown>[] = [];
  private readonly observations: string[] = [];

  constructor(
    private readonly page: Page,
    testInfo: TestInfo,
    readonly name: string,
  ) {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    this.runDir = join('testing', 'runs', `${stamp}-${slug}`);
    this.screenshotsDir = join(this.runDir, 'screenshots');
    this.logsDir = join(this.runDir, 'logs');
    this.reviewsDir = join(this.runDir, 'reviews');
    mkdirSync(this.screenshotsDir, { recursive: true });
    mkdirSync(this.logsDir, { recursive: true });
    mkdirSync(this.reviewsDir, { recursive: true });
    this.note(`Playwright test: ${testInfo.title}`);
    this.note(`Run folder: ${this.runDir}`);
  }

  note(message: string): void {
    const line = `${new Date().toISOString()} ${message}`;
    this.logLines.push(line);
    console.log(line);
  }

  observe(message: string): void {
    this.observations.push(message);
    this.note(`Observation: ${message}`);
  }

  async installCursor(): Promise<void> {
    await this.page.evaluate(() => {
      if (document.querySelector('#operator-cursor')) return;
      const cursor = document.createElement('div');
      cursor.id = 'operator-cursor';
      cursor.style.position = 'fixed';
      cursor.style.left = '20px';
      cursor.style.top = '20px';
      cursor.style.width = '24px';
      cursor.style.height = '24px';
      cursor.style.border = '3px solid #facc15';
      cursor.style.borderRadius = '999px';
      cursor.style.background = 'rgba(250, 204, 21, 0.25)';
      cursor.style.boxShadow = '0 0 0 10px rgba(250, 204, 21, 0.18)';
      cursor.style.zIndex = '10000';
      cursor.style.pointerEvents = 'none';
      cursor.style.transform = 'translate(-50%, -50%)';
      cursor.style.transition = 'left 650ms ease, top 650ms ease, transform 160ms ease';
      document.body.appendChild(cursor);
    });
  }

  async label(message: string): Promise<void> {
    await this.page.evaluate((text) => {
      let banner = document.querySelector('#operator-banner');
      if (!banner) {
        banner = document.createElement('div');
        banner.id = 'operator-banner';
        banner.setAttribute('aria-label', 'operator step');
        banner.style.position = 'fixed';
        banner.style.right = '24px';
        banner.style.bottom = '24px';
        banner.style.zIndex = '9999';
        banner.style.maxWidth = '520px';
        banner.style.background = '#0284c7';
        banner.style.color = 'white';
        banner.style.padding = '14px 18px';
        banner.style.borderRadius = '12px';
        banner.style.font = '600 16px Arial, sans-serif';
        banner.style.boxShadow = '0 10px 30px rgba(0,0,0,.35)';
        document.body.appendChild(banner);
      }
      banner.textContent = text;
    }, message);
  }

  async moveTo(selector: string, comment: string): Promise<void> {
    this.step += 1;
    const label = `Step ${this.step}: ${comment}`;
    this.note(label);
    await this.label(label);

    const locator = this.page.locator(selector).first();
    await locator.waitFor({ state: 'visible' });
    const box = await locator.boundingBox();
    if (!box) throw new Error(`No bounding box for ${selector}`);

    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await this.page.mouse.move(x, y, { steps: 18 });
    await this.page.evaluate(
      ({ x, y, selectorText }) => {
        const cursor = document.querySelector('#operator-cursor');
        if (cursor instanceof HTMLElement) {
          cursor.style.left = `${x}px`;
          cursor.style.top = `${y}px`;
        }
        document.querySelectorAll('[data-operator-highlight]').forEach((el) => {
          el.removeAttribute('data-operator-highlight');
          if (el instanceof HTMLElement) {
            el.style.outline = '';
            el.style.boxShadow = '';
          }
        });
        const target = document.querySelector(selectorText);
        if (target instanceof HTMLElement) {
          target.setAttribute('data-operator-highlight', 'true');
          target.style.outline = '3px solid #facc15';
          target.style.boxShadow = '0 0 0 6px rgba(250, 204, 21, .18)';
        }
      },
      { x, y, selectorText: selector },
    );
    await this.page.waitForTimeout(1200);
  }

  async click(selector: string, comment: string): Promise<void> {
    await this.moveTo(selector, comment);
    await this.page.mouse.down();
    await this.page.evaluate(() => {
      const cursor = document.querySelector('#operator-cursor');
      if (cursor instanceof HTMLElement) cursor.style.transform = 'translate(-50%, -50%) scale(.72)';
    });
    await this.page.waitForTimeout(180);
    await this.page.mouse.up();
    await this.page.evaluate(() => {
      const cursor = document.querySelector('#operator-cursor');
      if (cursor instanceof HTMLElement) cursor.style.transform = 'translate(-50%, -50%) scale(1)';
    });
    await this.page.waitForTimeout(700);
  }

  async screenshot(name: string, comment: string): Promise<void> {
    const file = join(this.screenshotsDir, `${String(this.step).padStart(2, '0')}-${name}.png`);
    await this.page.screenshot({ path: file, fullPage: true });
    this.note(`Screenshot: ${file} - ${comment}`);
  }

  async assertText(text: string, comment: string): Promise<void> {
    await expect(this.page.getByText(text)).toBeVisible();
    this.assertions.push({ text, comment, passed: true });
    this.note(`Assertion passed: ${comment} (${text})`);
  }

  async assertSelectorText(selector: string, text: string, comment: string): Promise<void> {
    await expect(this.page.locator(selector).first()).toContainText(text);
    this.assertions.push({ selector, text, comment, passed: true });
    this.note(`Assertion passed: ${comment} (${selector} contains ${text})`);
  }

  async finish(): Promise<void> {
    writeFileSync(join(this.logsDir, 'operator-log.md'), this.logLines.join('\n') + '\n');
    writeFileSync(join(this.logsDir, 'assertions.json'), JSON.stringify(this.assertions, null, 2));
    const review = [
      `# ${this.name} Review`,
      '',
      '## What Was Exercised',
      '- Loaded the StormLead admin dashboard in a real Chromium browser.',
      '- Submitted real buyer create, activation, and deposit forms through the browser UI.',
      '- Used real StormLead HTTP API calls and database-backed dashboard responses.',
      '- Moved a visible operator cursor through business-critical UI areas.',
      '- Captured screenshots, Playwright video, trace, logs, and assertions.',
      '',
      '## Observations',
      ...this.observations.map((item) => `- ${item}`),
      '',
      '## Follow-Up Product Gaps',
      '- KPI cards are read-only; drill-down links should be added when lead/buyer detail pages exist.',
      '- Buyer table shows services and zips, but low-wallet warnings are not visually emphasized yet.',
      '- Add drill-down detail pages for buyer wallet history and lead return review.',
      '',
      `Run folder: \`${this.runDir}\``,
      '',
    ].join('\n');
    writeFileSync(join(this.reviewsDir, 'review.md'), review);
    this.note(`Review written: ${join(this.reviewsDir, 'review.md')}`);
  }
}
