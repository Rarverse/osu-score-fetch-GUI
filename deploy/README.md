# 用 Docker Compose 部署

面向一台自己的 Debian 机器。API 只在 Compose 网络里监听 `8000`，不对宿主机发布端口。web 容器里的 Caddy 只提供明文 HTTP：反代 `/api` 和 `/health`，并托管前端静态文件。

HTTPS is your reverse proxy's job. 容器不读证书，也不把 HTTP 跳到 HTTPS。这台机器上雷池（SafeLine）已经占用宿主机 `80`/`443` 并终止 TLS，Portainer 也在管 Docker。web 只绑 `127.0.0.1:${HTTP_PORT}`（默认 `127.0.0.1:8080`）。公网地址是 `https://scores.rarverse.com`，没有端口。

Compose 项目名固定为 `osu-score-api`（文件里的 `name:`）。在 `/opt/osu-score-api` 里执行和在 Portainer 里用同名 stack，看到的是同一组容器和卷 `osu-data`。

镜像：

- `ghcr.io/rarverse/osu-score-fetch-gui-api:${IMAGE_TAG}`
- `ghcr.io/rarverse/osu-score-fetch-gui-web:${IMAGE_TAG}`

基础镜像按**精确版本标签 + 多架构 index digest** 固定在两个 Dockerfile 里（`python:3.12.13-slim-bookworm`、`ghcr.io/astral-sh/uv:0.13.1`、`node:22.23.3-bookworm-slim`、`caddy:2.10.2`）。更新基础镜像时要同时改标签和 digest。

成绩缓存和匿名统计在命名卷 `osu-data` 上，挂到容器内 `/var/lib/osu-score-api`。`CACHE_PATH` 与 `STATS_PATH` 都指到这个目录，不写进镜像层，换 `IMAGE_TAG` 不会丢掉数据。

生效的 Caddy 配置是构建 web 镜像时复制进去的 `/etc/caddy/Caddyfile`。部署任务也会把仓库里的 `deploy/Caddyfile` 拷到服务器的 `/opt/osu-score-api/Caddyfile`，但 Compose 不把这份文件挂进容器。改服务器上的副本不会改变正在跑的进程，下一次部署也会覆盖它。`TRUSTED_PROXIES` 在容器启动时从环境读入，改完后执行一次 `up -d` 即可，不必为了它重做镜像。

## 1. 安装 Docker

在 Debian 上安装 Docker Engine 和 Compose 插件。下面用 Docker 官方 apt 源，避免发行版里过旧的 `docker.io`：

```sh
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker "$USER"
```

重新登录后 `docker compose version` 应能输出版本号。

## 2. 登录 GHCR

拉取私有或受限镜像时，使用只带 `read:packages` 的 GitHub token。不要把 token 写进仓库、镜像或 `env.deploy`。

```sh
# 从密码管理器或 GitHub Secrets 取出只读 token，粘贴到 stdin
docker login ghcr.io -u YOUR_GITHUB_USER --password-stdin
```

公开镜像可以跳过登录。osu! 的 Client Secret **不**放在 GitHub 仓库里；如果以后有发布镜像的流水线，registry 凭证放 GitHub Secrets，不要写进 workflow 文件的明文。

## 3. 配置文件

```sh
sudo mkdir -p /etc/osu-score-api /opt/osu-score-api
sudo cp deploy/env.example /etc/osu-score-api/env
sudo chmod 600 /etc/osu-score-api/env
sudoedit /etc/osu-score-api/env
```

`/etc/osu-score-api/env` 只给 root 读。填入真实的 `OSU_CLIENT_ID` 和 `OSU_CLIENT_SECRET`。`CACHE_PATH=/var/lib/osu-score-api/cache` 和 `STATS_PATH=/var/lib/osu-score-api/stats/usage.json` 保持指向数据卷。Compose 里的 `environment` 也会把这两个路径设成同一位置，避免有人把缓存写进可替换的镜像层。

浏览器和 API 走同一个站点时，请求是同源的，不用为了端口去改 `CORS_ORIGINS`。公网来源写反代对外的地址，例如 `https://scores.rarverse.com`。

```sh
sudo cp deploy/.env.deploy.example /opt/osu-score-api/.env.deploy
sudoedit /opt/osu-score-api/.env.deploy
```

已经在跑的机器不要整文件覆盖。部署任务每次只改写 `.env.deploy` 里的 `IMAGE_TAG` 一行，其余行会留下。把下面的变量补进现有文件。以前如果写过 `COMPOSE_PROFILES`、`CADDY_MODE`、`HTTPS_PORT`、`PUBLIC_HTTPS_PORT`、`TLS_CERT_DIR`、`SITE_DOMAIN`，删掉这些行。Compose 会读取 `COMPOSE_PROFILES`，留着旧值没有对应的服务。

