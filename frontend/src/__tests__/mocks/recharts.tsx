/**
 * Shared stub for recharts.
 *
 * ResponsiveContainer measures its parent, which is always 0x0 in jsdom, so
 * the real components render nothing and assertions cannot see the chart.
 * These passthroughs keep children in the tree. Registered in setup.ts.
 */

import type { ReactNode } from "react";

export const ResponsiveContainer = ({ children }: { children: ReactNode }) => (
  <div data-testid="responsive-container">{children}</div>
);
export const LineChart = ({ children }: { children: ReactNode }) => (
  <svg data-testid="line-chart">{children}</svg>
);
export const AreaChart = ({ children }: { children: ReactNode }) => (
  <svg data-testid="area-chart">{children}</svg>
);
export const Line = () => null;
export const Area = () => null;
export const XAxis = () => null;
export const YAxis = () => null;
export const CartesianGrid = () => null;
export const Tooltip = () => null;
export const Legend = () => null;
export const ReferenceLine = () => null;
