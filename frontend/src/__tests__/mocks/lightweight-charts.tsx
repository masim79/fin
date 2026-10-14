/**
 * Shared stub for lightweight-charts.
 *
 * The real library draws to a canvas that jsdom cannot provide, so every test
 * run needs this. It is registered globally in setup.ts — keep the exported
 * surface in step with what the components import (v5 API: createChart(...)
 * .addSeries(SeriesDefinition, options), not the v4 chart.addLineSeries()).
 */

import { vi } from "vitest";

export const ColorType = { Solid: 0, VerticalGradient: 1 } as const;
export const LineType = { Simple: 0, WithSteps: 1, Curved: 2 } as const;
export const LineStyle = { Solid: 0, Dotted: 1, Dashed: 2 } as const;

// v5 series definitions. Identity is all that matters to the stub.
export const LineSeries = { type: "Line" } as const;
export const AreaSeries = { type: "Area" } as const;
export const CandlestickSeries = { type: "Candlestick" } as const;
export const HistogramSeries = { type: "Histogram" } as const;
export const BaselineSeries = { type: "Baseline" } as const;
export const BarSeries = { type: "Bar" } as const;

export function createSeriesStub() {
  return {
    setData: vi.fn(),
    update: vi.fn(),
    applyOptions: vi.fn(),
    setMarkers: vi.fn(),
    priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
  };
}

export function createChartStub() {
  return {
    addSeries: vi.fn(() => createSeriesStub()),
    // Keep the v4 helpers so a stray old call fails loudly in the component,
    // not silently inside the mock.
    timeScale: vi.fn(() => ({
      fitContent: vi.fn(),
      setVisibleLogicalRange: vi.fn(),
      applyOptions: vi.fn(),
    })),
    priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
    applyOptions: vi.fn(),
    resize: vi.fn(),
    remove: vi.fn(),
    subscribeCrosshairMove: vi.fn(),
    unsubscribeCrosshairMove: vi.fn(),
  };
}

export const createChart = vi.fn(() => createChartStub());
