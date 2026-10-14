# Rarsu查分器

rarverse 旗下的非官方 fan-made 网页查分器。网站名称为 **Rarsu查分器**。输入玩家用户名或 ID，查看 **osu! / taiko / catch / mania best performance**、pp、accuracy、mods、基础 SR、rank 和 combo。与 peppy / osu! 无隶属关系。

支持四种模式切换，默认 mania。按后续要求扩展了原始 mania MVP；没有账号系统或批量抓取接口。

界面按浏览器语言偏好自动选择中文或英文（识别 `zh-*` / `en-*`，无匹配时使用英文），包括标题、输入提示、错误、等待页和成绩说明。译文位于 `apps/web/src/i18n.ts`。

中文首页文案在 `apps/web/src/content/intro.md`，英文在 `intro.en.md`。页面按浏览器语言渲染其中一份 Markdown（段落、链接、列表；不执行原始 HTML）。开发服务会自动更新，生产需要重新构建。

`apps/web/index.html` 的标题是「Rarsu查分器」。`description` 和 `og:description` 使用中文介绍的第一句；英文浏览器加载后，现有的语言逻辑会把这两条 meta 换成英文第一句。`og:title` 固定为 `Rarsu查分器 / Rarsu Score Checker`，`og:image` 指向 `/og.png`（另有 `public/og.svg`），`og:type` 为 `website`，`twitter:card` 为 `summary_large_image`。

`og:image` 和 `og:url` 在构建时由 `VITE_SITE_URL` 拼成绝对地址，例如 `VITE_SITE_URL=https://scores.example.com` 得到 `https://scores.example.com/og.png`。本地开发不设置该变量时回退为 `/og.png` 和 `/`，页面本身仍可用；发给社交平台的生产构建必须带上站点根地址。模式按钮使用页面内的简易 SVG，选中项为 `#c9b2ff`，当前模式标记的底色是 `#101116`。

## 本地启动

