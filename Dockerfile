# Two images for docker compose: target api (FastAPI + Alembic), target web (nginx: SPA + /api proxy).
FROM node:22-slim AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
# The guide imports content/*.json at build time (web/src/guide/site.ts).
COPY content/ /content/
RUN npm run build

FROM nginx:1.30-alpine AS web
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=web-build /web/dist /usr/share/nginx/html

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS api
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev
COPY content/ /app/content/
ENV CONTENT_DIR=/app/content
ARG GIT_SHA=unknown
ENV GIT_SHA=$GIT_SHA PATH=/app/.venv/bin:$PATH
EXPOSE 8000
# Migrations first: the API never starts on an old schema.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn api.main:app --host 0.0.0.0 --port 8000"]
