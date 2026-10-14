# FinAlly — Frontend/Backend Contract

The boundary between `frontend/` and `backend/`, **as actually implemented**.
`planning/PLAN.md` is the specification; this file records what the code does
today so agents do not have to reverse-engineer it from source.

All paths are same-origin (`/api/*`). There is no CORS configuration and no
auth. Every table carries a `user_id` that is hardcoded to `"default"`.

> **Authority:** where this file and PLAN.md disagree, **PLAN.md is
> authoritative** and the difference is a bug. Known differences are listed
> under [Known divergences](#known-divergences).

---

## Shared shapes

### `PriceUpdate`
Emitted by the SSE stream. Source: `backend/app/market/models.py`.

```json
{
  "ticker": "AAPL",
  "price": 191.25,
  "previous_price": 190.00,
  "timestamp": "2026-01-01T00:00:00.000000+00:00",
  "direction": "up"
}
```

- `direction` is `"up" | "down" | "flat"`, computed against the previous
  cached price.
- `price` and `previous_price` are rounded to 2 decimals.
- `timestamp` is an ISO-8601 UTC string.

### `Position`
Source: `backend/app/portfolio.py`.

```json
{
  "ticker": "AAPL",
  "quantity": 10.0,
  "avg_cost": 190.00,
  "current_price": 191.25,
  "unrealized_pnl": 12.50,
  "pnl_percent": 0.66
}
```

- The field is **`pnl_percent`**, not `pnl_pct`. The frontend mirror is
  `frontend/src/lib/api.ts`.
- `quantity` is a float — fractional shares are supported.

---

## Market data

### `GET /api/stream/prices`
Server-Sent Events. The client uses the native `EventSource`, which handles
reconnection on its own.

- Events are **named `price`**, so clients must use
  `addEventListener("price", ...)`. An `onmessage` handler alone receives
  nothing.
- `data` is a JSON-encoded `PriceUpdate`.
- One event per known ticker, re-emitted every ~500ms.
- "Known tickers" means everything in the in-memory price cache: the ten
  seeded defaults, plus anything added to the watchlist, plus anything the
  portfolio still holds.

```
event: price
data: {"ticker":"AAPL","price":191.25,"previous_price":190.0,"timestamp":"...","direction":"up"}
```

Sparklines are accumulated client-side from this stream since page load; the
backend serves no historical price series.

---

## Portfolio

### `GET /api/portfolio`
```json
{
  "cash_balance": 8500.00,
  "total_value": 10012.50,
  "positions": [ /* Position */ ]
}
```
`total_value` is cash plus the live market value of all positions.

### `POST /api/portfolio/trade`
Request:
```json
{ "ticker": "AAPL", "quantity": 10, "side": "buy" }
```
Response `200`:
```json
{
  "id": "uuid",
  "ticker": "AAPL",
  "side": "buy",
  "quantity": 10.0,
  "price": 191.25,
  "executed_at": "2026-01-01T00:00:00+00:00"
}
```
`400` with `{"detail": "..."}` when:

| Condition | Detail |
|---|---|
| `side` not `buy`/`sell` | `side must be 'buy' or 'sell'` |
| `quantity <= 0` | `quantity must be positive` |
| ticker has no cached price | `No price available for {ticker}` |
| buy exceeds cash | `Insufficient cash: need $X, have $Y` |
| sell exceeds holdings | `Insufficient shares: want to sell X, hold Y` |

Market orders only: instant fill at the current cached price, no fees, no
partial fills. Selling the full quantity deletes the position row. A
portfolio snapshot is recorded immediately after every fill.

**Both the REST route and the LLM chat auto-executor call the same
`portfolio.perform_trade()`**, so they fill at the same price and enforce the
same validation. It raises `TradeError`; the route maps that to a `400`, chat
maps it to text appended to the assistant message.

### `GET /api/portfolio/history`
```json
[ { "total_value": 10000.0, "recorded_at": "2026-01-01T00:00:00+00:00" } ]
```
Ascending by `recorded_at`. Written every 30s by a background task and after
each trade.

---

## Watchlist

### `GET /api/watchlist`
```json
[
  {
    "ticker": "AAPL",
    "price": 191.25,
    "previous_price": 190.00,
    "change_percent": 0.66
  }
]
```
All three price fields are `null` until the ticker has a cached price.

### `POST /api/watchlist`
Request `{ "ticker": "PYPL" }` → `200` with a single `WatchlistItem`.

- Ticker is upper-cased and trimmed.
- `400` if empty, `409` if already present.
- **Side effect:** calls `provider.add_ticker()`, so a ticker outside the
  seeded ten starts streaming immediately and comes back with a price already
  populated.

### `DELETE /api/watchlist/{ticker}`
`200` `{"ok": true}`, or `404` if not present.

- **Side effect:** calls `provider.remove_ticker()` — *unless the portfolio
  still holds the ticker*, in which case it keeps streaming so P&L stays live.

---

## Chat

### `POST /api/chat`
Request `{ "message": "buy 10 AAPL" }`. Returns the complete response — there
is no token streaming.

```json
{
  "message": "Buying 10 shares of AAPL.",
  "trades": [ { "ticker": "AAPL", "side": "buy", "quantity": 10 } ],
  "watchlist_changes": [ { "ticker": "PYPL", "action": "add" } ]
}
```

`trades` and `watchlist_changes` are `null` when there are none. Actions in
the response have **already been executed** by the time it returns; failures
are appended to `message` rather than returned as an error status.

**Inference:** LiteLLM → OpenRouter → `openrouter/openai/gpt-oss-120b`, pinned
to Cerebras with `provider: {"order": ["cerebras"], "allow_fallbacks": false}`.

**Structured output** uses a strict `json_schema` (not `json_object`), so
`side` is constrained to `buy`/`sell` and `action` to `add`/`remove`. The
schema lives in `chat.py` as `RESPONSE_SCHEMA`.

**Failure handling** — `_call_llm` never raises. Transport errors, non-JSON,
and schema violations all degrade to a conversational `message`, and a
half-parsed response never has its actions executed.

**`LLM_MOCK=true`** short-circuits before any network call and returns
deterministic responses. E2E tests rely on this.

---

## System

### `GET /api/health`
`200` `{"status": "ok"}`. Used by Docker and deployment probes.

### Static files
Everything not under `/api/*` is served from `static/` (the Next.js export)
with `html=True`, mounted at `/`.

---

## Environment

| Variable | Effect |
|---|---|
| `OPENROUTER_API_KEY` | Required for real chat. |
| `MASSIVE_API_KEY` | Set and non-empty → Massive REST polling; else the GBM simulator. |
| `MASSIVE_POLL_INTERVAL` | Poll seconds, default 15 (free tier is 5 calls/min). |
| `LLM_MOCK` | `true` → deterministic mock chat, no network. |
| `DB_PATH` | SQLite file path. Defaults to `<project root>/db/finally.db`; the Dockerfile sets `/app/db/finally.db`, which is the mounted volume. |

Market data providers are interchangeable behind
`app/market/interface.py::MarketDataProvider` (`start`, `stop`, `add_ticker`,
`remove_ticker`). Everything downstream reads the shared in-memory cache in
`app/market/cache.py` and is agnostic to the source.

---

## Known divergences

None outstanding. The gaps found during the SPEC audit have been fixed and
closed: `fin-b64` (chat filled at a hardcoded $150), `fin-dxo` (watchlist
additions never streamed), `fin-om1.2` (SQLite written off the volume),
`fin-om1.3` (no Cerebras pinning, weak structured output), `fin-9t8` (heatmap
not area-proportional), `fin-r09` (duplicate price cache), `fin-om1.4`
(frontend test environment broken).

When code and PLAN.md diverge in future, record it here with the bead that
tracks the fix, and treat PLAN.md as authoritative.
