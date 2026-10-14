import { test, expect, type Page } from "@playwright/test";

/**
 * E2E coverage of the seven scenarios in PLAN.md section 12.
 *
 * Runs against the container built by docker-compose.test.yml with
 * LLM_MOCK=true and the market simulator, so chat replies and the ticker
 * universe are deterministic.
 */

/** Parse "$10,000.00" into 10000. */
function money(text: string | null): number {
  if (!text) return NaN;
  return parseFloat(text.replace(/[$,\s]/g, ""));
}

async function cash(page: Page): Promise<number> {
  return money(await page.getByTestId("cash-balance").textContent());
}

async function portfolioValue(page: Page): Promise<number> {
  return money(await page.getByTestId("portfolio-value").textContent());
}

/** Wait until the SSE stream is live and at least one price has arrived. */
async function waitForPrices(page: Page): Promise<void> {
  await expect(page.getByTestId("connection-status")).toHaveText("connected", {
    timeout: 15_000,
  });
  await expect(page.locator("td.tabular-nums").first()).not.toHaveText("--", {
    timeout: 15_000,
  });
}

/**
 * Reset server state to the seeded baseline.
 *
 * The app is single-user with server-side state, so without this every test
 * would inherit the previous one's portfolio and could not assert the concrete
 * values PLAN.md section 12 specifies. Backed by the E2E_TEST_MODE-gated
 * endpoint, which exists only in the test container.
 */
async function resetState(page: Page): Promise<void> {
  const response = await page.request.post("/api/test/reset");
  expect(
    response.ok(),
    "POST /api/test/reset failed — is E2E_TEST_MODE=true set on the app container?",
  ).toBeTruthy();
}

test.beforeEach(async ({ page }) => {
  await resetState(page);
});

async function trade(page: Page, ticker: string, qty: number, side: "BUY" | "SELL") {
  await page.getByPlaceholder("Ticker").fill(ticker);
  await page.getByPlaceholder("Qty").fill(String(qty));
  await page.getByRole("button", { name: side, exact: true }).click();
}

// ---------------------------------------------------------------------------
// 1. Fresh start
// ---------------------------------------------------------------------------

test.describe("Fresh start", () => {
  test("shows the default watchlist, $10k balance and streaming prices", async ({
    page,
  }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { level: 1 })).toContainText("FinAlly");
    await expect(page.getByTestId("cash-balance")).toHaveText("$10,000.00");

    // All ten seeded tickers are present
    for (const ticker of [
      "AAPL",
      "GOOGL",
      "MSFT",
      "AMZN",
      "TSLA",
      "NVDA",
      "META",
      "JPM",
      "V",
      "NFLX",
    ]) {
      await expect(
        page.locator("tr", { hasText: new RegExp(`\\b${ticker}\\b`) }).first(),
      ).toBeVisible();
    }

    await waitForPrices(page);
  });

  test("prices actually move while the stream is open", async ({ page }) => {
    await page.goto("/");
    await waitForPrices(page);

    const cell = page.locator("td.tabular-nums").first();
    const first = await cell.textContent();

    // The simulator ticks ~every 500ms
    await expect(cell).not.toHaveText(first ?? "", { timeout: 15_000 });
  });
});

// ---------------------------------------------------------------------------
// 2. Watchlist add / remove
// ---------------------------------------------------------------------------

test.describe("Watchlist CRUD", () => {
  test("adds a ticker outside the seeded set and streams a price for it", async ({
    page,
  }) => {
    await page.goto("/");
    await waitForPrices(page);

    const input = page.getByPlaceholder("Add ticker");
    await input.fill("SNAP");
    await input.press("Enter");

    const row = page.locator("tr", { hasText: /\bSNAP\b/ });
    await expect(row).toBeVisible({ timeout: 10_000 });

    // Regression guard for fin-dxo: a non-seeded ticker must get a real price,
    // not stay stuck on the "--" placeholder.
    await expect(row.locator("td.tabular-nums").first()).not.toHaveText("--", {
      timeout: 15_000,
    });
  });

  test("removes a ticker", async ({ page }) => {
    await page.goto("/");
    await waitForPrices(page);

    const input = page.getByPlaceholder("Add ticker");
    await input.fill("SHOP");
    await input.press("Enter");

    const row = page.locator("tr", { hasText: /\bSHOP\b/ });
    await expect(row).toBeVisible({ timeout: 10_000 });

    await row.getByTitle("Remove").click();
    await expect(row).toHaveCount(0, { timeout: 10_000 });
  });
});

