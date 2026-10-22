# Frontend Dockerfile — ARCH-L1-001 ReactFrontend
# ADR-08: Self-Hosted via Docker Compose (no Kubernetes in v1)

FROM node:22.17.0-slim@sha256:b04ce4ae4e95b522112c2e5c52f781471a5cbc3b594527bcddedee9bc48c03a0 AS base

WORKDIR /app

COPY package.json package-lock.json ./

# Development stage
FROM base AS development

RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# Production build stage
FROM base AS builder

ARG VITE_API_BASE_URL
ARG VITE_ALLOWED_HOSTS
# Issue #980: the bluepencil review layer guard is read at *build* time
# (`import.meta.env.VITE_BLUEPENCIL_ENABLED`, loader.ts). Without these ARGs a
# `--build-arg VITE_BLUEPENCIL_ENABLED=1` was silently ignored and every
# prebuilt/production image evaluated the guard as false.
ARG VITE_BLUEPENCIL_ENABLED
ARG VITE_BLUEPENCIL_ENVIRONMENT

RUN npm ci

COPY . .

RUN VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_ALLOWED_HOSTS=$VITE_ALLOWED_HOSTS \
    VITE_BLUEPENCIL_ENABLED=$VITE_BLUEPENCIL_ENABLED \
    VITE_BLUEPENCIL_ENVIRONMENT=$VITE_BLUEPENCIL_ENVIRONMENT \
    npm run build

# Production serve stage (nginx)
FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10 AS production

# The digest above freezes the base image, but Alpine's rolling apk repo
# still ships security patches (e.g. openssl, c-ares) between the base
# image's own rebuilds, so even a pinned base can carry CRITICAL/HIGH CVEs
# that are already fixed upstream. Trivy's exit-code:1 gate in
# docker-publish.yml caught this on 2026-08-30 (35 findings, all with a
# fixed version available) — patch OS packages at build time so the gate
# stays green regardless of how stale the upstream base rebuild is.
RUN apk update && apk upgrade --no-cache

# Create non-root user for security
RUN addgroup -S app && adduser -S app -G app

COPY --from=builder /app/dist /usr/share/nginx/html

COPY nginx.conf /etc/nginx/conf.d/default.conf

# Ensure nginx html directory and logs are owned by app user
RUN chown -R app:app /usr/share/nginx/html /var/log/nginx

# Create necessary nginx directories for cache (required for non-root operation)
RUN mkdir -p /var/cache/nginx && chown -R app:app /var/cache/nginx

# /run is a tmpfs mounted fresh at container start on many container
# runtimes, so a build-time chown of it is discarded and nginx's default
# `pid /run/nginx.pid;` fails with "Permission denied" as non-root.
# Redirect it to /tmp (always world-writable, sticky bit) instead.
RUN sed -i 's#pid\s*/run/nginx\.pid;#pid /tmp/nginx.pid;#' /etc/nginx/nginx.conf

EXPOSE 8080

# Run as non-root user
USER app

CMD ["nginx", "-g", "daemon off;"]
