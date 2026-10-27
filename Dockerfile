# syntax=docker/dockerfile:1

# --- Stage 1: build the React SPA ---
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY LICENSE /LICENSE
COPY web/ ./
RUN npm run build

# --- Stage 2: Python runtime — FastAPI serves the API AND the built SPA ---
FROM python:3.12-slim
WORKDIR /app
COPY api/requirements.txt ./api/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r ./api/requirements.txt
COPY core/ ./core/
COPY api/ ./api/
COPY LICENSE THIRD_PARTY_NOTICES.md ./
COPY --from=web /web/dist ./web/dist
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/api/health', timeout=3).close()"
# Railway injects $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
