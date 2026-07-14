# Frontend Dockerfile — ARCH-L1-001 ReactFrontend
# ADR-08: Self-Hosted via Docker Compose (no Kubernetes in v1)

FROM node:22.17.0-slim AS base

WORKDIR /app

COPY package.json package-lock.json ./

# Development stage
FROM base AS development

RUN npm install --legacy-peer-deps

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# Production build stage
FROM base AS builder

RUN npm ci

COPY . .

RUN npm run build

# Production serve stage (nginx)
FROM nginx:1.27-alpine AS production

# Create non-root user for security
RUN addgroup -S app && adduser -S app -G app

COPY --from=builder /app/dist /usr/share/nginx/html

COPY nginx.conf /etc/nginx/conf.d/default.conf

# Ensure nginx html directory is owned by app user
RUN chown -R app:app /usr/share/nginx/html

EXPOSE 80

# Run as non-root user
USER app

CMD ["nginx", "-g", "daemon off;"]
