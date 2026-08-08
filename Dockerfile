FROM node:22-alpine AS web
WORKDIR /app/web
COPY web/package.json ./
RUN npm install
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ECHO_MASQUE_ENVIRONMENT=production \
    ECHO_MASQUE_DEBUG=false \
    ECHO_MASQUE_PUBLIC_DEMO_ENABLED=true \
    ECHO_MASQUE_DATABASE_URL=sqlite:////data/echo_masque.db \
    ECHO_MASQUE_SEMANTIC_PARTICIPATION_ENABLED=true \
    ECHO_MASQUE_SEMANTIC_EMBEDDING_CACHE_DIR=/data/embedding-models
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN python -m pip install --no-cache-dir .
COPY --from=web /app/web/dist ./web/dist
RUN mkdir -p /data
EXPOSE 8000
CMD ["sh", "-c", "exec python -m uvicorn echo_masque.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
