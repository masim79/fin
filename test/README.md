# E2E Tests

Playwright coverage of the seven scenarios in
[`planning/PLAN.md`](../planning/PLAN.md) section 12.

## Run

One command, from this directory:

```bash
docker compose -f docker-compose.test.yml up --build \
  --abort-on-container-exit --exit-code-from playwright
```

That builds the production image, waits for `/api/health`, then runs the suite
in a Playwright container. The exit code is the suite's. Tear down with:

```bash
docker compose -f docker-compose.test.yml down
```

The browser dependencies live in the Playwright container, so they stay out of
the production image — which is why this compose file is here and not at the
repo root.

### Against an app you are already running

```bash
npm ci
BASE_URL=http://localhost:8000 npx playwright test
```

The app must have been started with `LLM_MOCK=true` and `E2E_TEST_MODE=true`.

## Environment

| Variable | Value | Why |
|---|---|---|
| `LLM_MOCK` | `true` | Deterministic chat replies, no API key, no network. |
| `MASSIVE_API_KEY` | empty | Forces the built-in simulator, so the ticker set is known. |
| `E2E_TEST_MODE` | `true` | Exposes `POST /api/test/reset`. |
| `DB_PATH` | `/tmp/test.db` | Throwaway, no volume — every run starts clean. |

## Test isolation

FinAlly is single-user with server-side state, so tests cannot run in
parallel against one container and cannot inherit each other's portfolios —
otherwise no test could assert the $10,000 opening balance. Therefore:

- `playwright.config.ts` sets `workers: 1` and `fullyParallel: false`.
- `beforeEach` calls `POST /api/test/reset`, which truncates the tables and
  re-seeds the default profile and watchlist.

That endpoint is mounted **only** when `E2E_TEST_MODE=true`
(`backend/app/testsupport.py`); in a normal run the route does not exist and
returns 404. `backend/tests/test_health.py` guards that.

## Coverage

| PLAN.md section 12 scenario | Tests |
|---|---|
| 1. Fresh start: watchlist, $10k, streaming | `Fresh start` (2) |
| 2. Add and remove a watchlist ticker | `Watchlist CRUD` (2) |
| 3. Buy shares | `Trading › buying...` |
| 4. Sell shares | `Trading › selling...`, plus a rejected sell |
| 5. Heatmap colors, P&L data points | `Portfolio visualization` (2) |
| 6. AI chat with inline trade execution | `AI Chat` (4) |
| 7. SSE disconnect and reconnect | `SSE resilience` |
| — Persistence across reload (fin-om1.2) | `Persistence` |

Scenario 2 also guards `fin-dxo` by adding a ticker outside the seeded ten and
asserting it receives a real streaming price rather than staying on `--`.
Scenario 5 asserts tiles are area-proportional to portfolio weight
(`fin-9t8`), not merely that a panel exists.
