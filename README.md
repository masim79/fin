# FinAlly — AI Trading Workstation

A visually dense trading terminal with live streaming prices, a simulated
$10,000 portfolio, and an LLM copilot that can analyze positions and execute
trades on your behalf.

Built entirely by coding agents as the capstone for an agentic AI course.

## Quick start

One command, one container, one port:

```bash
cp .env.example .env     # add your OPENROUTER_API_KEY
./scripts/start_mac.sh   # or: ./scripts/start_windows.ps1
```

Then open <http://localhost:8000>.

The market simulator runs by default, so no market data key is needed. Set
`MASSIVE_API_KEY` in `.env` to use real data instead.

To stop: `./scripts/stop_mac.sh` (or `stop_windows.ps1`). Your portfolio
persists in a Docker volume across restarts.

## Documentation

`planning/` is the shared contract that all agents reference:

- **[planning/PLAN.md](planning/PLAN.md)** — the project specification
- **[planning/API_CONTRACT.md](planning/API_CONTRACT.md)** — the
  frontend/backend API as actually implemented

## Layout

| Path | Contents |
|---|---|
| `frontend/` | Next.js + TypeScript, built as a static export |
| `backend/` | FastAPI (uv), serves `/api/*` and the static frontend |
| `planning/` | Specification and agent reference docs |
| `test/` | Playwright E2E suite |
| `db/` | Volume mount target for the SQLite file |

## Development

```bash
# Backend
cd backend && uv sync && uv run pytest
uv run uvicorn app.main:app --reload

# Frontend
cd frontend && npm install && npm test
npm run dev
```

Issue tracking uses [beads](https://github.com/gastownhall/beads): `bd ready`.
