# ============================================================
# KYS Agent AI Branch - Multi-stage: React + FastAPI + Nginx + Supervisor
# ============================================================
# Stage 1: Build React SPA
# ============================================================
FROM node:20-alpine AS frontend-builder

# Build argument for API base path (e.g., /qa)
ARG VITE_API_BASE=/qa

WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm install

# Copy source files and build
COPY . .
ARG VITE_API_BASE
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

# ============================================================
# Stage 2: Build Python backend dependencies
# ============================================================
FROM python:3.12-slim AS backend-builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies for Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy Python project and install dependencies
COPY backend/pyproject.toml backend/
COPY backend/kys backend/kys
RUN pip install "./backend[server]"

# ============================================================
# Stage 3: Final runtime image with Nginx + Uvicorn + Supervisor
# ============================================================
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install runtime dependencies: nginx, supervisor, curl (for health checks), gettext-base (envsubst)
# Debian's default site listens on :80 and would shadow our config, so it is removed.
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    supervisor \
    curl \
    gettext-base \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /etc/nginx/sites-enabled/default

WORKDIR /app

# Copy Python backend from builder
COPY --from=backend-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=backend-builder /app/backend/kys /app/kys

# Copy built React frontend from builder
COPY --from=frontend-builder /app/dist /app/web

# Copy nginx configuration template for dynamic $PORT injection
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Copy supervisor configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create non-root user and directories
RUN useradd --create-home kys && \
    mkdir -p /data /var/log/supervisor /var/log/nginx && \
    chown -R kys:kys /app /data /var/log/supervisor /var/log/nginx

# Environment variables
ENV KYS_DB_PATH=/data/kys.db \
    KYS_OVERRIDES_PATH=/data/kys_overrides.json \
    KYS_BASE_PATH=/qa \
    KYS_WEB_DIR=/app/web \
    PORT=8080 \
    UVICORN_HOST=127.0.0.1 \
    UVICORN_PORT=8000

EXPOSE 8080

VOLUME /data

# Render nginx config with the runtime $PORT (Cloud Run sets it), then run supervisor
# to manage nginx and uvicorn. Debian's nginx does not process /etc/nginx/templates itself.
CMD ["/bin/sh", "-c", "envsubst '${PORT}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf"]
