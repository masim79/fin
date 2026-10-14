import { describe, it, expect } from "vitest";
import { squarify, type TreemapItem } from "@/lib/treemap";

const item = (ticker: string, value: number, pnlPct = 0): TreemapItem => ({
  ticker,
  value,
  pnlPct,
});

describe("squarify", () => {
  it("returns no rectangles for an empty portfolio", () => {
    expect(squarify([])).toEqual([]);
  });

  it("gives a single position the whole canvas", () => {
    const [rect] = squarify([item("AAPL", 1000)]);
    expect(rect).toMatchObject({ x: 0, y: 0, width: 100, height: 100, weight: 1 });
  });

  it("sizes tiles by AREA in proportion to value (fin-9t8)", () => {
    const rects = squarify([item("BIG", 750), item("SMALL", 250)]);

    const big = rects.find((r) => r.ticker === "BIG")!;
    const small = rects.find((r) => r.ticker === "SMALL")!;

    const bigArea = big.width * big.height;
    const smallArea = small.width * small.height;

    expect(bigArea / smallArea).toBeCloseTo(3, 4);
    expect(big.weight).toBeCloseTo(0.75, 6);
    expect(small.weight).toBeCloseTo(0.25, 6);
  });

  it("does not apply a minimum size that would distort small positions", () => {
    // The old implementation floored flexBasis at 15%, so a 1% position
    // occupied the same space as a 15% one.
    const rects = squarify([item("HUGE", 99), item("TINY", 1)]);

    const huge = rects.find((r) => r.ticker === "HUGE")!;
    const tiny = rects.find((r) => r.ticker === "TINY")!;

    const ratio = (huge.width * huge.height) / (tiny.width * tiny.height);
    expect(ratio).toBeCloseTo(99, 2);
  });

  it("covers the full canvas area with no overlap", () => {
    const rects = squarify([
      item("A", 400),
      item("B", 300),
      item("C", 200),
      item("D", 70),
      item("E", 30),
    ]);

    const covered = rects.reduce((sum, r) => sum + r.width * r.height, 0);
    expect(covered).toBeCloseTo(100 * 100, 2);

    // Pairwise overlap check
    for (let i = 0; i < rects.length; i++) {
      for (let j = i + 1; j < rects.length; j++) {
        const a = rects[i];
        const b = rects[j];
        const overlapX = Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x));
        const overlapY = Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y));
        expect(overlapX * overlapY).toBeCloseTo(0, 6);
      }
    }
  });

  it("keeps every rectangle inside the canvas", () => {
    const rects = squarify([item("A", 50), item("B", 25), item("C", 15), item("D", 10)]);

    for (const r of rects) {
      expect(r.x).toBeGreaterThanOrEqual(-1e-6);
      expect(r.y).toBeGreaterThanOrEqual(-1e-6);
      expect(r.x + r.width).toBeLessThanOrEqual(100 + 1e-6);
      expect(r.y + r.height).toBeLessThanOrEqual(100 + 1e-6);
    }
  });

  it("orders tiles largest first", () => {
    const rects = squarify([item("S", 10), item("L", 100), item("M", 50)]);
    expect(rects.map((r) => r.ticker)).toEqual(["L", "M", "S"]);
  });

  it("drops non-positive values rather than emitting inverted tiles", () => {
    const rects = squarify([item("GOOD", 100), item("ZERO", 0), item("NEG", -50)]);
    expect(rects.map((r) => r.ticker)).toEqual(["GOOD"]);
  });

  it("produces reasonably square tiles for an even split", () => {
    const rects = squarify([item("A", 25), item("B", 25), item("C", 25), item("D", 25)]);

    for (const r of rects) {
      const aspect = Math.max(r.width / r.height, r.height / r.width);
      expect(aspect).toBeLessThan(2);
    }
  });

  it("honours a custom coordinate space", () => {
    const [rect] = squarify([item("AAPL", 10)], 200, 50);
    expect(rect.width).toBeCloseTo(200, 6);
    expect(rect.height).toBeCloseTo(50, 6);
  });

  it("carries pnlPct through untouched", () => {
    const rects = squarify([item("UP", 60, 4.2), item("DOWN", 40, -1.5)]);
    expect(rects.find((r) => r.ticker === "UP")!.pnlPct).toBe(4.2);
    expect(rects.find((r) => r.ticker === "DOWN")!.pnlPct).toBe(-1.5);
  });
});
