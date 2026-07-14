# Frontend Dockerfile — ARCH-L1-001 ReactFrontend
# ADR-08: Self-Hosted via Docker Compose (no Kubernetes in v1)

FROM node:22-slim AS base

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
FROM nginx:alpine AS production

COPY --from=builder /app/dist /usr/share/nginx/html

# TODO: Add nginx.conf for SPA routing (all paths → index.html)
# COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
