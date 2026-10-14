import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Chart libraries need stubbing in jsdom: lightweight-charts draws to a canvas
// jsdom does not provide, and recharts' ResponsiveContainer measures a parent
// that is always 0x0. Registered once here rather than per test file so an
// upstream API change breaks one place. See ./mocks/.
vi.mock("lightweight-charts", () => import("./mocks/lightweight-charts"));
vi.mock("recharts", () => import("./mocks/recharts"));

/**
 * EventSource stub for useMarketData.
 *
 * The hook subscribes with addEventListener("price", ...) for named SSE events
 * and also sets onopen/onerror, so all three paths must work. Tests can reach
 * the live instance via MockEventSource.last to push events or force an error.
 */
export class MockEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;

  /** Most recently constructed instance, for tests to drive. */
  static last: MockEventSource | null = null;
  static instances: MockEventSource[] = [];

  readonly CONNECTING = MockEventSource.CONNECTING;
  readonly OPEN = MockEventSource.OPEN;
  readonly CLOSED = MockEventSource.CLOSED;

  url: string;
  readyState: number = MockEventSource.CONNECTING;
  withCredentials = false;

  onopen: ((e: Event) => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: ((e: Event) => void) | null = null;

  private listeners = new Map<string, Set<EventListener>>();

  constructor(url: string) {
    this.url = url;
    MockEventSource.last = this;
    MockEventSource.instances.push(this);

    // Open on a later tick, as a real connection would.
    setTimeout(() => {
      if (this.readyState === MockEventSource.CLOSED) return;
      this.readyState = MockEventSource.OPEN;
      this.onopen?.(new Event("open"));
      this.dispatch("open", new Event("open"));
    }, 0);
  }

  addEventListener(type: string, listener: EventListener): void {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(listener);
  }

  removeEventListener(type: string, listener: EventListener): void {
    this.listeners.get(type)?.delete(listener);
  }

  dispatchEvent(event: Event): boolean {
    this.dispatch(event.type, event);
    return true;
  }

  close = vi.fn(() => {
    this.readyState = MockEventSource.CLOSED;
  });

  /** Emit a named SSE event carrying `data` as a JSON string. */
  emit(type: string, data: unknown): void {
    const event = new MessageEvent(type, { data: JSON.stringify(data) });
    this.dispatch(type, event);
    if (type === "message") this.onmessage?.(event);
  }

  /** Simulate a transport error. */
  fail(): void {
    const event = new Event("error");
    this.onerror?.(event);
    this.dispatch("error", event);
  }

  private dispatch(type: string, event: Event): void {
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event);
    }
  }
}

vi.stubGlobal("EventSource", MockEventSource);

afterEach(() => {
  cleanup();
  MockEventSource.last = null;
  MockEventSource.instances = [];
});

// jsdom doesn't implement scrollTo
Element.prototype.scrollTo = () => {};

/**
 * ResizeObserver stub — jsdom has no layout engine, so it ships none.
 * MainChart observes its container to resize the chart. Tests can trigger a
 * resize via MockResizeObserver.last?.trigger().
 */
export class MockResizeObserver {
  static last: MockResizeObserver | null = null;

  private callback: ResizeObserverCallback;
  observed: Element[] = [];

  observe = vi.fn((target: Element) => {
    this.observed.push(target);
  });
  unobserve = vi.fn();
  disconnect = vi.fn();

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
    MockResizeObserver.last = this;
  }

  /** Invoke the callback as a real observer would on a size change. */
  trigger(): void {
    const entries = this.observed.map(
      (target) => ({ target, contentRect: target.getBoundingClientRect() }) as ResizeObserverEntry,
    );
    this.callback(entries, this as unknown as ResizeObserver);
  }
}

vi.stubGlobal("ResizeObserver", MockResizeObserver);
