# node:22.23.3-bookworm-slim, multi-arch index digest
FROM node:22.23.3-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS build

WORKDIR /src

COPY package.json package-lock.json .npmrc ./
COPY apps/web/package.json apps/web/package.json

RUN npm ci --ignore-scripts

COPY apps/web apps/web

ARG VITE_SITE_URL=
ENV VITE_SITE_URL=${VITE_SITE_URL}

RUN npm run build --workspace apps/web

# nginx:1.30.6-alpine, multi-arch index digest
FROM nginx:1.31.7-alpine@sha256:892bb2152464f0c5d8972593a5f5afaf8054552580b699d95f8ff4af08c2d33d

COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/15-trusted-proxies.sh /docker-entrypoint.d/15-trusted-proxies.sh
RUN chmod 755 /docker-entrypoint.d/15-trusted-proxies.sh
COPY --from=build /src/apps/web/dist /usr/share/nginx/html

# Check both the static site and the API through the same HTTP entry point.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ && wget -q -O /dev/null http://127.0.0.1/health
