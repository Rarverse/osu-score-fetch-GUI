# Rarsu 查分器

输入 osu! 玩家用户名或 ID，查看四种模式的 Top 20 / Top 50 最佳成绩，并下载对应的 B20 / B50 图片。项目属于 rarverse，是非官方 fan-made 网页工具，与 peppy / osu! 无隶属关系。

前端使用 React、TypeScript 和 Vite，后端使用 FastAPI 与 ossapi；生产环境由 Nginx 托管静态文件并转发 API 请求，支持 Docker Compose 部署。

[快速部署](#快速部署) · [本地开发](#本地开发) · [环境配置](#环境配置) · [API](#api) · [部署详情](deploy/README.md) · [持续开发建议](DEVELOPMENT.md)

## 功能

- **四种模式**：osu!、taiko、catch、mania。默认读取玩家资料中的首选模式，也可手动切换。
- **公开成绩查询**：无需登录，展示玩家 pp、全球排名和准确率，以及成绩的 pp、accuracy、mods、rank、combo、时间和谱面基础 SR。
- **官方等级与星级配色**：银色等级显示为 S / SS，悬停说明 Silver S / Silver SS；星级按 osu! 官网色谱及 gamma 插值着色，6.5★及以上的深色文字增加浅色底衬，9★及以上保持黑色，网页与导出图保持一致。
- **B20 / B50 图片导出**：根据最近一次成功查询的 Top 20 / Top 50 生成对应的双列 PNG，包含玩家头像、谱面曲绘和按 rank 区分颜色的成绩；不足所选数量时按实际数量导出。下载时单独显示素材加载进度、PNG 生成状态和浏览器下载提示，生成期间防止重复点击。修改模式或数量后，点击查询才会获取新成绩。
- **中英文界面**：根据浏览器语言自动选择中文或英文，无匹配时使用英文。
- **缓存与繁忙重试**：复用近期查询结果；服务繁忙时显示倒计时，最多自动重试 5 次，可取消等待或查询。
- **可选个人凭据**：访客可以临时填写自己的 osu! OAuth 凭据，部署者也可提供共享的服务端凭据。

当前仅支持 `best` 成绩，最多 50 条。SR 是**未应用 mods 的谱面基础难度**，pp 使用 osu! 返回值；没有 recent、分页、账号系统或批量抓取接口。

## 快速部署

准备好 Docker Engine 和 Docker Compose 插件（Compose ≥ 2.24.0），在仓库根目录执行：

```sh
docker compose up -d
```

首次启动会从源码构建前后端，站点默认位于 [http://127.0.0.1:8080](http://127.0.0.1:8080)。宿主机无需安装 Node.js、Python 或 uv，也无需登录 GHCR。

**不配置服务端凭据也能启动。** 首页和健康检查可用；实际查询需要访客填写自己的凭据，或按下面的步骤配置共享凭据。

### 配置共享凭据与公网地址

```sh
cp .env.example .env
chmod 600 .env
```

编辑 `.env`，取消注释并填写 `OSU_CLIENT_ID`、`OSU_CLIENT_SECRET`；将 `VITE_SITE_URL` 改为站点的公网根地址，例如 `https://scores.example.com`。OAuth 应用可在 [osu! 账号设置](https://osu.ppy.sh/home/account/edit) 中创建，本项目使用 client credentials grant 与 `public` scope，无需玩家登录授权。

```sh
docker compose up -d --build
```

`VITE_SITE_URL` 在构建时写入分享卡片元数据，修改后需要重建 web 镜像。其他部署选项见 [.env.example](.env.example)。

### 接入外部反向代理

访问链路：`访客 → 外部 HTTPS 反代 → web（HTTP）→ API`。

外部 Nginx 或雷池负责域名、HTTPS 和证书。同机反代的上游填写 **`http://127.0.0.1:8080`**，转发整个站点并保留路径。项目内部仅提供 HTTP，不申请或挂载证书，不占用宿主机 80/443；API 的 8000 端口仅在 Docker 网络内可用。

反代在独立 bridge 网络容器中时，容器内的 `127.0.0.1` 指向反代自身。请按[部署说明](deploy/README.md#反代在独立-bridge-网络容器)接入项目网络，使用 `http://web:80` 并配置可信代理 IP。

### 验证、更新与数据保留

```sh
docker compose ps
curl -fsS http://127.0.0.1:8080/health
docker compose logs --tail=100
```

`/health` 返回 200 只表示 API 存活，不能证明 OAuth 凭据有效或 osu! 上游可达。配置凭据后，还需在页面完成一次真实查询。

更新源码后执行：

```sh
git pull
docker compose up -d --build
```

成绩缓存和使用统计保存在命名卷 `osu-score-api_osu-data`，普通容器重建与 `docker compose down` 会保留数据。**`docker compose down -v` 会删除该卷。**

根目录 `compose.yaml` 用于源码部署；`deploy/compose.yaml` 用于现有 GitHub Actions / GHCR 镜像部署。反代配置、备份、旧部署迁移和镜像回滚见[完整部署说明](deploy/README.md)。

## 本地开发

需要 Python ≥ 3.12、[uv](https://docs.astral.sh/uv/)、Node.js 22 和 npm。

在仓库根目录安装前端依赖：

```sh
npm ci
```

在第一个终端启动 API：

```sh
cd apps/api
uv sync --locked
cp .env.example .env
# 可选：编辑 .env，填写 OSU_CLIENT_ID 和 OSU_CLIENT_SECRET
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

在第二个终端，从仓库根目录启动前端：

```sh
npm run dev
```

打开 [http://127.0.0.1:5173](http://127.0.0.1:5173)。Vite 将 `/api` 和 `/health` 代理到 `http://127.0.0.1:8000`；交互式 API 文档位于 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。

本地 API 自动读取 `apps/api/.env`；根目录 `.env` 用于 Compose，两者不要混淆。未配置服务端凭据且请求未携带个人凭据时，缓存未命中的查询返回 `503 NOT_CONFIGURED`，不会返回演示成绩。

## 环境配置

### Docker Compose

配置写在根目录 `.env`，示例见 [.env.example](.env.example)。

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `BIND_ADDR` | `127.0.0.1` | web 在宿主机的监听地址 |
| `HTTP_PORT` | `8080` | web 在宿主机的 HTTP 端口 |
| `VITE_SITE_URL` | 空 | 分享元数据的公网根地址，修改后需重新构建 |
| `API_ENV_FILE` | `.env` | API 环境文件，可指向已有的 `/etc/osu-score-api/env` |
| `COMPOSE_SUBNET` / `COMPOSE_GATEWAY` | `172.31.210.0/24` / `172.31.210.1` | Docker 网络；发生冲突时配套修改 |
| `WEB_IPV4` | `172.31.210.10` | web 固定地址，也是 API 信任的代理地址 |
| `TRUSTED_PROXIES` | `127.0.0.1 172.31.210.1` | web 信任的外部代理 IP，空格分隔 |

### API

源码定义见 [config.py](apps/api/app/config.py)，本地示例见 [apps/api/.env.example](apps/api/.env.example)。Compose 默认从根目录 `.env` 传入这些配置；设置 `API_ENV_FILE` 后则从指定文件读取。

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `OSU_CLIENT_ID` / `OSU_CLIENT_SECRET` | 无 | 可选的服务端 OAuth 凭据，须成对配置 |
| `LOG_FORMAT` | `text` | 英文易读日志；设为 `json` 可接入日志采集工具 |
| `LOG_LEVEL` | `INFO` | `DEBUG`、`INFO`、`WARNING` 或 `ERROR`；`DEBUG` 增加请求发起、限速间隔和图片队列细节 |
| `CACHE_TIMEOUT` | `60` | 查询结果复用窗口，单位秒，最小为 60 |
| `CACHE_RETENTION` | `15552000` | 缓存文件保留期，默认 180 天，不得短于复用窗口 |
| `CACHE_PATH` | `apps/api/.cache` | 本地默认缓存目录 |
| `STATS_PATH` | `apps/api/data/cache/usage.json` | 本地默认匿名统计文件 |
| `NEGATIVE_CACHE_TTL` | `60` | 玩家不存在结果的缓存时长，单位秒 |
| `RATE_LIMIT_WINDOW` | `60` | 本地限流窗口，单位秒 |
| `RATE_LIMIT_PER_IP` | `20` | 每个 IP 在窗口内允许的查询次数 |
| `RATE_LIMIT_PER_PLAYER` | `10` | 每个规范化玩家输入在窗口内允许的查询次数 |
| `OSU_REQUESTS_PER_MINUTE` | `60` | API 与图片各自的请求预算，可设为 3–60 |
| `CORS_ORIGINS` | localhost 与 127.0.0.1 的 5173 端口 | 允许来源，使用 JSON 字符串数组 |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | API 信任的代理 IP / CIDR，逗号分隔 |

表中的本地默认路径相对于仓库位置描述；**自行填写的相对路径按 API 进程工作目录解析**。Compose 将 `CACHE_PATH`、`STATS_PATH` 固定到数据卷中的 `/var/lib/osu-score-api/cache` 和 `/var/lib/osu-score-api/stats/usage.json`，并根据 `WEB_IPV4` 设置 API 代理信任地址。

## 凭据与隐私

服务端密钥保存在未提交的环境文件中，不能放进 `VITE_` 变量，这类变量会公开到前端构建产物。

页面中的个人 Client ID / Client Secret 仅保存在当前页面内存，刷新或关闭后清除；查询时通过 `X-Osu-Client-Id` / `X-Osu-Client-Secret` 请求头发送给后端，由后端换取 token。浏览器 Network 面板能够看到自己提交的凭据。服务端不将个人凭据写入文件，OAuth token 也不写入 ossapi 的 pickle 文件。公开站点使用个人凭据需要 HTTPS，本机开发地址除外。

个人凭据仅在缓存未命中时用于上游请求；命中时复用同一份公开成绩，不会再次验证凭据。个人凭据与服务端凭据共用缓存、限流和全站请求预算。

浏览器在 `localStorage` 中保存随机匿名访客 ID（`rarsu-visitor-id`），查询时通过 `X-Visitor-Id` 发送。服务端按 UTC 日期统计查询数、成功查询的去重玩家数、各模式查询数和回访访客数；访客 ID 与成功查询的玩家 ID 以加盐 SHA-256 保存，统计文件不含原始用户名、访客 ID 或 IP。

浏览器缓存命中不产生后端请求，因此不会新增服务端统计。统计文件没有管理页面或查询接口，写入失败不影响成绩返回；使用统计没有成绩缓存的 180 天自动清理机制。成绩缓存本身包含公开玩家资料与成绩，备份时应同时考虑缓存和统计文件。

## API

### 健康检查

```http
GET /health
```

```json
{"status":"ok","modes":["osu","taiko","fruits","mania"]}
```

### 查询最佳成绩

```http
GET /api/v1/players/{username}/scores?type=best&limit=20&mode=mania
```

| 参数 | 说明 |
| --- | --- |
| `username` | URL 编码后的用户名或数字 ID；去除首尾空格，大小写不敏感 |
| `type` | 仅支持 `best`，默认 `best` |
| `limit` | 1–50，默认 20；前端提供 Top 20 / Top 50 |
| `mode` | 可选 `osu`、`taiko`、`fruits`、`mania`；省略时读取玩家首选模式，catch 对应 `fruits` |

成功响应包含 `player`、实际解析的 `mode`、`type`、`scores` 和 `fetched_at`。完整字段以 [Python 响应模型](apps/api/app/schemas/scores.py)和 [TypeScript 类型](apps/web/src/types.ts)为准；运行中的 OpenAPI 位于 API 服务的 `/openapi.json`。

- 成绩 `accuracy` 为 0–1，玩家 `hit_accuracy` 为 0–100。
- pp、排名等不可用字段保留 `null`，页面显示 `—`。
- `star_rating` 是基础 SR；rank 的 `X` / `XH` 映射为 `SS` / `SSH`。
- 时间使用 ISO 8601，页面按浏览器本地时间显示。
- `X-Cache` 为 `MISS`、`HIT` 或 `BYPASS`（缓存写入失败）；`X-Cache-TTL` 表示剩余可复用秒数。

错误格式：

```json
{"error":{"code":"PLAYER_NOT_FOUND","message":"未找到该玩家，请检查用户名或 ID。"}}
```

| HTTP | 错误代码 | 含义 |
| --- | --- | --- |
| 404 | `PLAYER_NOT_FOUND` | 玩家不存在 |
| 422 | `INVALID_PLAYER` / `INVALID_REQUEST` / `INVALID_CREDENTIALS` | 玩家输入、查询参数或个人凭据格式不合法 |
| 429 | `RATE_LIMITED` | 本地限流，附带 `Retry-After` |
| 502 | `UPSTREAM_ERROR` | OAuth、osu! 请求或上游数据解析失败 |
| 503 | `NOT_CONFIGURED` | 未提供可用的服务端凭据配置，也未提交个人凭据 |
| 503 | `SERVER_BUSY` / `UPSTREAM_BUSY` | 查询并发繁忙、上游预算不足或冷却中，附带 `Retry-After` |

## 缓存与运行限制

服务端将结构化成绩写入 JSON 文件。用户名和 ID 共用结果，Top 20 / Top 50 共用最多 50 条成绩的缓存；四种模式隔离，自动模式使用独立缓存键，并同时写入解析出的模式缓存。

默认在 **60 秒**内复用相同玩家、相同模式的结果，过期后由下一次主动查询刷新；没有后台轮询，也不会在上游失败时返回过期成绩。文件默认保留 **180 天**，刷新会覆盖旧结果，因此这不是成绩历史归档。查询或写入时至多每小时扫描清理一次过期文件，没有磁盘容量配额。玩家不存在的结果另缓存 60 秒。

浏览器仅在内存中缓存成功响应，最多 50 个键、最长 60 秒，且不超过服务端 `X-Cache-TTL`。刷新页面会清除成绩内存缓存。

网页头像与曲绘直接从 osu! 官方图片站点加载。成绩查询响应发出后，服务端将本次返回的头像和曲绘加入去重的后台队列（最多 256 张待处理素材），按现有限速预缓存；成绩及玩家资料继续使用 JSON 缓存。预缓存失败不影响查询结果或网页展示。

图片导出通过同源 `/api/v1/images?url=…` 读取服务端缓存，不依赖图片站点的 CORS 支持。服务端在 `CACHE_PATH/images` 中缓存图片 24 小时，浏览器按剩余有效期缓存；磁盘文件沿用 `CACHE_RETENTION` 保留策略（至少 24 小时）。后台预缓存和导出请求共用缓存及并发锁，避免重复回源；导出会合并重复曲绘，最多同时加载两张素材。仅允许 osu! 官方头像与曲绘地址，不跟随重定向，单张图片上限 5 MiB。图片请求排队最多等待 75 秒，繁忙或加载失败会提示重试下载。

所有成绩查询，包括缓存命中，都受 IP 与玩家输入限流。上游 OAuth、玩家详情和成绩共用 API 请求预算，默认最多 60 次/分钟、至少间隔 1 秒；失败请求也计入。该预算遵循 [osu! API 使用要求](https://osu.ppy.sh/docs/#terms-of-use)。图片 CDN 使用独立的同等限速预算，避免头像、曲绘预加载及图片 429 冷却阻塞查分。成绩缓存未命中通常需要 2 次上游请求，获取 token 时需要 3 次；图片缓存命中不占用上游预算。上游返回 429 后，对应的 API 或图片预算遵守 `Retry-After` 进入冷却，图片请求排队等待，不进行快速重试。

60 秒缓存复用不是搜索冷却：可以立即查询其他玩家。使用自己的 API 凭据仍受站点 IP / 玩家限流和 API 总预算约束；密钥错误会提示核对凭据，前端支持显示 / 隐藏 Client Secret。服务繁忙时自动退避最多 10 秒，另加最多 2 秒随机错峰；若上游要求更长的 `Retry-After`，仍遵守该时间。

**必须以单 worker、单副本运行**：全站请求预算、并发锁和统计锁均位于进程内。上游查询串行执行，繁忙时立即返回 503；浏览器保留输入并重试，服务端不建立排队任务。取消浏览器查询不能撤销已经发出的上游请求。扩容前需要实现共享限流和锁，OAuth 凭据也应由本服务独占使用。

## 查看后台日志

应用日志直接输出到容器标准错误流，Docker 和 Portainer 均可查看，无需开启额外接口。在仓库根目录执行：

```sh
# 实时查看 API 日志，先显示最近 200 行
docker compose logs -f --tail=200 api

# 查看最近 10 分钟的 API 和 Nginx 日志
docker compose logs --since=10m api web
```

使用 Portainer 时，进入 **Containers → API 容器 → Logs**，打开自动刷新。镜像部署在 `deploy` 目录运行同样的命令，或加上 `-f deploy/compose.yaml --env-file deploy/.env.deploy`。

API 默认每行输出一条**英文易读日志**：UTC 时间、级别、模块、请求编号、事件说明和可搜索的 `key=value` 字段。失败时补充英文 `error_reason` 和 `next_step`，说明原因与处理建议。例如（编号和耗时仅为示例）：

```text
2026-10-19T10:00:00.000+00:00 INFO    [app.routers.players] request_id=abc123 Scores ready to return to the browser | event=scores_ready mode=mania limit=20 score_count=20 cached_score_count=50 cache=HIT cache_age_seconds=12.3
2026-10-19T10:00:01.000+00:00 WARNING [app.main] request_id=def456 Request completed with an error | event=request_completed status=503 error_code=SERVER_BUSY retry_after=3 error_reason="Another score lookup is already running" next_step="Wait retry_after seconds; the browser retries automatically"
```

`request_started` 到 `request_completed` 之间的同一次查询使用相同的 `request_id`。响应头 `X-Request-ID` 可在浏览器开发者工具 **Network → 请求 → Headers** 中找到。`duration_ms` 是阶段耗时，`wait_ms` 是等待限速或排队的耗时，单位均为毫秒；`retry_after`、`cache_ttl` 和 `cache_age_seconds` 的单位是秒。健康检查成功时不写请求日志。

需要查看更细的限速间隔、上游请求开始、图片缓存命中和后台队列时，在 API 使用的环境文件中设置：

```dotenv
LOG_FORMAT=text
LOG_LEVEL=DEBUG
```

需要保留原来的结构化输出时，设置 `LOG_FORMAT=json`；JSON 同样包含英文 `message`、错误原因和处理建议。修改配置后执行 `docker compose up -d --build api`，日志级别也可设为 `WARNING` 或 `ERROR` 来减少输出。`LOG_LEVEL` 只控制本应用日志，不开启可能包含原始 URL 的第三方库调试日志。

遇到等待或失败时，关注以下字段：

| 事件 / 字段 | 含义 |
| --- | --- |
| `scores_query_started` / `mode`、`limit` | 查询开始；`auto` 表示读取玩家首选模式 |
| `scores_cache_lookup` / `cache` | `HIT` 复用缓存，`MISS` 需要进一步检查不存在缓存或请求上游 |
| `negative_cache_hit` / `cache_ttl` | 最近已确认玩家不存在，直接复用 404 |
| `scores_ready` / `score_count`、`cached_score_count` | 实际返回条数与完整缓存条数，附带解析后的模式和缓存年龄 |
| `oauth_token_requested` / `oauth_token_reused` | 区分重新获取 OAuth token 和复用站点 token |
| `oauth_token_invalidated` | 站点 token 被上游拒绝；下次查询会重新获取 |
| `local_rate_limited` / `scope` | 站点 IP 或玩家限流，`retry_after` 是剩余秒数 |
| `upstream_wait` / `reason=budget_exhausted` | 本服务的上游请求预算已耗尽 |
| `upstream_wait` / `reason=upstream_cooldown` | 正在遵守上游 429 冷却 |
| `upstream_rate_limited` / `budget` | osu! API 或图片返回 429，`api` 与 `images` 分别计数 |
| `upstream_rate_limited` / `fallback=true` | 上游未给出有效 `Retry-After`，保守等待 60 秒 |
| `osu_http_completed` / `phase`、`status` | `oauth`、`player`、`scores` 分别表示认证、玩家资料和成绩阶段；例如 OAuth 401 表示凭据被拒绝 |
| `image_http_completed` / `bytes`、`media_type` | 图片下载大小、类型和耗时 |
| `image_fetch_wait` / `image_queue_timeout` | 图片等待请求额度，或排队超过 75 秒 |
| `images_enqueued` / `added`、`skipped`、`dropped` | 后台图片队列新增、跳过、因队列已满而丢弃的数量 |
| `cache_entry_invalid` / `cache_read_failed` | 缓存文件损坏或不可读，作为未命中继续查询 |
| `scores_cache_write_failed` / `image_cache_write_failed` / `usage_write_failed` | 缓存或统计写入失败；当前查询仍尽量返回已获取的数据 |
| `request_failed` / `error_type`、`error_trace`、`error_errno` | 异常类型、应用内相对文件／行号／函数，以及适用时的系统错误编号 |

两种格式均不记录用户名、玩家 ID、IP、访客标识、Client ID、密钥、token、原始 URL、查询参数或上游响应正文。异常仅记录类型和安全的代码位置，不输出原始异常文字、源码行或局部变量。后台图片预缓存独立运行，其日志可能没有用户请求编号；预缓存失败不会影响成绩查询。Nginx 与 Uvicorn 的原始访问日志继续关闭，避免将查询路径中的玩家信息写入日志。Compose 对每个容器启用日志轮转，最多保留 3 个、每个 10 MB 的日志文件；重建容器后旧日志不保证保留。

## 项目结构与检查

```text
apps/web/          React 页面、国际化、B20/B50 导出和前端测试
apps/api/          FastAPI、osu! 客户端、缓存、限流和后端测试
compose.yaml       从源码构建的默认部署入口
deploy/            Nginx 配置、GHCR 部署、更新脚本与部署文档
DEVELOPMENT.md     后续开发与运行维护建议
```

首页说明可在 `apps/web/src/content/intro.md` 和 `intro.en.md` 修改，界面译文位于 `apps/web/src/i18n.ts`。开发环境自动更新，生产环境需要重新构建。前端构建产物位于 `apps/web/dist`，生产部署由 Nginx 提供服务。

在仓库根目录检查前端：

```sh
npm run typecheck
npm run lint
npm test
npm run build
```

在 `apps/api` 检查后端：

```sh
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

自动测试不需要真实 osu! 凭据。部署配置可用 `docker compose config --quiet` 检查；实际容器启动和真实成绩查询仍需分别验证。前端格式化命令为 `npm run format`，后端为 `uv run ruff format .`，执行时会修改文件。

查询思路参考 [Rarverse/osu-score-fetch](https://github.com/Rarverse/osu-score-fetch)，osu! 数据来自 [osu! API v2](https://osu.ppy.sh/docs/)。
