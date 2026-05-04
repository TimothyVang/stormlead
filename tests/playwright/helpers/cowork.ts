import { expect, type Page, type TestInfo } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

type WorkflowStep = { key: string; label: string };

export type CoworkWorkflow = {
  name: string;
  slug: string;
  objective: string;
  appPath: string;
  inputs: readonly string[];
  outputs: readonly string[];
  analysis: readonly string[];
  plan: readonly WorkflowStep[];
  reviewNotes: readonly string[];
};

export class CoworkRun {
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
    readonly workflow: CoworkWorkflow,
  ) {
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    this.runDir = join('testing', 'runs', `${stamp}-${workflow.slug}`);
    this.screenshotsDir = join(this.runDir, 'screenshots');
    this.logsDir = join(this.runDir, 'logs');
    this.reviewsDir = join(this.runDir, 'reviews');
    mkdirSync(this.screenshotsDir, { recursive: true });
    mkdirSync(this.logsDir, { recursive: true });
    mkdirSync(this.reviewsDir, { recursive: true });
    this.note(`Playwright test: ${testInfo.title}`);
    this.note(`Run folder: ${this.runDir}`);
    this.writePlan();
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

  async installPanel(): Promise<void> {
    await this.page.evaluate((workflow) => {
      if (document.querySelector('#cowork-panel')) return;
      const panel = document.createElement('aside');
      panel.id = 'cowork-panel';
      panel.style.position = 'fixed';
      panel.style.top = '20px';
      panel.style.right = '20px';
      panel.style.width = '420px';
      panel.style.maxHeight = 'calc(100vh - 40px)';
      panel.style.overflow = 'auto';
      panel.style.zIndex = '9998';
      panel.style.background = 'rgba(15, 23, 42, .97)';
      panel.style.border = '1px solid #38bdf8';
      panel.style.borderRadius = '16px';
      panel.style.boxShadow = '0 20px 60px rgba(0,0,0,.45)';
      panel.style.color = '#e2e8f0';
      panel.style.font = '14px Arial, sans-serif';
      panel.innerHTML = `
        <div style="padding:14px 16px;background:#082f49;border-bottom:1px solid #38bdf8;font-weight:700;color:white;">
          StormLead Cowork - Real System
        </div>
        <div style="padding:14px 16px;">
          <div class="cowork-label">Task</div>
          <div style="margin-bottom:12px;color:white;font-weight:700;">${workflow.objective}</div>
          <div class="cowork-label">Analysis</div>
          <ul style="margin:0 0 12px 18px;padding:0;line-height:1.45;">${workflow.analysis.map((item) => `<li>${item}</li>`).join('')}</ul>
          <div class="cowork-label">Plan</div>
          <ol id="cowork-checklist" style="margin:0 0 12px 18px;padding:0;line-height:1.65;">${workflow.plan.map((step) => `<li data-step="${step.key}">${step.label}</li>`).join('')}</ol>
          <div class="cowork-label">Current Action</div>
          <div id="cowork-action" style="min-height:44px;font-size:16px;font-weight:700;color:white;">Presenting plan for review...</div>
          <div class="cowork-label">Verification</div>
          <pre id="cowork-verification" style="white-space:pre-wrap;margin:0 0 12px;color:#bbf7d0;background:#052e16;border-radius:10px;padding:10px;">Pending execution.</pre>
          <div class="cowork-label">Notes</div>
          <pre id="cowork-notes" style="white-space:pre-wrap;margin:0;color:#bae6fd;background:#020617;border-radius:10px;padding:10px;min-height:86px;"></pre>
          <div class="cowork-label" style="margin-top:12px;">Outputs</div>
          <ul id="cowork-outputs" style="margin:0 0 0 18px;padding:0;line-height:1.45;">${workflow.outputs.map((item) => `<li>${item}</li>`).join('')}</ul>
        </div>`;
      const style = document.createElement('style');
      style.textContent = '.cowork-label{font-size:12px;color:#93c5fd;text-transform:uppercase;letter-spacing:.08em;margin:12px 0 6px;}';
      document.head.appendChild(style);
      document.body.appendChild(panel);
    }, this.workflow);
  }

  async installCursor(): Promise<void> {
    await this.page.evaluate(() => {
      if (document.querySelector('#cowork-cursor')) return;
      const cursor = document.createElement('div');
      cursor.id = 'cowork-cursor';
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

  async presentPlan(reviewMs = Number(process.env.COWORK_PLAN_REVIEW_MS ?? 1200)): Promise<void> {
    this.note('Cowork plan presented for review.');
    await this.update('Reviewing plan before execution', 'plan', 'Plan displayed. No mocks will be used; all actions go through the real admin UI.');
    await this.screenshot('plan-visible', 'Cowork plan is visible before execution.');
    await this.page.waitForTimeout(reviewMs);
  }

  async update(action: string, stepKey: string | null, note: string): Promise<void> {
    this.note(`${action} :: ${note}`);
    await this.page.evaluate(
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
      { actionText: action, step: stepKey, noteText: note },
    );
  }

  async typeNote(text: string): Promise<void> {
    await this.page.evaluate(() => {
      const notes = document.querySelector('#cowork-notes');
      if (notes) notes.textContent += '\n';
    });
    for (const char of text) {
      await this.page.evaluate((value) => {
        const notes = document.querySelector('#cowork-notes');
        if (notes) notes.textContent += value;
      }, char);
      await this.page.waitForTimeout(8);
    }
    await this.page.evaluate(() => {
      const notes = document.querySelector('#cowork-notes');
      if (notes) notes.textContent += '\n';
    });
  }

  async moveTo(selector: string, comment: string): Promise<void> {
    this.step += 1;
    const label = `Step ${this.step}: ${comment}`;
    this.note(label);

    const locator = this.page.locator(selector).first();
    await locator.waitFor({ state: 'visible' });
    const box = await locator.boundingBox();
    if (!box) throw new Error(`No bounding box for ${selector}`);

    const x = box.x + box.width / 2;
    const y = box.y + box.height / 2;
    await this.page.mouse.move(x, y, { steps: 18 });
    await this.page.evaluate(
      ({ x, y, selectorText }) => {
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
        const target = document.querySelector(selectorText);
        if (target instanceof HTMLElement) {
          target.setAttribute('data-cowork-highlight', 'true');
          target.style.outline = '3px solid #facc15';
          target.style.boxShadow = '0 0 0 6px rgba(250, 204, 21, .18)';
        }
      },
      { x, y, selectorText: selector },
    );
    await this.page.waitForTimeout(850);
  }

  async click(selector: string, comment: string): Promise<void> {
    await this.moveTo(selector, comment);
    await this.page.mouse.down();
    await this.page.evaluate(() => {
      const cursor = document.querySelector('#cowork-cursor');
      if (cursor instanceof HTMLElement) cursor.style.transform = 'translate(-50%, -50%) scale(.72)';
    });
    await this.page.waitForTimeout(150);
    await this.page.mouse.up();
    await this.page.evaluate(() => {
      const cursor = document.querySelector('#cowork-cursor');
      if (cursor instanceof HTMLElement) cursor.style.transform = 'translate(-50%, -50%) scale(1)';
    });
    await this.page.waitForTimeout(500);
  }

  async screenshot(name: string, comment: string): Promise<void> {
    const file = join(this.screenshotsDir, `${String(this.step).padStart(2, '0')}-${name}.png`);
    await this.page.screenshot({ path: file, fullPage: true });
    this.note(`Screenshot: ${file} - ${comment}`);
  }

  async assertSelectorText(selector: string, text: string, comment: string): Promise<void> {
    await expect(this.page.locator(selector).first()).toContainText(text);
    this.assertions.push({ selector, text, comment, passed: true });
    this.note(`Assertion passed: ${comment} (${selector} contains ${text})`);
    await this.page.evaluate((line) => {
      const verification = document.querySelector('#cowork-verification');
      if (verification) verification.textContent += `\n✓ ${line}`;
    }, comment);
  }

  async finish(): Promise<void> {
    await this.update('Workflow verified; evidence saved', 'evidence', `Run artifacts written under ${this.runDir}.`);
    writeFileSync(join(this.logsDir, 'cowork-log.md'), this.logLines.join('\n') + '\n');
    writeFileSync(join(this.logsDir, 'assertions.json'), JSON.stringify(this.assertions, null, 2));
    const review = [
      `# ${this.workflow.name} Review`,
      '',
      '## What Was Exercised',
      '- Loaded the StormLead admin dashboard in a real Chromium browser.',
      '- Presented a Cowork plan before execution.',
      '- Submitted real buyer create, activation, and deposit forms through the browser UI.',
      '- Used real StormLead HTTP API calls and database-backed dashboard responses.',
      '- Moved a visible Cowork cursor through business-critical UI areas.',
      '- Captured screenshots, Playwright video, trace, logs, assertions, and review notes.',
      '',
      '## Observations',
      ...this.observations.map((item) => `- ${item}`),
      '',
      '## Follow-Up Product Gaps',
      ...this.workflow.reviewNotes.map((item) => `- ${item}`),
      '',
      `Run folder: \`${this.runDir}\``,
      '',
    ].join('\n');
    writeFileSync(join(this.reviewsDir, 'review.md'), review);
    this.note(`Review written: ${join(this.reviewsDir, 'review.md')}`);
  }

  private writePlan(): void {
    const plan = [
      `# ${this.workflow.name} Plan`,
      '',
      `Objective: ${this.workflow.objective}`,
      '',
      '## Inputs',
      ...this.workflow.inputs.map((item) => `- ${item}`),
      '',
      '## Analysis',
      ...this.workflow.analysis.map((item) => `- ${item}`),
      '',
      '## Plan',
      ...this.workflow.plan.map((step, index) => `${index + 1}. ${step.label}`),
      '',
      '## Outputs',
      ...this.workflow.outputs.map((item) => `- ${item}`),
      '',
    ].join('\n');
    writeFileSync(join(this.runDir, 'plan.md'), plan);
  }
}
