import type { ConsoleMessage, Page, Request, Response, WebSocket } from '@playwright/test';
import { appendFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

type Severity = 'info' | 'warning' | 'error';

type BrowserEvent = {
  schema_version: 1;
  at: string;
  run_id: string;
  type: string;
  severity: Severity;
  page_url: string;
  data: Record<string, unknown>;
};

export type BrowserObserverSummary = {
  schema_version: 1;
  run_id: string;
  generated_at: string;
  event_counts: Record<string, number>;
  error_count: number;
  recent_errors: BrowserEvent[];
  artifacts: {
    browser_events_jsonl: string;
    browser_summary_json: string;
  };
};

const MAX_TEXT_LENGTH = Number(process.env.STORMLEAD_BROWSER_LOG_MAX_TEXT ?? 4000);
const MAX_BODY_LENGTH = Number(process.env.STORMLEAD_BROWSER_LOG_MAX_BODY ?? 8000);

function truncate(value: unknown, maxLength = MAX_TEXT_LENGTH): string {
  const text = String(value ?? '');
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...[truncated ${text.length - maxLength} chars]`;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function isReadableResponseBody(response: Response): boolean {
  const resourceType = response.request().resourceType();
  if (!['document', 'fetch', 'xhr'].includes(resourceType)) return false;
  const contentType = response.headers()['content-type'] ?? '';
  return /json|text|html|plain|problem\+json/i.test(contentType);
}

function isObservedNetworkResource(resourceType: string): boolean {
  return ['document', 'fetch', 'xhr', 'websocket'].includes(resourceType);
}

export class BrowserLogObserver {
  readonly eventsPath: string;
  readonly summaryPath: string;

  private readonly eventCounts: Record<string, number> = {};
  private readonly recentErrors: BrowserEvent[] = [];
  private closed = false;

  constructor(
    private readonly page: Page,
    private readonly options: { runId: string; logsDir: string; testTitle: string },
  ) {
    mkdirSync(options.logsDir, { recursive: true });
    this.eventsPath = join(options.logsDir, 'browser-events.jsonl');
    this.summaryPath = join(options.logsDir, 'browser-summary.json');
    this.install();
    this.record('browser.observe_started', 'info', {
      test_title: options.testTitle,
      note: 'Streaming browser console, pageerror, network, and websocket events for agentic debugging.',
    });
  }

  finish(): BrowserObserverSummary {
    this.record('browser.observe_finished', 'info', { final_url: this.safePageUrl() });
    this.closed = true;
    const summary: BrowserObserverSummary = {
      schema_version: 1,
      run_id: this.options.runId,
      generated_at: new Date().toISOString(),
      event_counts: this.eventCounts,
      error_count: this.recentErrors.length,
      recent_errors: this.recentErrors.slice(-25),
      artifacts: {
        browser_events_jsonl: this.eventsPath,
        browser_summary_json: this.summaryPath,
      },
    };
    writeFileSync(this.summaryPath, JSON.stringify(summary, null, 2) + '\n');
    return summary;
  }

  private install(): void {
    this.page.on('console', (message) => this.onConsole(message));
    this.page.on('pageerror', (error) => this.record('browser.page_error', 'error', { message: errorMessage(error) }));
    this.page.on('request', (request) => this.onRequest(request));
    this.page.on('requestfailed', (request) => this.onRequestFailed(request));
    this.page.on('response', (response) => {
      void this.onResponse(response);
    });
    this.page.on('websocket', (socket) => this.onWebSocket(socket));
    this.page.on('crash', () => this.record('browser.page_crash', 'error', { message: 'Page crashed' }));
    this.page.on('framenavigated', (frame) => {
      if (frame === this.page.mainFrame()) {
        this.record('browser.navigation', 'info', { url: frame.url() });
      }
    });
  }

  private onConsole(message: ConsoleMessage): void {
    const level = message.type();
    const severity: Severity = level === 'error' ? 'error' : level === 'warning' ? 'warning' : 'info';
    this.record('browser.console', severity, {
      level,
      text: truncate(message.text()),
      location: message.location(),
    });
  }

  private onRequestFailed(request: Request): void {
    this.record('browser.request_failed', 'error', {
      method: request.method(),
      url: request.url(),
      resource_type: request.resourceType(),
      failure: request.failure()?.errorText ?? null,
    });
  }

  private onRequest(request: Request): void {
    if (!isObservedNetworkResource(request.resourceType())) return;
    this.record('browser.request', 'info', {
      method: request.method(),
      url: request.url(),
      resource_type: request.resourceType(),
    });
  }

  private async onResponse(response: Response): Promise<void> {
    if (response.status() < 400) {
      if (isObservedNetworkResource(response.request().resourceType())) {
        this.record('browser.response', 'info', {
          method: response.request().method(),
          url: response.url(),
          status: response.status(),
          resource_type: response.request().resourceType(),
          content_type: response.headers()['content-type'] ?? null,
        });
      }
      return;
    }
    const data: Record<string, unknown> = {
      method: response.request().method(),
      url: response.url(),
      status: response.status(),
      status_text: response.statusText(),
      resource_type: response.request().resourceType(),
      content_type: response.headers()['content-type'] ?? null,
    };

    if (isReadableResponseBody(response)) {
      try {
        data.body_preview = truncate(await response.text(), MAX_BODY_LENGTH);
      } catch (error) {
        data.body_error = errorMessage(error);
      }
    }

    this.record('browser.http_error', 'error', data);
  }

  private onWebSocket(socket: WebSocket): void {
    this.record('browser.websocket_open', 'info', { url: socket.url() });
    socket.on('framesent', (frame) => {
      this.record('browser.websocket_frame_sent', 'info', {
        url: socket.url(),
        payload: truncate(frame.payload, MAX_TEXT_LENGTH),
      });
    });
    socket.on('framereceived', (frame) => {
      this.record('browser.websocket_frame_received', 'info', {
        url: socket.url(),
        payload: truncate(frame.payload, MAX_TEXT_LENGTH),
      });
    });
    socket.on('close', () => this.record('browser.websocket_close', 'info', { url: socket.url() }));
  }

  private record(type: string, severity: Severity, data: Record<string, unknown>): void {
    if (this.closed) return;
    const event: BrowserEvent = {
      schema_version: 1,
      at: new Date().toISOString(),
      run_id: this.options.runId,
      type,
      severity,
      page_url: this.safePageUrl(),
      data,
    };
    this.eventCounts[type] = (this.eventCounts[type] ?? 0) + 1;
    if (severity === 'error') this.recentErrors.push(event);
    appendFileSync(this.eventsPath, JSON.stringify(event) + '\n');
  }

  private safePageUrl(): string {
    try {
      return this.page.url();
    } catch {
      return '';
    }
  }
}
