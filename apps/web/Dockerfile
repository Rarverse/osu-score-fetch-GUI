# node:22.23.3-bookworm-slim, multi-arch index digest
FROM node:26.13.0-bookworm-slim@sha256:bc0a2afd3b74ce12222fc8bab99271e66257f021078f5f4a5d687a77d280c1d9 AS build

WORKDIR /src

COPY package.json package-lock.json .npmrc ./
COPY apps/web/package.json apps/web/package.json

RUN npm ci --ignore-scripts

COPY apps/web apps/web

ARG VITE_SITE_URL=
ENV VITE_SITE_URL=${VITE_SITE_URL}

RUN npm run build --workspace apps/web

# nginx:1.30.6-alpine, multi-arch index digest
FROM nginx:1.30.6-alpine@sha256:970364228b1e4f932abc22d321932816782cca8a20b85a77552a7cfe9acfb3b5

COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/15-trusted-proxies.sh /docker-entrypoint.d/15-trusted-proxies.sh
RUN chmod 755 /docker-entrypoint.d/15-trusted-proxies.sh
COPY --from=build /src/apps/web/dist /usr/share/nginx/html

# Check both the static site and the API through the same HTTP entry point.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ && wget -q -O /dev/null http://127.0.0.1/health
