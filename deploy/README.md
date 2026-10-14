# 用 Docker Compose 部署

面向一台自己的 Debian 机器。API 只在 Compose 网络里监听 `8000`，不对宿主机发布端口。Caddy 对外提供 80/443，同一站点反代 `/api` 和 `/health`，并托管前端静态文件。

镜像：

- `ghcr.io/rarverse/osu-score-fetch-gui-api:${IMAGE_TAG}`
- `ghcr.io/rarverse/osu-score-fetch-gui-web:${IMAGE_TAG}`

基础镜像按**精确版本标签 + 多架构 index digest** 固定在两个 Dockerfile 里（`python:3.12.13-slim-bookworm`、`ghcr.io/astral-sh/uv:0.13.1`、`node:22.23.3-bookworm-slim`、`caddy:2.10.2`）。更新基础镜像时要同时改标签和 digest。

成绩缓存和匿名统计在命名卷 `osu-data` 上，挂到容器内 `/var/lib/osu-score-api`。`CACHE_PATH` 与 `STATS_PATH` 都指到这个目录，不写进镜像层，换 `IMAGE_TAG` 不会丢掉数据。

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

```sh
sudo cp deploy/env.deploy.example /opt/osu-score-api/.env.deploy
sudoedit /opt/osu-score-api/.env.deploy
```

`.env.deploy` 只有这三项，没有 osu! 密钥：

| 变量 | 作用 |
| --- | --- |
| `IMAGE_TAG` | 要运行的 GHCR 镜像标签 |
| `SITE_DOMAIN` | 主机名，不含 `https://`。Caddy 用它申请证书 |
| `VITE_SITE_URL` | 构建 web 镜像时写入 `og:image` / `og:url` 的站点根，例如 `https://scores.example.com` |

`VITE_SITE_URL` 在 **构建** web 镜像时生效，只 `pull` 已有镜像不会改写已经打进 `index.html` 的地址。本地构建时把它放进 `.env.deploy`，Compose 会作为 build arg 传入。

把仓库放到这台机器上（路径随意），下面假设当前目录是仓库根。

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

API 容器入口先准备数据目录，再以降权用户 `osu`（uid 10001）启动 **一个** uvicorn worker。进程监听 `0.0.0.0:8000`，但 Compose 没有把该端口映射到宿主机。Caddy 通过服务名 `api:8000` 访问它。证书存在卷 `caddy-data`（容器内 `/data`）和 `caddy-config`（`/config`）。

## 5. 健康检查

API 镜像自带 `HEALTHCHECK`，请求容器内 `http://127.0.0.1:8000/health`。宿主机上不直接访问 8000。

```sh
docker compose --env-file /opt/osu-score-api/.env.deploy -f deploy/compose.yaml ps
curl -fsS "https://scores.example.com/health"
```

`ps` 里 api 应为 `healthy`。`curl` 应返回 `{"status":"ok","modes":[...]}`。把域名换成 `SITE_DOMAIN`。

## 6. 回滚

数据卷不动。把 `/opt/osu-score-api/.env.deploy` 的 `IMAGE_TAG` 改回上一个可用标签，然后：

```sh
docker compose --env-file /opt/osu-score-api/.env.deploy -f deploy/compose.yaml pull
docker compose --env-file /opt/osu-score-api/.env.deploy -f deploy/compose.yaml up -d
```

再跑一次上面的健康检查。web 镜像如果是用另一个 `VITE_SITE_URL` 构建的，回滚标签也会带回当时写进页面的 OG 地址。

## Usage stats

`deploy/compose.yaml` 把命名卷 `osu-data` 挂到服务 `api` 的 `/var/lib/osu-score-api`，并用 `STATS_PATH` 固定统计文件：

- 容器内：`/var/lib/osu-score-api/stats/usage.json`
- 卷 `osu-data` 内：`stats/usage.json`（卷根对应容器里的 `/var/lib/osu-score-api`）

成绩缓存是同一卷上的 `cache/`（`CACHE_PATH=/var/lib/osu-score-api/cache`）。统计和缓存不在两个卷里。

`api` 已经启动时，把统计文件复制到当前目录：

```sh
docker compose --env-file /opt/osu-score-api/.env.deploy -f deploy/compose.yaml cp api:/var/lib/osu-score-api/stats/usage.json ./stats.json
```

`--env-file` 与上面的启动命令相同：compose 文件会展开 `IMAGE_TAG` 和 `SITE_DOMAIN`。

不要为了清缓存删掉卷 `osu-data`。`docker compose down -v` 和 `docker volume rm` 会把 `usage.json` 和缓存一起删掉。只删除缓存目录，保留 `stats/`：

```sh
docker compose --env-file /opt/osu-score-api/.env.deploy -f deploy/compose.yaml exec api rm -rf /var/lib/osu-score-api/cache
```

下次写入缓存时服务会重新创建该目录。不要删除 `/var/lib/osu-score-api/stats`。

## 构建时的依赖约束

- 前端：`npm ci --ignore-scripts`，仓库根 `.npmrc` 同样设置了 `ignore-scripts=true`。
- API：`uv sync --locked --no-dev`，以已提交的 `apps/api/uv.lock` 为准。
- 不要把 `/etc/osu-score-api/env`、GHCR token 或 `.env.deploy` 里的生产域名以外的密钥提交进 git。
