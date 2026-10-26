# Stage 1: Build React SPA
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm install

# Copy source files and build
COPY . .
RUN npm run build

# Stage 2: Python backend + Nginx with Supervisor
FROM python:3.12-slim

# Install nginx, supervisor, and runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    supervisor \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy Python backend
COPY backend/ ./backend/

# Install Python dependencies
RUN pip install --no-cache-dir -e "./backend[server]"

# Copy built React assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy Nginx configuration template for dynamic $PORT injection
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Copy Supervisor configuration
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Cloud Run default port is 8080
ENV PORT=8080
EXPOSE 8080

# Create necessary directories
RUN mkdir -p /var/log/supervisor /var/run/nginx /data

# Run supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