// ---------------------------------------------------------------------------
// 3 & 4. Buying and selling
// ---------------------------------------------------------------------------

test.describe("Trading", () => {
  test("buying reduces cash and creates a position", async ({ page }) => {
    await page.goto("/");
    await waitForPrices(page);

    const cashBefore = await cash(page);
    expect(cashBefore).toBeGreaterThan(0);

    await trade(page, "AAPL", 5, "BUY");

    const row = page.getByTestId("position-row-AAPL");
    await expect(row).toBeVisible({ timeout: 10_000 });
    await expect(row).toContainText("5");

    await expect
      .poll(() => cash(page), { timeout: 10_000 })
      .toBeLessThan(cashBefore);

    // Cash fell by a real market amount, not by some constant
    const spent = cashBefore - (await cash(page));
    expect(spent).toBeGreaterThan(0);

    await expect
      .poll(() => portfolioValue(page), { timeout: 10_000 })
      .toBeGreaterThan(0);
  });

  test("selling returns cash and clears the position", async ({ page }) => {
    await page.goto("/");
    await waitForPrices(page);

    await trade(page, "MSFT", 3, "BUY");
    await expect(page.getByTestId("position-row-MSFT")).toBeVisible({
      timeout: 10_000,
    });

    const cashAfterBuy = await cash(page);

    await trade(page, "MSFT", 3, "SELL");

    // Position fully closed, so the row disappears
    await expect(page.getByTestId("position-row-MSFT")).toHaveCount(0, {
      timeout: 10_000,
    });
    await expect
      .poll(() => cash(page), { timeout: 10_000 })
      .toBeGreaterThan(cashAfterBuy);
  });

  test("rejects a sell with no shares held", async ({ page }) => {
    await page.goto("/");
    await waitForPrices(page);

    const cashBefore = await cash(page);
    await trade(page, "NVDA", 1, "SELL");

    await expect(page.getByText(/insufficient/i)).toBeVisible({ timeout: 10_000 });
    expect(await cash(page)).toBeCloseTo(cashBefore, 2);
  });
});

// ---------------------------------------------------------------------------
// 5. Portfolio visualization
// ---------------------------------------------------------------------------

