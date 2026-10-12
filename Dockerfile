# The React screens (POS, waiter, kitchen, kiosk, status board), built into src/kiosk/web/ui.
FROM node:22-slim AS screens
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY --from=screens /build/src/kiosk/web/ui ./src/kiosk/web/ui
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

RUN useradd --create-home kiosk && mkdir -p /app/prints /app/media && chown kiosk /app/prints /app/media
USER kiosk
EXPOSE 8000

# Apply migrations, then serve. One worker: the edge real-time hub lives in-process.
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn kiosk.main:app --host 0.0.0.0 --port 8000 --proxy-headers"]