`.env.deploy` 没有 osu! 密钥：

| 变量 | 作用 |
| --- | --- |
| `IMAGE_TAG` | 要运行的 GHCR 镜像标签。部署任务会改写这一行 |
| `BIND_ADDR` | 宿主机绑定的 IPv4 地址。默认 `127.0.0.1`，只给本机的反代用 |
| `HTTP_PORT` | 宿主机 HTTP 端口，映射到容器 `80`。反代上游用这个端口，默认 `8080` |
| `COMPOSE_SUBNET` / `COMPOSE_GATEWAY` | 本项目网络。默认 `172.31.210.0/24` 和 `172.31.210.1` |
| `WEB_IPV4` | web 容器地址，默认 `172.31.210.10`。API 只信任这个地址上的 `X-Forwarded-For` |
| `TRUSTED_PROXIES` | Caddy 在容器 `80` 上信任的对端，默认 `127.0.0.1` 和网关。不要写成整个公网 |
| `FORWARDED_ALLOW_IPS` | 传给 uvicorn `--forwarded-allow-ips`，与 `WEB_IPV4` 相同 |
| `VITE_SITE_URL` | 只在**本机** `docker compose build` 时写入 `og:image` / `og:url` |

GitHub 上的部署流水线构建 web 镜像时用的是仓库变量 **`SITE_URL`**，不是 `.env.deploy` 里的 `VITE_SITE_URL`。这台机器的 `SITE_URL` 是：

```text
https://scores.rarverse.com
```

改完仓库变量后要发布新的 web 镜像。部署任务会把新的 git sha 写成 `IMAGE_TAG`。只改 `.env.deploy` 里的 `VITE_SITE_URL` 不会改掉已经打进镜像的地址。

`VITE_SITE_URL` 在构建时写进 `index.html`。只 `pull` 已有镜像不会改掉已经打进去的地址。

## 4. 启动

```sh
docker compose --env-file /opt/osu-score-api/.env.deploy -f deploy/compose.yaml pull
docker compose --env-file /opt/osu-score-api/.env.deploy -f deploy/compose.yaml up -d
```

第一次在没有对应 GHCR 标签时，可以在同一命令后加 `build`，或分开执行：

```sh
docker compose --env-file /opt/osu-score-api/.env.deploy -f deploy/compose.yaml build
docker compose --env-file /opt/osu-score-api/.env.deploy -f deploy/compose.yaml up -d
```

部署任务在服务器上的工作目录是 `/opt/osu-score-api`，用的是已拷贝的 `compose.yaml`：

```sh
docker compose --env-file .env.deploy -f compose.yaml pull
docker compose --env-file .env.deploy -f compose.yaml up -d
```

API 容器入口先准备数据目录，再以降权用户 `osu`（uid 10001）启动 **一个** uvicorn worker。进程监听 `0.0.0.0:8000`，但 Compose 没有把该端口映射到宿主机。Caddy 通过服务名 `api:8000` 访问它。Caddy 只听容器内的 `80`。宿主机上看到的是 `127.0.0.1:HTTP_PORT`。上游 Caddy 镜像声明了 `443`，`docker ps` 里可能列出 `443/tcp`，那不是宿主机端口。

改了 `BIND_ADDR`、`HTTP_PORT` 或 `TRUSTED_PROXIES` 之后要 `up -d`，才会重新创建容器并套用新的发布端口。

## 5. 健康检查

API 镜像自带 `HEALTHCHECK`，在容器里用 Python 请求 `http://127.0.0.1:8000/health`。镜像里没有 curl。宿主机上不映射 8000。

部署流水线的检查方式和这个镜像一致：在 `api` 容器里用同一条 Python 请求。仓库变量 `DEPLOY_HEALTH_MODE`、`DEPLOY_HEALTH_URL`、`DEPLOY_API_SERVICE` 仍然可以覆盖。要让检查穿过雷池时，设：

```text
DEPLOY_HEALTH_MODE=host
DEPLOY_HEALTH_URL=https://scores.rarverse.com/health
```

`host` 表示在服务器上用 curl 请求这个 URL。不设这两项时，检查留在 `api` 容器内部，不经过反代，也不需要宿主机上的 8000。

本机确认栈本身：

```sh
cd /opt/osu-score-api
set -a && . ./.env.deploy && set +a
docker compose --env-file .env.deploy -f compose.yaml ps
docker compose --env-file .env.deploy -f compose.yaml logs web --tail=200
curl -sS -D - -o /dev/null "http://127.0.0.1:${HTTP_PORT}/"
curl -sS -D - -o /dev/null "http://127.0.0.1:${HTTP_PORT}/health"
```