test.describe("Portfolio visualization", () => {
  test("heatmap sizes tiles by weight and colors them by P&L", async ({ page }) => {
    await page.goto("/");
    await waitForPrices(page);

    await expect(page.getByTestId("portfolio-heatmap")).toHaveCount(0);

    // Two positions of deliberately different weight
    await trade(page, "NVDA", 10, "BUY"); // ~$880 each — the larger weight
    await expect(page.getByTestId("position-row-NVDA")).toBeVisible({
      timeout: 10_000,
    });
    await trade(page, "JPM", 2, "BUY"); // ~$195 each — the smaller weight
    await expect(page.getByTestId("position-row-JPM")).toBeVisible({
      timeout: 10_000,
    });

    const heatmap = page.getByTestId("portfolio-heatmap");
    await expect(heatmap).toBeVisible({ timeout: 10_000 });

    const big = page.getByTestId("heatmap-tile-NVDA");
    const small = page.getByTestId("heatmap-tile-JPM");
    await expect(big).toBeVisible();
    await expect(small).toBeVisible();

    // Sized by portfolio weight (fin-9t8)
    const bigWeight = parseFloat((await big.getAttribute("data-weight")) ?? "0");
    const smallWeight = parseFloat((await small.getAttribute("data-weight")) ?? "0");
    expect(bigWeight).toBeGreaterThan(smallWeight);
    expect(bigWeight + smallWeight).toBeCloseTo(1, 2);

    // Rendered area follows the weight
    const bigBox = await big.boundingBox();
    const smallBox = await small.boundingBox();
    expect(bigBox!.width * bigBox!.height).toBeGreaterThan(
      smallBox!.width * smallBox!.height,
    );

    // Colored by P&L: green when up, red when down — never uncolored
    for (const tile of [big, small]) {
      const bg = await tile.evaluate((el) => getComputedStyle(el).backgroundColor);
      const [r, g, b] = bg.match(/\d+/g)!.map(Number);
      const isGain = g > r && g > b;
      const isLoss = r > g && r > b;
      expect(isGain || isLoss).toBe(true);
    }
  });

  test("P&L chart plots real data points", async ({ page }) => {
    await page.goto("/");
    await waitForPrices(page);

    // A trade forces an immediate snapshot, so the series is never empty
    await trade(page, "AAPL", 1, "BUY");
    await expect(page.getByTestId("position-row-AAPL")).toBeVisible({
      timeout: 10_000,
    });

    const chart = page.getByTestId("pnl-chart");
    await expect(chart).toBeVisible();

    await expect
      .poll(
        async () =>
          parseInt((await chart.getAttribute("data-point-count")) ?? "0", 10),
        { timeout: 40_000 },
      )
      .toBeGreaterThan(0);

    // And the line is actually drawn
    await expect(chart.locator("svg path").first()).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 6. AI chat (mocked)
// ---------------------------------------------------------------------------

test.describe("AI Chat", () => {
  test("answers a message", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByText("AI Chat")).toBeVisible();
    await expect(
      page.getByText("Ask about stocks, trade, or manage your watchlist."),
    ).toBeVisible();

    const input = page.getByPlaceholder("Message...");
    await input.fill("hello");
    await page.getByRole("button", { name: "Send" }).click();

    await expect(page.getByText("hello", { exact: true })).toBeVisible();
    // LLM_MOCK greeting
    await expect(
      page.getByText(/FinAlly, your AI trading assistant/),
    ).toBeVisible({ timeout: 20_000 });
  });

  test("executes a trade requested in chat and shows it inline", async ({ page }) => {
    await page.goto("/");
    await waitForPrices(page);

    const cashBefore = await cash(page);

    const input = page.getByPlaceholder("Message...");
    await input.fill("buy some TSLA");
    await page.getByRole("button", { name: "Send" }).click();

    // Confirmation in the conversation
    await expect(page.getByText(/Buying 10 shares of TSLA/)).toBeVisible({
      timeout: 20_000,
    });

    // And the trade really happened, at the live price (fin-b64)
    await expect(page.getByTestId("position-row-TSLA")).toBeVisible({
      timeout: 15_000,
    });
    await expect
      .poll(() => cash(page), { timeout: 15_000 })
      .toBeLessThan(cashBefore);
  });

  test("applies a watchlist change requested in chat", async ({ page }) => {
    await page.goto("/");
    await waitForPrices(page);

    const input = page.getByPlaceholder("Message...");
    await input.fill("add PYPL to my watchlist");
    await page.getByRole("button", { name: "Send" }).click();

    await expect(page.getByText(/Adding PYPL to your watchlist/)).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.locator("tr", { hasText: /\bPYPL\b/ })).toBeVisible({
      timeout: 15_000,
    });
  });

  test("collapses and expands", async ({ page }) => {
    await page.goto("/");

    await page.getByLabel("Collapse chat").click();
    await expect(page.getByText("AI Chat")).not.toBeVisible();

    await page.getByLabel("Expand chat").click();
    await expect(page.getByText("AI Chat")).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// 7. SSE resilience
// ---------------------------------------------------------------------------

test.describe("SSE resilience", () => {
  test("reports reconnecting on disconnect, then recovers", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByTestId("connection-status")).toHaveText("connected", {
      timeout: 15_000,
    });

    // Kill the stream
    await page.route("**/api/stream/prices", (route) => route.abort());
    await expect(page.getByTestId("connection-status")).toHaveText("reconnecting", {
      timeout: 20_000,
    });

    // Let EventSource's built-in retry succeed again
    await page.unroute("**/api/stream/prices");
    await expect(page.getByTestId("connection-status")).toHaveText("connected", {
      timeout: 30_000,
    });
  });
});

// ---------------------------------------------------------------------------
// Persistence (fin-om1.2) — state is server-side, so a reload must keep it
// ---------------------------------------------------------------------------

test.describe("Persistence", () => {
  test("positions and cash survive a page reload", async ({ page }) => {
    await page.goto("/");
    await waitForPrices(page);

    await trade(page, "AMZN", 4, "BUY");
    await expect(page.getByTestId("position-row-AMZN")).toBeVisible({
      timeout: 10_000,
    });
    const cashAfterBuy = await cash(page);

    await page.reload();
    await waitForPrices(page);

    await expect(page.getByTestId("position-row-AMZN")).toBeVisible({
      timeout: 10_000,
    });
    expect(await cash(page)).toBeCloseTo(cashAfterBuy, 2);
  });
});
