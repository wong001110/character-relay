FROM node:22-bookworm-slim AS node_runtime

FROM node:22-alpine AS web
WORKDIR /app/web
COPY web/package.json ./
RUN npm install
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    CHARACTER_RELAY_ENVIRONMENT=production \
    CHARACTER_RELAY_DEBUG=false \
    CHARACTER_RELAY_PUBLIC_DEMO_ENABLED=true \
    CHARACTER_RELAY_DATABASE_URL=sqlite:////data/echo_masque.db \
    CHARACTER_RELAY_SEMANTIC_PARTICIPATION_ENABLED=true \
    CHARACTER_RELAY_SEMANTIC_EMBEDDING_CACHE_DIR=/data/embedding-models
WORKDIR /app
COPY --from=node_runtime /usr/local/bin/node /usr/local/bin/node
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libatomic1 libstdc++6 \
    && node --version \
    && python -m pip install --no-cache-dir . \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*
COPY --from=web /app/web/dist ./web/dist
RUN mkdir -p /data
EXPOSE 8000
CMD ["sh", "-c", "exec python -m uvicorn echo_masque.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
