# Raru 查分器

一个支持 osu! 四种模式的玩家查分网页工具。输入用户名或 ID，即可查看 **Best 20 / Best 50**，并导出 B20 / B50 PNG 图片。

React + TypeScript + Vite · FastAPI + ossapi · Nginx · Docker Compose

[快速部署](#快速部署) · [本地开发](#本地开发) · [环境配置](#环境配置) · [API](#api) · [运行维护](docs/operations.md) · [部署详情](deploy/README.md)

## 功能

- **四种模式**：osu!、osu!taiko、osu!catch、osu!mania；可读取玩家默认模式或手动选择。
- **玩家与成绩概览**：查看玩家 pp、全球排名、准确率，以及成绩的 pp、准确率、mods、评级、combo 和谱面基础 SR；评级与星级配色在网页和导出图中保持一致。
- **B20 / B50 图片导出**：生成带头像、曲绘和当前模式累计游玩时长的 PNG；B20 使用双列布局，B50 使用五列布局，统一采用深色渐变与柔光几何纹样背景；支持素材加载进度、折叠预览、再次下载和失败重试，不足所选数量时按实际条数导出。
- **连续查询**：同一玩家切换模式或成绩数量后自动查询；查询中保留上次结果，首次查询展示骨架屏，支持取消、失败重试和繁忙倒计时。
- **最近查询**：在当前浏览器保存最近 5 位成功查询的玩家，可单独删除或清空；支持 `Ctrl / ⌘ + K` 聚焦搜索和长列表快捷导航。
- **中英文与移动端**：按浏览器语言选择中文或英文，提供响应式布局、键盘菜单操作与减少动态效果支持。
- **可自托管**：无需玩家登录；支持共享的服务端 OAuth 凭据，也可由访客临时提供个人凭据。

当前版本 **v0.2.0**，页脚版本号读取 `apps/web/package.json`。

仅查询 `best` 成绩，最多 50 条。SR 为未应用 mods 的谱面基础难度，pp 使用 osu! 返回值。相同玩家、相同模式的成绩默认复用 3 分钟，缓存到期后再次查询才会刷新；期间可以继续查询其他玩家。

## 快速部署

需要 Docker Engine 和 Docker Compose 插件（Compose ≥ 2.24.0）。克隆仓库后执行：

```sh
git clone https://github.com/Rarverse/osu-score-fetch-GUI.git
cd osu-score-fetch-GUI
docker compose up -d
```

首次启动会从源码构建前后端，打开 [http://127.0.0.1:8080](http://127.0.0.1:8080)。宿主机无需安装 Node.js、Python 或 uv。

**无需服务端凭据也能启动页面，但查询需要 OAuth 凭据。** 可以在页面中临时填写个人凭据，或为站点配置共享凭据：

```sh
cp .env.example .env
chmod 600 .env
```

编辑 `.env`，取消注释并填写 `OSU_CLIENT_ID` 和 `OSU_CLIENT_SECRET`。凭据来自 [osu! 账号设置](https://osu.ppy.sh/home/account/edit) 中的 OAuth 应用，使用 Client ID / Client Secret，而非旧版 API Key。项目使用 client credentials grant 与 `public` scope，无需玩家登录授权。

如需公开部署，将 `VITE_SITE_URL` 设置为公网根地址，例如 `https://scores.example.com`，然后重建：

```sh
docker compose up -d --build
```

`VITE_SITE_URL` 会在构建时写入分享元数据，修改后需要重建 web 镜像。完整配置见 [.env.example](.env.example)。

### 域名与 HTTPS

```text
访客 → 外部 HTTPS 反向代理 → web:80（Nginx）→ api:8000
```

默认映射为 `127.0.0.1:8080:80`：宿主机监听 `127.0.0.1:8080`，容器内 Nginx 监听 `80`。同机外部反代的上游填写 **`http://127.0.0.1:8080`**，保留请求路径。

域名、HTTPS 和证书由外部 Nginx 或雷池处理；项目内部提供 HTTP，API 的 8000 端口不对宿主机发布。外部反代若位于独立 bridge 容器，接入方式和可信代理设置见[部署说明](deploy/README.md#反代在独立-bridge-网络容器)。

### 验证与更新

```sh
docker compose ps
curl -fsS http://127.0.0.1:8080/health
docker compose logs --tail=100
```

`/health` 返回 200 仅表示 API 存活。要验证 OAuth 和上游连接，还需在页面完成一次真实查询。

更新时执行：

```sh
git pull
docker compose up -d --build
```

成绩、图片缓存和使用统计保存在命名卷 `osu-score-api_osu-data`。重建容器或 `docker compose down` 会保留数据，**`docker compose down -v` 会删除数据卷**。

根目录 `compose.yaml` 从源码构建；`deploy/compose.yaml` 用于 GitHub Actions / GHCR 镜像部署。镜像更新、备份、迁移和回滚见[部署文档](deploy/README.md)，缓存、日志与请求限制见[运行维护](docs/operations.md)。

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
| `OSU_CLIENT_ID` / `OSU_CLIENT_SECRET` | 无 | 第一组服务端 OAuth 凭据，须成对配置 |
| `OSU_CLIENT_ID_2` / `OSU_CLIENT_SECRET_2` | 无 | 可选第二组凭据，须成对配置 |
| `OSU_CLIENT_ID_3` / `OSU_CLIENT_SECRET_3` | 无 | 可选第三组凭据，须成对配置 |
| `LOG_FORMAT` | `text` | 英文易读日志；设为 `json` 可接入日志采集工具 |
| `LOG_LEVEL` | `INFO` | `DEBUG`、`INFO`、`WARNING` 或 `ERROR`；`DEBUG` 增加请求发起、限速间隔和图片队列细节 |
| `CACHE_TIMEOUT` | `180` | 成绩查询结果复用窗口，默认 3 分钟，单位秒，最小为 60 |
| `CACHE_RETENTION` | `15552000` | 成绩与图片缓存文件从最后写入起的保留期，默认 180 天，不得短于复用窗口 |
| `CACHE_PATH` | `apps/api/.cache` | 本地默认缓存目录 |
| `STATS_PATH` | `apps/api/data/cache/usage.json` | 本地默认匿名统计文件 |
| `NEGATIVE_CACHE_TTL` | `60` | 玩家不存在结果的缓存时长，单位秒 |
| `RATE_LIMIT_WINDOW` | `60` | 本地限流窗口，单位秒 |
| `RATE_LIMIT_GLOBAL` | `120` | 全站在窗口内允许的成绩请求次数 |
| `RATE_LIMIT_PER_IP` | `20` | 每个 IP 在窗口内允许的查询次数 |
| `RATE_LIMIT_PER_PLAYER` | `10` | 每个规范化玩家输入在窗口内允许的查询次数 |
| `RATE_LIMIT_UPSTREAM_COST_PER_IP` | `30` | 每个 IP 的上游成本额度；一次实际缓存未命中保守计 3 |
| `RATE_LIMIT_IMAGES_GLOBAL` | `300` | 全站在窗口内允许的图片请求次数 |
| `RATE_LIMIT_IMAGES_PER_IP` | `120` | 每个 IP 在窗口内允许的图片请求次数，可覆盖一次 B50 导出 |
| `OSU_REQUESTS_PER_MINUTE` | `60` | API 与图片各自的请求预算，可设为 3–60 |
| `CORS_ORIGINS` | localhost 与 127.0.0.1 的 5173 端口 | 允许来源，使用 JSON 字符串数组 |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | API 信任的代理 IP / CIDR，逗号分隔 |

表中的本地默认路径相对于仓库位置描述；**自行填写的相对路径按 API 进程工作目录解析**。Compose 将 `CACHE_PATH`、`STATS_PATH` 固定到数据卷中的 `/var/lib/osu-score-api/cache` 和 `/var/lib/osu-score-api/stats/usage.json`，并根据 `WEB_IPV4` 设置 API 代理信任地址。

## 凭据与隐私

服务端密钥保存在未提交的环境文件中，不能放进 `VITE_` 变量，这类变量会公开到前端构建产物。

页面中的个人 Client ID / Client Secret 仅保存在当前页面内存，刷新或关闭后清除；查询时通过 `X-Osu-Client-Id` / `X-Osu-Client-Secret` 请求头发送给后端，由后端换取 token。浏览器 Network 面板能够看到自己提交的凭据。服务端不将个人凭据写入文件，OAuth token 也不写入 ossapi 的 pickle 文件。公开站点使用个人凭据需要 HTTPS，本机开发地址除外。

个人凭据仅在缓存未命中时用于上游请求；命中时复用同一份公开成绩，不会再次验证凭据。个人凭据与服务端凭据共用缓存、限流和全站请求预算。

最近查询记录（玩家 ID、用户名、头像 URL 和查询模式）保存在当前浏览器的 `localStorage` 中，不包含 API 凭据；可通过页面删除或清空。成绩响应与导出预览的临时 Blob URL 仅缓存在页面内存中，刷新后清除；已经下载的 PNG 由浏览器或用户保存，不会随页面刷新删除。

浏览器还在 `localStorage` 中保存随机匿名访客 ID（`rarsu-visitor-id`），查询时通过 `X-Visitor-Id` 发送。服务端只对通过参数校验和全部站点限流的查询按 UTC 日期统计查询数、成功查询的去重玩家数、各模式查询数和回访访客数；访客 ID 与成功查询的玩家 ID 以加盐 SHA-256 保存，统计文件不含原始用户名、访客 ID 或 IP。统计使用滚动 180 天窗口，在下次统计写入时清理窗口外数据，并最多保留 10,000 个访客哈希；站点没有后续查询时，旧文件不会自行定时删除。

浏览器缓存命中不产生后端请求，因此不会新增服务端统计。统计文件没有管理页面或查询接口，写入失败不影响成绩返回。成绩与图片缓存包含公开玩家资料、成绩和素材；文件最后写入满 180 天后，由后续缓存操作触发清理。备份时应同时考虑缓存和统计文件。

页面样式会向 Google Fonts 请求 DM Sans 与 Space Grotesk；正常页面展示的头像和曲绘会由浏览器直接请求 osu! 官方图片域名，PNG 导出则通过本站同源图片缓存。第三方会收到完成请求所需的网络信息，其处理和保留规则由相应服务决定。内置部署 Nginx 发送 `Referrer-Policy: no-referrer`，不随这些请求发送当前页面地址。

应用日志会记录原始玩家查询值，以及成功解析后的公开用户名和玩家 ID，便于排障；不会记录个人 API 密钥、原始访客 ID、访问 IP、OAuth token 或图片 URL。默认 Docker 日志按 10 MiB、最多 3 个文件轮换，不承诺固定天数；外层反向代理和第三方服务的日志策略由部署者或服务提供方负责。

开发者工具能够看到公开 API 路径和浏览器发出的请求，这是网页应用的正常行为，不能作为安全边界。服务端对成绩请求设置全站、每 IP、每玩家和实际缓存未命中的上游成本限流；图片请求在读取缓存前设置全站与每 IP 限流。查询参数不影响同一官方图片的缓存身份，避免用无意义参数制造永久缓存文件。

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
| `limit` | 1–50，默认 20；前端提供 Best 20 / Best 50 |
| `mode` | 可选 `osu`、`taiko`、`fruits`、`mania`；省略时读取玩家首选模式，catch 对应 `fruits` |

成功响应包含 `player`、实际解析的 `mode`、`type`、`scores` 和 `fetched_at`。完整字段以 [Python 响应模型](apps/api/app/schemas/scores.py) 和 [TypeScript 类型](apps/web/src/types.ts)为准；运行中的 OpenAPI 位于 API 服务的 `/openapi.json`。

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

## 项目结构与检查

```text
apps/web/          React 页面、国际化、B20/B50 导出和前端测试
apps/api/          FastAPI、osu! 客户端、缓存、限流和后端测试
compose.yaml       从源码构建的默认部署入口
deploy/            Nginx 配置、GHCR 部署、更新脚本与部署文档
docs/operations.md 缓存、请求限制、日志与运行维护
DEVELOPMENT.md     持续开发建议
```

首页说明可在 `apps/web/src/content/intro.md` 和 `intro.en.md` 修改，界面译文位于 `apps/web/src/i18n.ts`。修改后重启开发服务或等待热更新，生产环境需要重新构建。前端构建产物位于 `apps/web/dist`，生产部署由 Nginx 提供服务。

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

## 致谢与声明

查询思路参考 [Rarverse/osu-score-fetch](https://github.com/Rarverse/osu-score-fetch)，数据来自 [osu! API v2](https://osu.ppy.sh/docs/)。

Raru 查分器由 Rarverse 维护，是非官方 fan-made 项目，与 peppy / osu! 无隶属关系。

## 许可证

Copyright © 2026 Rarverse.

本项目以 [GNU AGPLv3（AGPL-3.0-only）](LICENSE) 发布，允许使用、修改和商用。分发修改版时须遵守 AGPLv3 的源码提供要求；修改后通过网络提供服务时，也须向使用该服务的用户提供对应源码的获取方式。

核心依赖 [ossapi](https://github.com/liam-devoe/ossapi) 使用 AGPLv3。第三方依赖、osu! 数据、头像与谱面曲绘仍适用各自的许可或使用条款。

## Publicity Community

[LINUX DO](https://linux.do/)
