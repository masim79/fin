import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import PortfolioHeatmap from "@/components/PortfolioHeatmap";
import type { Position } from "@/lib/api";

function position(overrides: Partial<Position> & { ticker: string }): Position {
  const quantity = overrides.quantity ?? 10;
  const avgCost = overrides.avg_cost ?? 100;
  const currentPrice = overrides.current_price ?? 100;

  return {
    ticker: overrides.ticker,
    quantity,
    avg_cost: avgCost,
    current_price: currentPrice,
    unrealized_pnl: overrides.unrealized_pnl ?? (currentPrice - avgCost) * quantity,
    pnl_percent:
      overrides.pnl_percent ?? (avgCost > 0 ? ((currentPrice - avgCost) / avgCost) * 100 : 0),
  };
}

const tile = (ticker: string) => screen.getByTestId(`heatmap-tile-${ticker}`);

describe("PortfolioHeatmap", () => {
  it("shows an empty state with no positions", () => {
    render(<PortfolioHeatmap positions={[]} prices={{}} />);
    expect(screen.getByText("No positions")).toBeInTheDocument();
  });

  it("sizes tiles by portfolio weight (fin-9t8)", () => {
    render(
      <PortfolioHeatmap
        positions={[
          position({ ticker: "BIG", quantity: 75, current_price: 100 }),
          position({ ticker: "SMALL", quantity: 25, current_price: 100 }),
        ]}
        prices={{}}
      />,
    );

    expect(tile("BIG").dataset.weight).toBe("0.7500");
    expect(tile("SMALL").dataset.weight).toBe("0.2500");

    // Areas, read off the inline percentage geometry, keep the 3:1 ratio
    const area = (el: HTMLElement) =>
      parseFloat(el.style.width) * parseFloat(el.style.height);
    expect(area(tile("BIG")) / area(tile("SMALL"))).toBeCloseTo(3, 3);
  });

  it("does not inflate tiny positions to a minimum size", () => {
    render(
      <PortfolioHeatmap
        positions={[
          position({ ticker: "HUGE", quantity: 99, current_price: 100 }),
          position({ ticker: "TINY", quantity: 1, current_price: 100 }),
        ]}
        prices={{}}
      />,
    );

    expect(tile("TINY").dataset.weight).toBe("0.0100");
    const tinyArea =
      parseFloat(tile("TINY").style.width) * parseFloat(tile("TINY").style.height);
    const hugeArea =
      parseFloat(tile("HUGE").style.width) * parseFloat(tile("HUGE").style.height);
    expect(hugeArea / tinyArea).toBeCloseTo(99, 1);
  });

  it("colors gainers green and losers red", () => {
    render(
      <PortfolioHeatmap
        positions={[
          position({ ticker: "WIN", avg_cost: 100, current_price: 110, quantity: 10 }),
          position({ ticker: "LOSS", avg_cost: 100, current_price: 90, quantity: 10 }),
        ]}
        prices={{}}
      />,
    );

    expect(tile("WIN").style.backgroundColor).toContain("63, 185, 80");
    expect(tile("LOSS").style.backgroundColor).toContain("248, 81, 73");
  });

  it("scales color intensity with the size of the move", () => {
    const { rerender } = render(
      <PortfolioHeatmap
        positions={[position({ ticker: "A", avg_cost: 100, current_price: 101 })]}
        prices={{}}
      />,
    );
    const alphaOf = (el: HTMLElement) =>
      parseFloat(el.style.backgroundColor.split(",")[3]);
    const small = alphaOf(tile("A"));

    rerender(
      <PortfolioHeatmap
        positions={[position({ ticker: "A", avg_cost: 100, current_price: 120 })]}
        prices={{}}
      />,
    );
    expect(alphaOf(tile("A"))).toBeGreaterThan(small);
  });

  it("prefers the live streamed price over the snapshot price", () => {
    render(
      <PortfolioHeatmap
        positions={[position({ ticker: "AAPL", avg_cost: 100, current_price: 100 })]}
        prices={{
          AAPL: {
            ticker: "AAPL",
            price: 150,
            previous_price: 100,
            direction: "up",
            timestamp: "",
          },
        }}
      />,
    );

    // +50% off avg_cost => green, and the tooltip reflects the live price
    expect(tile("AAPL").style.backgroundColor).toContain("63, 185, 80");
    expect(tile("AAPL").getAttribute("title")).toContain("+50.00%");
  });

  it("lays tiles out without overlapping", () => {
    render(
      <PortfolioHeatmap
        positions={[
          position({ ticker: "A", quantity: 40 }),
          position({ ticker: "B", quantity: 30 }),
          position({ ticker: "C", quantity: 20 }),
          position({ ticker: "D", quantity: 10 }),
        ]}
        prices={{}}
      />,
    );

    const rects = ["A", "B", "C", "D"].map((t) => {
      const el = tile(t);
      return {
        x: parseFloat(el.style.left),
        y: parseFloat(el.style.top),
        w: parseFloat(el.style.width),
        h: parseFloat(el.style.height),
      };
    });

    for (let i = 0; i < rects.length; i++) {
      for (let j = i + 1; j < rects.length; j++) {
        const a = rects[i];
        const b = rects[j];
        const ox = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x));
        const oy = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
        expect(ox * oy).toBeLessThan(0.01);
      }
    }
  });

  it("skips positions with no value instead of drawing empty tiles", () => {
    render(
      <PortfolioHeatmap
        positions={[
          position({ ticker: "REAL", quantity: 10, current_price: 100 }),
          position({ ticker: "ZERO", quantity: 0, current_price: 100 }),
        ]}
        prices={{}}
      />,
    );

    expect(screen.getByTestId("heatmap-tile-REAL")).toBeInTheDocument();
    expect(screen.queryByTestId("heatmap-tile-ZERO")).not.toBeInTheDocument();
  });
});
