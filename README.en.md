# Raru Score Fetcher

[简体中文](README.md) | **English**

A web app for looking up osu! players in all four game modes. Search by username or ID to view **Best 20 / Best 50** scores and export them as PNG images.

React + TypeScript + Vite · FastAPI + ossapi · Nginx · Docker Compose

## Contents

1. [Features and scope](#features-and-scope)
2. [Quick deployment](#quick-deployment)
3. [Local development](#local-development)
4. [Configuration](#configuration)
5. [Credentials and privacy](#credentials-and-privacy)
6. [API](#api)
7. [Project structure and checks](#project-structure-and-checks)
8. [Credits and disclaimer](#credits-and-disclaimer) · [License](#license)

More documentation: [Operations](docs/operations.md) · [Deployment details](deploy/README.md) (Chinese)

## Features and scope

- **Four modes:** osu!, osu!taiko, osu!catch, and osu!mania. Use the player's preferred mode or select one manually.
- **Player and score overview:** View player pp, global rank and accuracy, along with score pp, accuracy, mods, rank, combo and base beatmap SR. Rank and star colors are consistent between the page and exported images.
- **B20 / B50 PNG export:** Includes avatars, beatmap artwork and total play time in the current mode. B20 uses two columns and B50 uses five, with a dark gradient and soft geometric background. Asset loading progress, collapsible previews, repeat downloads and retries are supported. If fewer scores are available, only those scores are exported.
- **Continuous queries:** Changing the mode or score count for the same player runs a new query automatically. Previous results remain visible while loading; the first query shows a skeleton. Cancellation, retries and busy countdowns are supported.
- **Recent searches:** The browser stores the last five successfully queried players; entries can be removed individually or cleared. Use `Ctrl / ⌘ + K` to focus search and keyboard shortcuts to navigate long lists.
- **English, Chinese and mobile:** `/en` and `/zh` select the language (trailing slashes are also supported); the root path follows the browser language. The interface supports responsive layouts, keyboard menus and reduced motion.
- **Self-hosting:** Players do not need to sign in. Use shared server OAuth credentials or let visitors temporarily supply their own.

The current version is **v0.2.0**; the footer reads the version from `apps/web/package.json`.

Only `best` scores are queried, up to 50. SR is the beatmap's base difficulty without mods; pp is returned by osu!. Results for the same player and mode are reused for three minutes by default and refreshed on the next query after expiry. Other players can still be queried during that time.

## Quick deployment

Requires Docker Engine and the Docker Compose plugin (Compose ≥ 2.24.0).

### 1. Start the services

```sh
git clone https://github.com/Rarverse/osu-score-fetch-GUI.git
cd osu-score-fetch-GUI
docker compose up -d
```

The first startup builds the frontend and backend from source. Open [http://127.0.0.1:8080](http://127.0.0.1:8080). Node.js, Python and uv are not needed on the host.

### 2. Configure OAuth credentials

**The page starts without server credentials, but queries require OAuth credentials.** Visitors can enter their own temporarily on the page, or you can configure shared credentials:

```sh
cp .env.example .env
chmod 600 .env
```

Edit `.env` and uncomment and fill in `OSU_CLIENT_ID` and `OSU_CLIENT_SECRET`. Create an OAuth application in [osu! account settings](https://osu.ppy.sh/home/account/edit) and use its Client ID and Client Secret, not the legacy API key. The project uses the client credentials grant and `public` scope; player authorization is not required.

After saving, recreate the services to apply the credentials:

```sh
docker compose up -d
```

### 3. Set the public URL (optional)

For a public deployment, set `VITE_SITE_URL` to the public root URL, such as `https://scores.example.com`, then rebuild:

```sh
docker compose up -d --build
```

`VITE_SITE_URL` is embedded in sharing metadata at build time, so changes require rebuilding the web image. See [.env.example](.env.example) for the full configuration.

### Domain and HTTPS

```text
Visitor → external HTTPS reverse proxy → web:80 (Nginx) → api:8000
```

The default mapping is `127.0.0.1:8080:80`: the host listens on `127.0.0.1:8080` and Nginx listens on port `80` inside the container. For an external reverse proxy on the same host, use **`http://127.0.0.1:8080`** as the upstream and preserve the request path.

An external Nginx or SafeLine instance handles the domain, HTTPS and certificates. The project serves HTTP internally and does not publish API port 8000 on the host. For a reverse proxy in a separate bridge-network container, see the [deployment instructions](deploy/README.md#反代在独立-bridge-网络容器) for connectivity and trusted proxies.

### Verify and update

```sh
docker compose ps
curl -fsS http://127.0.0.1:8080/health
docker compose logs --tail=100
```

A 200 response from `/health` only confirms that the API is alive. Complete a real query on the page to verify OAuth and upstream connectivity.

To update:

```sh
git pull --ff-only
docker compose up -d --build
```

Scores, image caches and usage statistics are stored in the named volume `osu-score-api_osu-data`. Rebuilding containers or running `docker compose down` preserves it; **`docker compose down -v` deletes the volume**.

The root `compose.yaml` builds from source; `deploy/compose.yaml` deploys GitHub Actions / GHCR images. See the [deployment guide](deploy/README.md) for image updates, backups, migration and rollback, and [operations](docs/operations.md) for caches, logs and request limits.

## Local development

Requires Python ≥ 3.12, [uv](https://docs.astral.sh/uv/), Node.js 22 and npm.

1. Install frontend dependencies from the repository root:

   ```sh
   npm ci
   ```

2. Start the API in one terminal:

   ```sh
   cd apps/api
   uv sync --locked
   cp .env.example .env
   # Optional: edit .env and set OSU_CLIENT_ID and OSU_CLIENT_SECRET
   uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

3. Start the frontend in another terminal, from the repository root:

   ```sh
   npm run dev
   ```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Vite proxies `/api` and `/health` to `http://127.0.0.1:8000`; interactive API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

The local API automatically reads `apps/api/.env`; the root `.env` is for Compose. If server credentials are absent and the request does not provide personal credentials, a cache miss returns `503 NOT_CONFIGURED`, not demo scores.

## Configuration

### Docker Compose

Set these in the root `.env`; see [.env.example](.env.example).

| Variable | Default | Purpose |
| --- | --- | --- |
| `BIND_ADDR` | `127.0.0.1` | Host address for web |
| `HTTP_PORT` | `8080` | Host HTTP port for web |
| `VITE_SITE_URL` | Empty | Public root URL for sharing metadata; rebuild after changes |
| `API_ENV_FILE` | `.env` | API environment file; can point to an existing `/etc/osu-score-api/env` |
| `COMPOSE_SUBNET` / `COMPOSE_GATEWAY` | `172.31.210.0/24` / `172.31.210.1` | Docker network; change together if there is a conflict |
| `WEB_IPV4` | `172.31.210.10` | Fixed web address and proxy address trusted by the API |
| `TRUSTED_PROXIES` | `127.0.0.1 172.31.210.1` | External proxy IPs trusted by web, space-separated |

### API

See [config.py](apps/api/app/config.py) for definitions and [apps/api/.env.example](apps/api/.env.example) for the local example. Compose reads these settings from the root `.env` by default, or from the file specified by `API_ENV_FILE`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `OSU_CLIENT_ID` / `OSU_CLIENT_SECRET` | None | First server OAuth credential pair; configure both |
| `OSU_CLIENT_ID_2` / `OSU_CLIENT_SECRET_2` | None | Optional second pair; configure both |
| `OSU_CLIENT_ID_3` / `OSU_CLIENT_SECRET_3` | None | Optional third pair; configure both |
| `LOG_FORMAT` | `text` | Readable English logs; use `json` for log collectors |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`; `DEBUG` adds request, rate-spacing and image-queue details |
| `CACHE_TIMEOUT` | `180` | Score reuse window in seconds; minimum 60 |
| `CACHE_RETENTION` | `15552000` | Score and image file retention from last write, in seconds (180 days); must be at least the reuse window |
| `CACHE_PATH` | `apps/api/.cache` | Default local cache directory |
| `STATS_PATH` | `apps/api/data/cache/usage.json` | Default local anonymous statistics file |
| `STATS_HASH_SALT` | None | Random statistics secret of at least 32 characters, kept only in the server environment; without it only query, mode and source counts are stored, without identity hashes |
| `NEGATIVE_CACHE_TTL` | `60` | Retention of player-not-found results, in seconds |
| `RATE_LIMIT_WINDOW` | `60` | Local rate-limit window, in seconds |
| `RATE_LIMIT_GLOBAL` | `120` | Score requests allowed site-wide per window |
| `RATE_LIMIT_PER_IP` | `20` | Queries allowed per IP per window |
| `RATE_LIMIT_PER_PLAYER` | `10` | Actual cache misses allowed per normalized player input per window; score and player-not-found cache hits do not consume this quota |
| `RATE_LIMIT_UPSTREAM_COST_PER_IP` | `30` | Upstream cost quota per IP; each actual cache miss conservatively costs 3 |
| `RATE_LIMIT_IMAGES_GLOBAL` | `300` | Image requests allowed site-wide per window |
| `RATE_LIMIT_IMAGES_PER_IP` | `120` | Image requests allowed per IP per window; covers one B50 export |
| `OSU_REQUESTS_PER_MINUTE` | `60` | Separate request budgets for API and images; configurable from 3 to 60 |
| `CORS_ORIGINS` | localhost and 127.0.0.1 on port 5173 | Allowed origins as a JSON string array |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Proxy IPs / CIDRs trusted by the API, comma-separated |

Local default paths in the table are described relative to the repository; **relative paths you configure are resolved against the API process's working directory**. Compose fixes `CACHE_PATH` and `STATS_PATH` to `/var/lib/osu-score-api/cache` and `/var/lib/osu-score-api/stats/usage.json` in the data volume, and configures API proxy trust from `WEB_IPV4`.

## Credentials and privacy

### Credentials

Keep server secrets in an uncommitted environment file. Do not put them in `VITE_` variables, which are exposed in frontend builds.

Personal Client ID / Client Secret values entered on the page live only in page memory and are cleared on refresh or close. They are sent to the backend in `X-Osu-Client-Id` / `X-Osu-Client-Secret` headers for a token exchange. Users can see credentials they submit in their browser's Network panel. The server does not write personal credentials to files or OAuth tokens to ossapi pickle files. Personal credentials require HTTPS on public sites, except for local development addresses.

Personal credentials are used upstream only on cache misses. Cache hits reuse the same public scores without revalidating credentials. Personal and server credentials share the cache, rate limits and site-wide request budgets.

### Browser storage

Recent searches (player ID, username, avatar URL and query mode) are stored in the browser's `localStorage`, without API credentials; users can remove or clear them. Score responses and temporary Blob URLs for export previews are held only in page memory and cleared on refresh. Downloaded PNGs are saved by the browser or user and are not deleted on refresh.

### Anonymous usage statistics

The browser also stores a random anonymous visitor ID (`rarsu-visitor-id`) in `localStorage` and sends it as `X-Visitor-Id`. The server counts queries, modes and sources by UTC date only for requests that pass parameter validation and applicable site rate limits. With `STATS_HASH_SALT` configured, it also counts distinct players from successful queries and returning visitors: visitor IDs and successful player IDs are hashed with HMAC-SHA-256. The statistics file stores hashes and an irreversible key identifier, not the secret or raw identity fields. Statistics use a rolling 180-day window, cleaned on the next statistics write, and retain at most 10,000 visitor hashes. Old files do not delete themselves on a timer when there are no subsequent queries.

Generate a new `STATS_HASH_SALT` with `openssl rand -hex 32` and put it in the API environment file actually in use (local `apps/api/.env`, source Compose `.env` or `API_ENV_FILE`, or the server's `/etc/osu-score-api/env`). Keep it stable across deployments; do not reuse the salt in an old `usage.json`. At startup, the API migrates old statistics, removing the old salt and player and visitor hashes while retaining historical daily totals and all query counts. On the migration day, distinct player and returning visitor counts restart from zero, and return-visitor recognition builds up again. Changing or removing the secret has the same effect. Without a secret, newly recorded distinct player and returning visitor counts are 0 (disabled), not evidence that there were no players or returns. Old salts and hashes in existing backups are not automatically removed. A statistics read or migration failure logs `usage_write_failed`; it neither overwrites the damaged file nor interrupts score service.

### Source statistics

Links may use `https://your-domain/?from=bili`, `/zh?from=youtube`, and so on. The frontend attaches the current page's `from` label to score API requests; counts are stored in `days[UTC date].queries_by_source`, for example `{"bili":12,"youtube":3,"direct":5}`. Each backend request that passes validation and rate limiting and enters query processing counts once, including server cache hits and upstream failures. This is not a count of page views, unique people or successful queries.

Labels are trimmed and lowercased; they must contain 1–32 English letters, digits, underscores or hyphens and start with a letter or digit. Missing or invalid labels become `direct`. At most 64 custom sources are retained per day; additional new sources become `other`. Labels are stored in plain text, so use channel names only. Full page URLs are not stored, and no additional source data is persisted. Labels are supplied by the requester and can be forged, so they are useful only for approximate channel statistics; old data is not backfilled.

### Cache and retention

Browser cache hits do not create backend requests or increment server statistics. There is no administration page or query API for statistics; write failures do not affect score responses. Score and image caches contain public player profiles, scores and assets. Files are cleaned by subsequent cache operations 180 days after their last write. Account for both caches and statistics when making backups.

### Third-party requests

Page styles request DM Sans and Space Grotesk from Google Fonts. During normal page display, the browser requests avatars and beatmap artwork directly from official osu! image domains; PNG export uses the site's same-origin image cache. Third parties receive the network information needed to fulfill these requests and apply their own processing and retention policies. The bundled deployment Nginx sends `Referrer-Policy: no-referrer`, so the current page URL is not sent with these requests.

### Logs and request limits

Application logs record raw player search values and, after successful resolution, public usernames and player IDs for troubleshooting. They do not record personal API secrets, raw visitor IDs, IP addresses, OAuth tokens or image URLs. Docker logs rotate at 10 MiB with up to three files by default; no fixed retention period is promised. External reverse proxies and third-party services have their own logging policies.

Developer tools can reveal public API paths and browser requests; they are not a security boundary. Before reading score caches, the server checks site-wide and per-IP limits. Only after a second cache-miss check under a lock does it atomically check and deduct the per-player and per-IP upstream-cost quotas; cache hits remain subject to site-wide and per-IP limits. Image requests are limited site-wide and per IP before cache reads. Query parameters do not change the cache identity of the same official image, preventing meaningless parameters from creating permanent cache files.

## API

### Health check

```http
GET /health
```

```json
{"status":"ok","modes":["osu","taiko","fruits","mania"]}
```

### Get best scores

```http
GET /api/v1/players/{username}/scores?type=best&limit=20&mode=mania
```

| Parameter | Description |
| --- | --- |
| `username` | URL-encoded username or numeric ID; trimmed and case-insensitive |
| `type` | Only `best` is supported; default `best` |
| `limit` | 1–50; default 20; the frontend offers Best 20 / Best 50 |
| `mode` | Optional `osu`, `taiko`, `fruits`, or `mania`; omitted means the player's preferred mode; catch is `fruits` |

A successful response includes `player`, the resolved `mode`, `type`, `scores` and `fetched_at`. See the [Python response model](apps/api/app/schemas/scores.py) and [TypeScript types](apps/web/src/types.ts) for all fields; the running API exposes OpenAPI at `/openapi.json`.

- Score `accuracy` is 0–1; player `hit_accuracy` is 0–100.
- Unavailable fields such as pp and rank remain `null` and appear as `—` on the page.
- `star_rating` is base SR; ranks `X` / `XH` map to `SS` / `SSH`.
- Times use ISO 8601 and are displayed in the browser's local timezone.
- `X-Cache` is `MISS`, `HIT`, or `BYPASS` (cache write failed); `X-Cache-TTL` is the remaining reuse time in seconds.

Error format:

```json
{"error":{"code":"PLAYER_NOT_FOUND","message":"未找到该玩家，请检查用户名或 ID。"}}
```

| HTTP | Error code | Meaning |
| --- | --- | --- |
| 404 | `PLAYER_NOT_FOUND` | Player not found |
| 422 | `INVALID_PLAYER` / `INVALID_REQUEST` / `INVALID_CREDENTIALS` | Invalid player input, query parameters or personal credential format |
| 429 | `RATE_LIMITED` | Local rate limit; includes `Retry-After` |
| 502 | `UPSTREAM_ERROR` | OAuth, osu! request or upstream data parsing failed |
| 503 | `NOT_CONFIGURED` | No usable server credentials configured and no personal credentials supplied |
| 503 | `SERVER_BUSY` / `UPSTREAM_BUSY` | Query concurrency is busy, upstream budget exhausted or cooldown active; includes `Retry-After` |

## Project structure and checks

```text
apps/web/          React UI, translations, B20/B50 export and frontend tests
apps/api/          FastAPI, osu! client, cache, rate limits and backend tests
compose.yaml       Default deployment entry point, building from source
deploy/            Nginx config, GHCR deployment, update scripts and deployment guide
docs/operations.md Cache, request limits, logs and operations
DEVELOPMENT.md     Ongoing development guidance
```

Edit the home page introduction in `apps/web/src/content/intro.md` and `intro.en.md`; UI translations are in `apps/web/src/i18n.ts`. Restart the development server or wait for hot reload after changes; production requires a rebuild. Frontend build output is in `apps/web/dist` and is served by Nginx in production.

Run frontend checks from the repository root:

```sh
npm run typecheck
npm run lint
npm test
npm run build
```

Run backend checks from `apps/api`:

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

Automated tests do not require real osu! credentials. Check the deployment configuration with `docker compose config --quiet`; actual container startup and a real score query must still be verified separately. Formatting commands are `npm run format` for the frontend and `uv run ruff format .` for the backend; they modify files.

## Credits and disclaimer

The query approach references [Rarverse/osu-score-fetch](https://github.com/Rarverse/osu-score-fetch); data comes from [osu! API v2](https://osu.ppy.sh/docs/).

Raru Score Fetcher is maintained by Rarverse. It is an unofficial fan-made project and is not affiliated with peppy / osu!.

## License

Copyright © 2026 Rarverse.

This project is licensed under [GNU AGPLv3 (AGPL-3.0-only)](LICENSE), permitting use, modification and commercial use. Distribution of modified versions must comply with AGPLv3 source availability requirements; if a modified version is offered over a network, users of that service must also be given a way to obtain the corresponding source.

The core dependency [ossapi](https://github.com/liam-devoe/ossapi) uses AGPLv3. Third-party dependencies, osu! data, avatars and beatmap artwork remain subject to their respective licenses or terms of use.

## Publicity Community

[LINUX DO](https://linux.do/)