`ps` 里 api 应为 `healthy`。web 应为 `Up`。`/` 应是 `200`，`Content-Type` 为 `text/html`。`/health` 应是 `200`，正文为 `{"status":"ok","modes":[...]}`。两条都不应是跳转到 https。`/health` 只接受 GET，`curl -I` 会得到 `405`。

### 外面仍然打不开时

按这个顺序看，停在第一个失败的地方：

1. `docker compose ps`：web 不是 `Up` 就先看 `logs web`。
2. `ss -lntp`：应看到 `127.0.0.1` 上的 `HTTP_PORT`（常见进程名是 `docker-proxy`）。`443` 属于雷池或 Nginx，不属于这个栈。如果 `8080` 出现在 `0.0.0.0` 上，说明 `BIND_ADDR` 不是 `127.0.0.1`，或改完后没有 `up -d`。
3. 上面的两条 `curl`。本机 HTTP 失败，是容器没在听。本机 HTTP 成功、公网 HTTPS 失败，看反代、防火墙和 DNS。
4. 反代的上游是 `http://127.0.0.1:HTTP_PORT`，不要带路径。
5. DNS：`getent hosts scores.rarverse.com` 的 A 记录应是这台机器的公网地址。公网 80/443 放行的是反代，不是这个栈的 `8080`。

## 6. 前面已经有 Nginx、Caddy 或雷池

HTTPS is your reverse proxy's job. Immich 的 Compose 默认公布 HTTP `2283`，TLS 放在反代上，并要求反代转发 `Host`、`X-Forwarded-For`、`X-Forwarded-Proto`。Vaultwarden 的常见示例只绑定 `127.0.0.1:8080:80`，公网 URL 写在 `DOMAIN`。这个栈是同一形状。

`.env.deploy` 里和端口有关的行：

```text
BIND_ADDR=127.0.0.1
HTTP_PORT=8080
```

Caddy 只听容器内的 `80`，不读证书，也不把 HTTP 跳到 HTTPS。改完后 `up -d`。本机 `curl -sS -D - -o /dev/null http://127.0.0.1:8080/health` 的状态应是 `200`。

`ss -lntp` 里这个栈的端口应只出现在 `127.0.0.1:8080`，不应出现在 `0.0.0.0:8080` 或 `443`。

Nginx 示例是 `deploy/nginx.conf.example`。`ssl_certificate` 两行是占位路径，证书文件放在你自己管理的位置，不放进这个仓库。`location /` 原样转发，并设置 `Host`、`X-Real-IP`、`X-Forwarded-For`、`X-Forwarded-Proto`、`X-Forwarded-Host`。不要在反代里去掉 `/api` 或 `/health`。

门口如果也是 Caddy，由它使用证书，再反代到本机 HTTP。它自己会设置 `X-Forwarded-For`、`X-Forwarded-Proto` 和 `X-Forwarded-Host`：

```caddy
scores.rarverse.com {
	reverse_proxy 127.0.0.1:8080
}
```

访问路径是：访客 → 反代（宿主机 `443`）→ 发布在 `127.0.0.1:8080` 的 Caddy。Caddy 在容器里看到的对端是 Docker 网关（默认 `172.31.210.1`），不是访客。`TRUSTED_PROXIES` 只包含这个网关和 `127.0.0.1`。Caddy 从 `X-Forwarded-For` 右侧取第一个不受信任的地址，再只把这个地址传给 API。API 的 uvicorn 使用 `--proxy-headers --forwarded-allow-ips`，允许的地址只有 web 容器（默认 `172.31.210.10`）。别人直接连 API，或从不被信任的地址连 Caddy 时，带上的 `X-Forwarded-For` 不算数。每个 IP 每分钟 20 次查询。

## Behind SafeLine/雷池

在雷池里为 `scores.rarverse.com` 加站点：

1. 上游协议选 HTTP，地址填 `127.0.0.1`，端口填 `.env.deploy` 的 `HTTP_PORT`（默认 `8080`）。上游不要带路径，雷池不会把路径写进反代。
2. 证书只放在雷池上。这个 Compose 栈不提供证书，也不占用宿主机 `443`。
3. 让雷池把真实访客地址放进 `X-Forwarded-For`，并把 `X-Forwarded-Proto` 设为 `https`。源 IP 用雷池自己看到的连接地址，不要改成信任访客带来的 header。
4. 人机验证会挡住分享卡片。给这个站点加白名单，放行路径 `/`、`/index.html`、`/og.png`、`/og.svg`。微信的预览请求经常没有稳定的爬虫 UA，只放行 UA 不够。再按请求头 User-Agent 放行 `Discordbot` 和 `Twitterbot`，避免 Discord 和 X 的抓取被挑战页截住。白名单是「放行」，多条规则各自独立；一条规则里的多个条件是同时满足。
5. 仓库变量 `SITE_URL` 设为 `https://scores.rarverse.com`（没有端口）。然后让部署任务打出新的 web 镜像，或自己用这个地址构建后把新的 `IMAGE_TAG` 写进 `.env.deploy` 再 `up -d`。旧镜像里的 `og:url` 不会跟着变。

