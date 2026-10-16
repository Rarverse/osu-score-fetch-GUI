# node:22.23.3-bookworm-slim, multi-arch index digest
FROM node:26.11.1-bookworm-slim@sha256:86f07bc9c5dce4578cf37e5a418b7bfc7f817cda25cde66e2b66e95ed86c4567 AS build

WORKDIR /src

COPY package.json package-lock.json .npmrc ./
COPY apps/web/package.json apps/web/package.json

RUN npm ci --ignore-scripts

COPY apps/web apps/web

ARG VITE_SITE_URL=
ENV VITE_SITE_URL=${VITE_SITE_URL}

RUN npm run build --workspace apps/web

# caddy:2.10.2, multi-arch index digest
FROM caddy:2.10.2@sha256:c3d7ee5d2b11f9dc54f947f68a734c84e9c9666c92c88a7f30b9cba5da182adb

COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /src/apps/web/dist /srv

# Check both the static site and the API through the same HTTP entry point.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ && wget -q -O /dev/null http://127.0.0.1/health
