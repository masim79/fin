# Stage 1: Build frontend static export
FROM node:20-slim AS frontend-build

WORKDIR /build
COPY frontend/ .
RUN npm ci && npm run build

# Stage 2: Production image with backend + static frontend
FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Install Python dependencies
COPY backend/ backend/
RUN cd backend && uv sync --frozen --no-dev

# Copy frontend build output as static files
COPY --from=frontend-build /build/out/ static/

EXPOSE 8000

# The SQLite file must live on the volume mounted at /app/db so the portfolio
# survives container restarts (SPEC section 11).
ENV DB_PATH=/app/db/finally.db
VOLUME ["/app/db"]

WORKDIR /app/backend

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