要求：Python ≥ 3.12、[uv](https://docs.astral.sh/uv/)、Node.js ≥ 20.19、npm。

在仓库根目录安装前端依赖：

```sh
npm ci
```

在第一个终端启动后端：

```sh
cd apps/api
uv sync --locked
cp .env.example .env
# 编辑 .env，取消注释并填入 OSU_CLIENT_ID / OSU_CLIENT_SECRET
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

在第二个终端，从仓库根目录启动前端：

```sh
npm run dev
```

打开 http://127.0.0.1:5173。Vite 将 `/api` 和 `/health` 代理到 http://127.0.0.1:8000。API 交互文档：http://127.0.0.1:8000/docs；实时 OpenAPI：http://127.0.0.1:8000/openapi.json。

`apps/api/.env` 无需前端配置。未配置 OAuth 时 `/health` 仍可用，查询返回 `503 NOT_CONFIGURED`；不返回演示成绩。部署者可以配置服务端凭据，也可以让访客在页面中填写自己的凭据。

## Docker Compose

在仓库根目录启动整套服务：

```sh
cp .env.example .env
# 编辑 .env。osu! Client ID / Secret 不要写在这里，也不要使用 VITE_ 前缀。
docker compose up -d
```

停止：

```sh
docker compose down
```

项目名固定为 `osu-score-api`，已有的 `osu-score-api_osu-data` 卷会继续使用。Web 只监听 `127.0.0.1:8080`。HTTPS 仍由反向代理 SafeLine 处理，本仓库不申请、也不保存证书。SafeLine 上游填 `http://127.0.0.1:8080`。变量、密钥文件、回滚，以及从 `.env.deploy` 迁移的步骤见 `deploy/README.md`。服务器上的 `DEPLOY_DIR` 必须就是手工执行 compose 的那个目录，只保留这一份，否则两个项目会抢 8080。

## 环境变量与密钥

在 [osu! 账号设置](https://osu.ppy.sh/home/account/edit) 创建 OAuth 应用。服务端以 client credentials grant 获取 `public` scope，用户无需登录。

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `OSU_CLIENT_ID` | 无 | 服务端 OAuth client ID |
| `OSU_CLIENT_SECRET` | 无 | 服务端 OAuth secret |
| `CACHE_TIMEOUT` | `60` | 相同查询的合并窗口（秒）；至少 60 秒，窗口过后由主动查询触发刷新 |
| `CACHE_RETENTION` | `15552000` | 缓存文件保留 180 天；不得短于 `CACHE_TIMEOUT` |
| `CACHE_PATH` | `apps/api/.cache` | 缓存目录；自定义相对路径按启动工作目录解析 |
| `STATS_PATH` | `apps/api/data/cache/usage.json` | 每日匿名使用统计 JSON；相对路径按启动工作目录解析 |
| `NEGATIVE_CACHE_TTL` | `60` | 玩家不存在结果的缓存秒数 |
| `RATE_LIMIT_WINDOW` | `60` | 限流窗口（秒） |
| `RATE_LIMIT_PER_IP` | `20` | 每个 IP 在窗口内允许的查询次数 |
| `RATE_LIMIT_PER_PLAYER` | `10` | 每个规范化玩家输入在窗口内允许的查询次数 |
| `OSU_REQUESTS_PER_MINUTE` | `60` | 全站向 osu! 发送的 HTTP 请求预算；可设 3–60，超过 60 拒绝启动 |
| `CORS_ORIGINS` | localhost 与 127.0.0.1 的 5173 端口 | JSON 数组格式的允许来源 |

服务端密钥由 `apps/api/app/config.py` 读取。页面中的可选 Client ID / Client Secret 只保存在当前页面运行内存，查询时通过 HTTPS 请求头发送；关闭或刷新页面后需要重新输入。后端只用这些凭据换取本次查询的 OAuth token，不写入文件或复用为服务端凭据。请勿在非 HTTPS 的公开站点输入 secret；localhost 开发环境例外。OAuth token 不写入 ossapi 的 pickle 文件，API 响应不包含 secret。不要使用 `VITE_` 前缀保存任何密钥。`.env`、`.cache`、虚拟环境和构建产物均已忽略。

用户可在页面展开「使用自己的 osu! API」，从 [osu! 账号设置](https://osu.ppy.sh/home/account/edit) 创建仅需 `public` scope 的 OAuth 应用并填入 Client ID 与 Client Secret。两项凭据必须同时提供；用户凭据只用于缓存 miss 的上游查询。服务端仍对所有凭据共用同一全站 60 次/分钟请求预算、请求间隔、并发锁、缓存和限流，个人凭据不会绕过服务限额。缓存命中返回相同的公开数据，不会再次验证所填凭据。

## 隐私与使用统计

为了回答「有没有人会回访」，每次成绩查询会计入按 UTC 日期汇总的计数。没有管理页面，也没有查询这些计数的接口。

浏览器把随机匿名 ID 放在 `localStorage`（键 `rarsu-visitor-id`），只在成绩请求上通过 `X-Visitor-Id` 发送。服务端保存的是该 ID 和成功查询所得玩家 ID 的加盐 SHA-256，用来去重和判断回访；统计文件里没有原始用户名、原始访客 ID 或 IP。同一访客如果在更早的 UTC 日期出现过，当天记为回访一次，同一天多次查询不重复累加。

每天的汇总包含：查询总数、成功查询的去重玩家数、各模式查询数、回访访客数。404、限流和其他失败只计入查询总数和对应模式，不计入去重玩家。成功查询按玩家 ID 去重，所以用用户名或数字 ID 查到同一个人只算一个玩家。

默认路径是 `STATS_PATH`（`apps/api/data/cache/usage.json`）。`apps/api/data/cache/` 和 `data/cache/` 已写入 `.gitignore`，不要提交统计文件。生产环境把 `CACHE_PATH` 和 `STATS_PATH` 指到 `/var/lib/osu-score-api/`，见 `deploy/README.md`。写入使用进程内锁和原子替换，只适合单 worker；统计写失败不影响查询结果。

未找到的玩家会负缓存约 60 秒（`NEGATIVE_CACHE_TTL`）。窗口内再次查询任意模式都返回相同的 404 `PLAYER_NOT_FOUND`，带 `Cache-Control: no-store`，并用 `X-Cache` 标出 `MISS` 或 `HIT`。其他错误不写入这份缓存。

## API 契约 v1

`GET /health` → `200 {"status":"ok","modes":["osu","taiko","fruits","mania"]}`，表示进程存活，不表示 OAuth 或上游已联通。

`GET /api/v1/players/{username}/scores?type=best&limit=20&mode=mania`

- `username`：URL 编码后的用户名或 ID，去除首尾空格，大小写不敏感。
- `mode`：`osu` / `taiko` / `fruits` / `mania`，默认 `mania`。UI 的 catch 使用 API 值 `fruits`。切换模式会重新查询当前已展示的玩家。
- `type`：仅 `best`；不提供分页、recent 或批量接口。
- `limit`：1–50，默认 20。一次上游最多拉 50 条，返回前按 limit 切片。
- 响应头 `X-Cache-TTL`：当前结果剩余可复用秒数，供浏览器缓存使用。
- 响应头 `X-Cache`：`MISS` / `HIT` / `BYPASS`（缓存写入失败）；`Cache-Control: no-store` 防止浏览器缓存影响服务端观测。
- 返回值由 Pydantic `ScoresResponse` 约束；前端契约位于 `apps/web/src/types.ts`。

示例仅用于说明字段：

```json
{
  "player": {
    "user_id": 123,
    "username": "Player",
    "country": "CN",
    "avatar_url": "https://a.ppy.sh/123",
    "pp": 5432.1,
    "global_rank": 1000,
    "hit_accuracy": 98.76
  },
  "mode": "mania",
  "type": "best",
  "scores": [{
    "score_id": 456,
    "beatmap_id": 789,
    "beatmap_title": "Song",
    "artist": "Artist",
    "version": "4K Hard",
    "cover_url": null,
    "star_rating": 4.52,
    "accuracy": 0.9876,
    "pp": 200.5,
    "rank": "S",
    "mods": ["DT"],
    "max_combo": 1234,
    "played_at": "2026-10-10T01:00:00Z"
  }],
  "fetched_at": "2026-10-10T02:00:00Z"
}
```

成绩 `accuracy` 是 0–1；玩家统计 `hit_accuracy` 是 0–100。`pp`、排名、未知谱面字段可以为 `null`，UI 显示 `—`，不会伪造 0。`star_rating` 是 **未应用 mods 的谱面基础 SR**，当前不返回 `star_rating_modded`。rank 将 API 的 `X/XH` 映射为 `SS/SSH`，保留银色 rank。时间为 ISO 8601，页面按浏览器本地时间显示。

错误统一为 `{"error":{"code":"PLAYER_NOT_FOUND","message":"…"}}`：

| HTTP | code | 含义 |
| --- | --- | --- |
| 404 | `PLAYER_NOT_FOUND` | 玩家查询上游返回 404 |
| 422 | `INVALID_PLAYER` / `INVALID_REQUEST` | 输入、mode、type 或 limit 不合法 |
| 429 | `RATE_LIMITED` | 本地短窗限流；`Retry-After` 为等待秒数 |
| 502 | `UPSTREAM_ERROR` | OAuth / osu! 请求失败或上游数据解析失败 |
| 503 | `NOT_CONFIGURED` / `SERVER_BUSY` / `UPSTREAM_BUSY` | 未配置密钥 / 并发查询繁忙 / 上游额度不足或冷却；后两项带 `Retry-After` |

## 缓存与限流

`services/cache.py` 以 SHA-256 键保存 `.cache/<hash>.json`，内容是 `created_at` 和结构化响应 `data`。键包含契约版本、所选模式、best、最多 50 条和规范化玩家标识。首尾空格、大小写、数字 ID 的前导零会归一化；成功查询后用户名和 ID 均写入同一份结果，Top 20 / Top 50 共用缓存。写入使用原子替换；默认 **60 秒内同玩家同模式的重复查询合并复用**，超过窗口后由下次主动查询拉取新成绩，无后台轮询。过期或损坏文件视为 miss，不用过期成绩掩盖上游失败。

服务器文件默认保留 **180 天**，再次刷新会覆盖该玩家/模式的旧结果，不是成绩历史归档。查询或写入时至多每小时扫描清理一次超过保留期的文件；服务完全空闲时会在下一次缓存操作中清理。60 秒刷新合并窗口和 180 天文件保留期分别配置，避免把半年前的成绩显示为最新。官方也将一分钟内反复轮询同一用户列为不当使用，因此保留最小 60 秒合并窗口。

浏览器另有最多 50 个键的内存缓存，按玩家、模式和 limit 区分，用户名与 ID 共用结果。保留时间不超过 60 秒，也不超过服务器 `X-Cache-TTL`；重复查询显示「本地缓存 / Browser cache」，过期后重新请求后端。只缓存成功响应，不缓存错误或等待状态，刷新页面后清空。

根据 [osu! API v2 官方使用条款](https://osu.ppy.sh/docs/#terms-of-use)，调用应不超过 **60 次/分钟，通常每秒 1 次**。本服务为所有四种模式共享一个上游请求预算：包括 OAuth、玩家详情和 best 成绩请求，按实际 HTTP 请求计数（失败请求也计入）。默认严格按至少 1 秒的间隔发送，并检查滚动 60 秒窗口；降低预算会同步延长间隔。普通缓存 miss 消耗 2 次请求，需要获取 token 时为 3 次。开始查询前先检查完整查询所需额度。收到上游 429 后整个预算进入冷却，遵守 `Retry-After` 秒数或 HTTP 日期，缺失或非法时等待 60 秒。

所有查询（包括 HIT）都受 IP 与玩家输入限流。缓存 miss 串行使用共享 ossapi session，同时重查缓存以减少重复上游调用。网络连接 / 读取超时为 5 / 20 秒。图片直接使用 osu! 返回的 URL，后端本轮不代理或缓存图片。

缓存命中无需上游额度，也不会进入等待页。缓存 miss 遇到已有查询或上游预算不足时立即返回 `503 SERVER_BUSY/UPSTREAM_BUSY` 与 `Retry-After`。前端保留用户名、模式和数量，显示等待倒计时，采用指数退避和随机延迟最多自动重试 5 次；可随时取消后续浏览器请求。等待期间不在服务端创建排队任务，也不会虚报队列位置；取消不能撤销已发出的上游请求。其他错误（包括个人 429 限流、缺少凭据）不会自动重试。

**全站预算、限流与并发锁位于进程内，本实现必须单 worker、单副本运行，且 OAuth 凭据应由本服务独占。** 重启进程会重置请求计数。公开部署时在可信反向代理上配置真实 IP：只信任该代理的 forwarded headers，禁止客户端直连后端。多副本或多 worker 部署前应改用 Redis 共享限流和缓存锁；当前单机限流不能保证阻止分布式收割。缓存目录会按保留期清理，但没有容量配额；生产仍需监测磁盘使用量。

## 对照参考仓

只读参考：[Rarverse/osu-score-fetch](https://github.com/Rarverse/osu-score-fetch)，本次核对 main 提交 `ee287362d9228034c0c0116fbd114f6dd9e30430`。旁路 clone 未放入目标仓。

| 参考仓 main.py | 网页实现 |
| --- | --- |
| `get_ossapi_client` | `services/osu_client.py`：服务端 OAuth、内存 token、超时 |
| `get_user_scores` / `search_user` / `get_user_info` | 指定所选模式查玩家、拉 best 50、读取玩家统计 |
| `structure_scores` | 纯映射函数，保留 title、beatmap_id、cover、SR、accuracy、pp、rank、mods，并补充难度名、combo、时间 |
| `beatmap_data_cache.json` 中 beatmaps / beatmapsets / last_update_time | `services/cache.py`：按玩家存储结构化 JSON，包含谱面元数据，以 TTL 刷新 |
| `.cache/beatmap_cover/<id>/cover.jpg`、`.cache/user/<id>/…` | 本轮浏览器直接加载图片 URL，不复制 Pillow 图片缓存 |

使用与参考一致的 `ossapi==5.3.6`。未复制 CLI、Pillow 出图、全局可变谱面字典或调试清缓存命令。当前复用的是拉分、结构化字段和 TTL 缓存思路，四种模式的玩家统计与成绩同时指定 ruleset。osu! API 依据：[官方 API 文档](https://osu.ppy.sh/docs/)。

## 检查与手动验收

前端使用 Biome 统一 lint / format；后端使用 Ruff，Python 导入排序由 Ruff 管理。CSS 使用组件 class 范围，关闭会对不相关组件误报的 `noDescendingSpecificity` 规则。

```sh
# 仓库根目录
npm run typecheck
npm run lint
npm run build
npm run format

# apps/api
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

自动测试覆盖缓存键、60 秒后主动刷新、180 天保留期清理、过期/损坏缓存、成绩字段映射、API 缓存命中、四模式缓存隔离和上游模式参数、60 次全局上限、请求间隔、上游 429 冷却、繁忙响应、限流与错误契约，不需要凭据。真实数据需按以下步骤验收：

1. 配好 `apps/api/.env` 后启动两个 dev 服务；访问 `/health` 确认 200。
2. 输入有公开 mania best 成绩的真实玩家用户名或 ID，切换四种模式，核对对应 osu! 玩家页的 pp 和成绩字段；可以先用已知玩家 `mrekk`（成绩可随时间变化）。
3. 连续请求同一查询，第一次 `X-Cache: MISS`，第二次 `HIT`；切换 limit 为 50 仍命中。
4. 查询不存在的用户名，确认 404 提示；短窗重复查询超过配置阈值，确认 429 和 `Retry-After`。
5. 同浏览器重复相同查询，确认第二次显示本地缓存且不产生新的后端请求；等待 60 秒后再查会触发刷新。分别用中文与英文浏览器语言检查错误、等待页、标题、`html lang` 和成绩说明。
6. 检查浏览器 Network 中无 OAuth secret；前端 `dist` 只有页面资源，OAuth 请求只在 API 进程发起。
7. 多个不同玩家的未缓存查询同时提交：后来的查询显示等待页，倒计时后重试，可取消；已有缓存仍正常返回。上游返回 429 时按 `Retry-After` 冷却，停止发起新上游请求。
8. 检查桌面和手机宽度：提交、加载、等待、错误、空成绩和列表；页脚保留非官方声明。

## 生产与后续

前端 `npm run build` 输出 `apps/web/dist`。自建部署在仓库根目录 `cp .env.example .env` 后执行 `docker compose up -d`：Caddy 托管静态文件并反代 `/api` 与 `/health`，只把 HTTP 绑到 `127.0.0.1:8080`，API 不对宿主机发布端口。HTTPS 由 SafeLine 终止，证书不在本仓库。步骤、GHCR 登录和回滚见 `deploy/README.md`。不要将 `vite preview` 用作生产服务器。本地仍可用 `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1`。生产密钥放在 `/etc/osu-score-api/env`（权限 `600`），缓存和统计放在数据卷 `/var/lib/osu-score-api`，不要写进仓库。

已知限制：仅 best、最多 50 条、基础 SR；没有后台自动轮询、recent、mods 后难度或 Pillow 出图。下一步可先加入有缓存的 mods 难度查询，再做 B50 卡片/图片导出；recent 需要同步扩展契约、缓存键和验收。
