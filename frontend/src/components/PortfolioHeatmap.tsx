"use client";

import type { Position } from "@/lib/api";
import type { PriceMap } from "@/hooks/useMarketData";
import { squarify, type TreemapItem } from "@/lib/treemap";

interface PortfolioHeatmapProps {
  positions: Position[];
  prices: PriceMap;
}

/** P&L percent at which the fill reaches full saturation. */
const FULL_SCALE_PCT = 5;

function fillFor(pnlPct: number): string {
  const intensity = Math.min(Math.abs(pnlPct) / FULL_SCALE_PCT, 1);
  const alpha = 0.18 + intensity * 0.62;
  return pnlPct >= 0
    ? `rgba(63, 185, 80, ${alpha.toFixed(3)})`
    : `rgba(248, 81, 73, ${alpha.toFixed(3)})`;
}

export default function PortfolioHeatmap({ positions, prices }: PortfolioHeatmapProps) {
  const items: TreemapItem[] = positions.map((pos) => {
    const livePrice = prices[pos.ticker]?.price ?? pos.current_price;
    return {
      ticker: pos.ticker,
      value: Math.abs(livePrice * pos.quantity),
      pnlPct: pos.avg_cost > 0 ? ((livePrice - pos.avg_cost) / pos.avg_cost) * 100 : 0,
    };
  });

  const rects = squarify(items);

  if (rects.length === 0) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-text-secondary">
        No positions
      </div>
    );
  }

  return (
    <div className="relative h-full w-full overflow-hidden" data-testid="portfolio-heatmap">
      {rects.map((rect) => {
        // Hide labels in tiles too small to read them.
        const showTicker = rect.width > 9 && rect.height > 7;
        const showPnl = rect.width > 13 && rect.height > 13;

        return (
          <div
            key={rect.ticker}
            data-testid={`heatmap-tile-${rect.ticker}`}
            data-weight={rect.weight.toFixed(4)}
            title={`${rect.ticker} — ${(rect.weight * 100).toFixed(1)}% of portfolio, ${
              rect.pnlPct >= 0 ? "+" : ""
            }${rect.pnlPct.toFixed(2)}%`}
            style={{
              position: "absolute",
              left: `${rect.x}%`,
              top: `${rect.y}%`,
              width: `${rect.width}%`,
              height: `${rect.height}%`,
              backgroundColor: fillFor(rect.pnlPct),
            }}
            className="flex flex-col items-center justify-center overflow-hidden rounded-sm border border-bg-primary/60 px-0.5"
          >
            {showTicker && (
              <span className="truncate text-[10px] font-bold leading-tight text-text-primary">
                {rect.ticker}
              </span>
            )}
            {showPnl && (
              <span
                className={`text-[9px] leading-tight ${
                  rect.pnlPct >= 0 ? "text-green" : "text-red"
                }`}
              >
                {rect.pnlPct >= 0 ? "+" : ""}
                {rect.pnlPct.toFixed(1)}%
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
