# 运行与维护

[返回项目首页](../README.md) · [部署说明](../deploy/README.md)

## 缓存与运行限制

服务端将结构化成绩写入 JSON 文件。用户名和 ID 共用结果，Top 20 / Top 50 共用最多 50 条成绩的缓存；四种模式隔离，自动模式使用独立缓存键，并同时写入解析出的模式缓存。

默认在 **3 分钟（180 秒）**内复用相同玩家、相同模式的成绩，过期后由下一次主动查询刷新；没有后台轮询，也不会在上游失败时返回过期成绩。成绩文件默认保留 **180 天**，刷新会覆盖旧结果，因此这不是成绩历史归档。查询或写入时至多每小时扫描清理一次过期的成绩文件，没有磁盘容量配额。玩家不存在的结果另缓存 60 秒。已有环境文件如果设置了 `CACHE_TIMEOUT=60`，需改为 `180` 才会使用新的复用时长。

浏览器仅在内存中缓存成功响应，最多 50 个键、最长 180 秒，且不超过服务端 `X-Cache-TTL`。刷新页面会清除成绩内存缓存。

网页头像与曲绘直接从 osu! 官方图片站点加载。成绩查询响应发出后，服务端将本次返回的头像和曲绘加入去重的后台队列（最多 256 张待处理素材），按现有限速预缓存；成绩及玩家资料继续使用 JSON 缓存。预缓存失败不影响查询结果或网页展示。

图片导出通过同源 `/api/v1/images?url=…` 读取服务端缓存，不依赖图片站点的 CORS 支持。服务端在 `CACHE_PATH/images` 中**永久复用有效图片缓存**，没有时间过期或自动清理；已有缓存也直接复用，`CACHE_RETENTION` 不作用于图片。相同 URL 一直使用已缓存内容，文件缺失或损坏时重新下载；图片 URL 变化时缓存为新图片。浏览器收到一年期的 `max-age`，浏览器缓存失效后仍从服务端缓存读取，无需再次回源。后台预缓存和导出请求共用缓存及并发锁，避免重复回源；导出会合并重复曲绘，最多同时加载两张素材。仅允许 osu! 官方头像与曲绘地址，不跟随重定向，单张图片上限 5 MiB。图片请求排队最多等待 75 秒，繁忙或加载失败会提示重试下载。

服务端支持 1–3 组不同的 OAuth 凭据，按实际配置数量在缓存未命中的查询之间依次轮换，空缺的组会跳过。每组独立复用 token；个人凭据不参与轮换，缓存命中不推进轮换。三组仍访问相同的 osu! 官方接口，共用下述请求预算和 429 冷却，因此不保证缩短官方响应时间。

所有成绩查询，包括缓存命中，都受 IP 与玩家输入限流。上游 OAuth、玩家详情和成绩共用 API 请求预算，默认最多 60 次/分钟、至少间隔 1 秒；失败请求也计入。该预算遵循 [osu! API 使用要求](https://osu.ppy.sh/docs/#terms-of-use)。图片 CDN 使用独立的同等限速预算，避免头像、曲绘预加载及图片 429 冷却阻塞查分。成绩缓存未命中通常需要 2 次上游请求，获取 token 时需要 3 次；图片缓存命中不占用上游预算。上游返回 429 后，对应的 API 或图片预算遵守 `Retry-After` 进入冷却，图片请求排队等待，不进行快速重试。

3 分钟成绩缓存复用不是搜索冷却：可以立即查询其他玩家。使用自己的 API 凭据仍受站点 IP / 玩家限流和 API 总预算约束；密钥错误会提示核对凭据，前端支持显示 / 隐藏 Client Secret。服务繁忙时自动退避最多 10 秒，另加最多 2 秒随机错峰；若上游要求更长的 `Retry-After`，仍遵守该时间。

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