本机确认：

```sh
curl -sS -D - -o /dev/null http://127.0.0.1:8080/health
curl -fsS https://scores.rarverse.com/health
ss -lntp
```

第一条应是 `200`，不是跳转到 https。第二条走雷池，也应是 `200`。`ss` 里 `443` 属于雷池，`8080` 只在 `127.0.0.1`。

## Portainer

选一个主人，不要两个一起改同一组容器。

**GitHub Actions 部署。** 仓库变量 `DEPLOY_ENABLED=true` 时，推 main 会覆盖服务器上的 `compose.yaml` 和 `Caddyfile`，并只改 `.env.deploy` 的 `IMAGE_TAG`。Portainer 只用来看容器和日志。不要在 Portainer 里编辑这个 stack、改环境变量或重新部署，否则下一次 Actions 会把改动盖掉，两边还会抢同一个项目名。

**Portainer 部署。** 把仓库变量 `DEPLOY_ENABLED` 设为 `false`（或不设成 `true`），让 Actions 不再连这台机器。然后：

1. 在服务器上放好 `/etc/osu-score-api/env` 和 `/opt/osu-score-api/.env.deploy`。
2. Portainer → Stacks → Add stack。名称填 `osu-score-api`，与 compose 文件里的 `name:` 一致。
3. Web editor 粘贴 `deploy/compose.yaml`。环境变量用 `.env.deploy` 里的键，不要另起一个项目名。
4. 镜像若是私有的，在 Portainer 里登记 ghcr.io 的只读凭据。
5. Deploy the stack。之后改端口只在这一处改，再 Update the stack。

`name: osu-score-api` 固定项目名。无论当前目录是仓库的 `deploy/` 还是 `/opt/osu-score-api`，`docker compose ps` 和 Portainer 列出的都是 `osu-score-api` 这一组。卷名是 `osu-score-api_osu-data`。不要 `down -v`。

以前如果创建过 `osu-score-api_caddy-data` 或 `osu-score-api_caddy-config`，这个栈不再使用它们。不要用 `down -v` 清理，那会连 `osu-data` 一起删掉。

## 7. 回滚

数据卷不动。把 `/opt/osu-score-api/.env.deploy` 的 `IMAGE_TAG` 改回上一个可用标签，然后：

```sh
docker compose --env-file /opt/osu-score-api/.env.deploy -f deploy/compose.yaml pull
docker compose --env-file /opt/osu-score-api/.env.deploy -f deploy/compose.yaml up -d
```

再跑一次上面的健康检查。web 镜像如果是用另一个 `SITE_URL` 构建的，回滚标签也会带回当时写进页面的 OG 地址。Caddyfile 随该镜像里的副本一起回去。

## Usage stats

`deploy/compose.yaml` 把命名卷 `osu-data` 挂到服务 `api` 的 `/var/lib/osu-score-api`，并用 `STATS_PATH` 固定统计文件：

- 容器内：`/var/lib/osu-score-api/stats/usage.json`
- 卷 `osu-data` 内：`stats/usage.json`（卷根对应容器里的 `/var/lib/osu-score-api`）

成绩缓存是同一卷上的 `cache/`（`CACHE_PATH=/var/lib/osu-score-api/cache`）。统计和缓存不在两个卷里。

`api` 已经启动时，把统计文件复制到当前目录：

```sh
docker compose --env-file /opt/osu-score-api/.env.deploy -f deploy/compose.yaml cp api:/var/lib/osu-score-api/stats/usage.json ./stats.json
```

`--env-file` 与上面的启动命令相同：compose 文件会展开 `IMAGE_TAG`。

不要为了清缓存删掉卷 `osu-data`。`docker compose down -v` 和 `docker volume rm` 会把 `usage.json` 和缓存一起删掉。只删除缓存目录，保留 `stats/`：

```sh
docker compose --env-file /opt/osu-score-api/.env.deploy -f deploy/compose.yaml exec api rm -rf /var/lib/osu-score-api/cache
```

下次写入缓存时服务会重新创建该目录。不要删除 `/var/lib/osu-score-api/stats`。

雷池把 `443` 接好、并且 `/og.png` 与首页能被抓取之后，再看 `usage.json`。人机验证挡住的分享卡片不会记成一次成功查询。

## 构建时的依赖约束

- 前端：`npm ci --ignore-scripts`，仓库根 `.npmrc` 同样设置了 `ignore-scripts=true`。
- API：`uv sync --locked --no-dev`，以已提交的 `apps/api/uv.lock` 为准。
- 不要把 `/etc/osu-score-api/env`、GHCR token 或 `.env.deploy` 提交进 git。
