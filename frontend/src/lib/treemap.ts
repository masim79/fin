/**
 * Squarified treemap layout (Bruls, Huizing & van Wijk, 2000).
 *
 * Returns rectangles whose AREAS are exactly proportional to each item's
 * value, laid out to keep rectangles close to square. Coordinates are emitted
 * in the supplied coordinate space (default 100x100) so callers can position
 * with percentages and stay resolution-independent — no measured pixel size
 * and no ResizeObserver needed.
 */

export interface TreemapItem {
  ticker: string;
  value: number;
  pnlPct: number;
}

export interface TreemapRect extends TreemapItem {
  /** Portfolio weight, 0..1 */
  weight: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

interface ScaledItem extends TreemapItem {
  weight: number;
  area: number;
}

interface Frame {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** Worst (largest) aspect ratio in a row of the given total area. */
function worstAspect(row: ScaledItem[], rowArea: number, side: number): number {
  if (rowArea <= 0 || side <= 0) return Infinity;

  const thickness = rowArea / side;
  let worst = 1;

  for (const item of row) {
    const length = item.area / thickness;
    const ratio = length > 0 ? Math.max(length / thickness, thickness / length) : Infinity;
    if (ratio > worst) worst = ratio;
  }

  return worst;
}

function placeRow(row: ScaledItem[], rowArea: number, frame: Frame, out: TreemapRect[]): Frame {
  const horizontal = frame.w >= frame.h;
  const side = horizontal ? frame.h : frame.w;
  const thickness = side > 0 ? rowArea / side : 0;

  let offset = 0;
  for (const item of row) {
    const length = thickness > 0 ? item.area / thickness : 0;

    out.push({
      ticker: item.ticker,
      value: item.value,
      pnlPct: item.pnlPct,
      weight: item.weight,
      x: horizontal ? frame.x : frame.x + offset,
      y: horizontal ? frame.y + offset : frame.y,
      width: horizontal ? thickness : length,
      height: horizontal ? length : thickness,
    });

    offset += length;
  }

  // Remaining space after consuming this row's thickness
  return horizontal
    ? { x: frame.x + thickness, y: frame.y, w: frame.w - thickness, h: frame.h }
    : { x: frame.x, y: frame.y + thickness, w: frame.w, h: frame.h - thickness };
}

function layout(items: ScaledItem[], frame: Frame, out: TreemapRect[]): void {
  if (items.length === 0) return;

  if (items.length === 1) {
    const item = items[0];
    out.push({
      ticker: item.ticker,
      value: item.value,
      pnlPct: item.pnlPct,
      weight: item.weight,
      x: frame.x,
      y: frame.y,
      width: frame.w,
      height: frame.h,
    });
    return;
  }

  const side = Math.min(frame.w, frame.h);

  // Grow the current row while doing so improves the worst aspect ratio.
  const row: ScaledItem[] = [items[0]];
  let rowArea = items[0].area;
  let index = 1;

  while (index < items.length) {
    const next = items[index];
    const current = worstAspect(row, rowArea, side);
    const expanded = worstAspect([...row, next], rowArea + next.area, side);

    if (expanded > current) break;

    row.push(next);
    rowArea += next.area;
    index += 1;
  }

  const remaining = placeRow(row, rowArea, frame, out);
  layout(items.slice(index), remaining, out);
}

/**
 * Lay out `items` as a treemap. Items with a non-positive value are dropped.
 * Returns [] when nothing has positive value.
 */
export function squarify(items: TreemapItem[], width = 100, height = 100): TreemapRect[] {
  const positive = items.filter((i) => i.value > 0);
  const total = positive.reduce((sum, i) => sum + i.value, 0);

  if (total <= 0 || width <= 0 || height <= 0) return [];

  const scaled: ScaledItem[] = positive
    .map((item) => ({
      ...item,
      weight: item.value / total,
      area: (item.value / total) * width * height,
    }))
    .sort((a, b) => b.area - a.area);

  const out: TreemapRect[] = [];
  layout(scaled, { x: 0, y: 0, w: width, h: height }, out);
  return out;
}
