# Stage 1: Build React SPA
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm install

# Copy source files and build
COPY . .
RUN npm run build

# Stage 2: Serve with Nginx
FROM nginx:alpine

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy Nginx configuration template for dynamic $PORT injection
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Cloud Run default port is 8080
ENV PORT=8080
EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
