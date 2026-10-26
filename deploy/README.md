# Debian / Docker Compose 部署

默认从源码构建，在仓库根目录执行 `docker compose up -d`。项目只提供 HTTP，域名、HTTPS 和证书全部由外部 Nginx、雷池等反代管理。

组织方式参考 [Outline 官方 Docker 部署](https://docs.getoutline.com/s/hosting/doc/docker-7pfeLP5a8t)：Compose 管理服务，环境文件管理配置，命名卷保存数据；本项目使用外部反代终止 TLS。

## 1. 从源码启动（推荐）

Debian 需要安装 Docker Engine 和 Compose 插件，Compose 版本至少为 **2.24.0**（使用可选 `env_file`）。安装步骤见 [Docker 官方 Debian 文档](https://docs.docker.com/engine/install/debian/)。不需要在宿主机安装 Node、Python、uv 或 Nginx。

进入已经克隆的仓库根目录：

```sh
docker compose up -d
```

首次自动构建 API 和 web 镜像，无需登录 GHCR、设置 `IMAGE_TAG` 或创建 `/etc` 文件。未配置服务端 osu! 凭据时，首页和 `/health` 可用；查询需要访客填写自己的凭据，否则返回 `503 NOT_CONFIGURED`。

需要共享服务端凭据、改端口或设置分享卡片的公网地址时，首次启动前执行：

```sh
cp .env.example .env
chmod 600 .env
# 编辑 .env，填写 OSU_CLIENT_ID、OSU_CLIENT_SECRET、VITE_SITE_URL 等
# 之后仍用同一条命令启动：
docker compose up -d
```

`.env` 已被 git 和 Docker 构建上下文忽略。Compose 自动读取它，API 也从它接收配置。不要将密钥放在 `VITE_` 变量中，这类变量会公开到前端。

| 配置 | 默认值 / 用途 |
| --- | --- |
| `BIND_ADDR` | `127.0.0.1`，仅供同机反代访问 |
| `HTTP_PORT` | `8080`，宿主机 HTTP 端口 |
| `OSU_CLIENT_ID` / `OSU_CLIENT_SECRET` | 可选的服务端 osu! OAuth 凭据 |
| `API_ENV_FILE` | 默认 `.env`；可指定 `/etc/osu-score-api/env` 复用已有密钥文件 |
| `VITE_SITE_URL` | 分享卡片的公网 origin，如 `https://scores.example.com`；更改后需要重新构建 web |
| `COMPOSE_SUBNET` / `COMPOSE_GATEWAY` | `172.31.210.0/24` / `172.31.210.1`；与现有网络冲突时一起修改 |
| `WEB_IPV4` | `172.31.210.10`；API 只信任这个 web 容器转发的客户端 IP |
| `TRUSTED_PROXIES` | 空格分隔的反代 IP，默认 `127.0.0.1 172.31.210.1` |

限流、缓存等 API 配置也可写进 `.env`，完整变量表见仓库 README。`CACHE_PATH` 和 `STATS_PATH` 由 Compose 固定在数据卷中。API 必须保持单 worker、单副本，限流和并发锁目前位于进程内。

可选管理员后台需要 PostgreSQL、OIDC、加密密钥、Prometheus 和 Loki。配置完成后使用 `docker compose --profile admin up -d --build` 启动；不要仅通过公开端口暴露观测组件。完整步骤见[管理员后台部署](../docs/admin.md)。

## 2. 接外部反代

访问链路：访客 → 外部 HTTPS 反代 → HTTP web → API。

- web 只发布 `127.0.0.1:8080`（或配置的端口），API 的 8000 不发布到宿主机。
- 项目内 Nginx 仅托管静态文件、转发 `/api/*` 和 `/health`，只监听 HTTP。
- 项目不申请、读取或挂载证书，不发布宿主机 80/443，不做 HTTPS 跳转。
- 外部反代转发整个站点，保留路径、`Host`、`X-Forwarded-For` 和 `X-Forwarded-Proto`。

### 反代在宿主机或使用 host 网络

上游填写 **`http://127.0.0.1:8080`**，协议选 HTTP，不附加 `/api`。

外部 Nginx 示例见 [nginx.conf.example](nginx.conf.example)，证书路径指向你自己管理的位置。雷池中配置相同 HTTP 上游，证书绑定在雷池站点上。

项目内 Nginx 信任 Docker 网关并从 `X-Forwarded-For` 右侧解析真实 IP，再向 API 发送单个客户端 IP。不要把 `TRUSTED_PROXIES` 或 API 的信任范围放开为整个公网。

### 反代在独立 bridge 网络容器

容器内的 `127.0.0.1` 指向反代容器自身，不能访问宿主机的 loopback 发布端口。这种情况下让反代加入 `osu-score-api_backend` 网络，通过 **`http://web:80`** 访问，不必将 HTTP 端口开放到公网。

例如先临时验证（替换反代容器名，IP 应未被使用）：

```sh
docker network connect --ip 172.31.210.20 osu-score-api_backend YOUR_PROXY_CONTAINER
```

在本项目 `.env` 中加入反代在该网络上的 IP，然后执行 `docker compose up -d`：

```dotenv
TRUSTED_PROXIES=127.0.0.1 172.31.210.1 172.31.210.20
```

验证后，在反代自己的 Compose 中持久配置这个 external 网络和固定地址；手动 `network connect` 的配置在反代容器被重建后不会保留。使用自定义子网时，上述地址需对应调整。

## 3. 验证与更新

在仓库根目录执行：

```sh
docker compose ps
docker compose logs --tail=100
curl -fsS http://127.0.0.1:8080/health
curl -sS -D - -o /dev/null http://127.0.0.1:8080/
```

api 和 web 都应为 `healthy`。首页与 `/health` 应返回 200，且不跳转到 HTTPS。`/health` 只接受 GET，`curl -I` 会返回 405。健康状态只确认站点和 API 可达，不证明 osu! OAuth 凭据或上游网络可用。

需要命令等待健康检查完成时：

```sh
docker compose up -d --wait --wait-timeout 120
```

本机 HTTP 成功、公网 HTTPS 失败时，检查外部反代的上游地址、运行网络、DNS 和防火墙；先不要在项目中添加证书配置。

拉取新代码后重建：

```sh
git pull
docker compose up -d --build
```

修改 `deploy/15-trusted-proxies.sh` 同样需要重新构建 web。仅改运行时配置时执行 `docker compose up -d`；改 `VITE_SITE_URL`、前端源码或 `deploy/nginx.conf` 时需要 `--build`。Nginx 配置和可信代理启动脚本打包在 web 镜像中，不挂载宿主机副本。

## 4. 已有部署与 GHCR 流水线

根目录 `compose.yaml` 用于源码构建。`deploy/compose.yaml` 保留给现有 GitHub Actions / GHCR 镜像部署，仍读取 `/etc/osu-score-api/env` 和 `.env.deploy`，不要混用两套更新流程。

已有镜像部署继续使用：

```sh
cd /opt/osu-score-api
docker compose --env-file .env.deploy -f compose.yaml pull
docker compose --env-file .env.deploy -f compose.yaml up -d --wait --wait-timeout 120
```

首次镜像部署需将仓库的 `deploy/compose.yaml` 放在 `/opt/osu-score-api/compose.yaml`，复制 `deploy/.env.deploy.example` 为该目录的 `.env.deploy` 并将 `IMAGE_TAG` 改为已发布标签；复制 `deploy/env.example` 到 `/etc/osu-score-api/env`，填入真实凭据并设权限 600。私有 GHCR 镜像需先用只读 `read:packages` token 登录。这个独立目录没有构建上下文，不能用其中的 `build` 配置构建源码。

`main` 自动部署流水线按 git SHA 发布镜像，只更新 `.env.deploy` 中的 `IMAGE_TAG`；web 分享地址由仓库变量 `SITE_URL` 构建进镜像。API 和 web 健康检查均通过后才继续部署验证。回滚时将 `IMAGE_TAG` 改回已知可用 SHA，再执行上面的 pull 和 up 命令。

### Release 版本镜像

将 `.github/workflows/release.yml` 提交并推送后，在 GitHub 创建并发布 Release，标签使用 `v0.1.1` 这样的版本号（也支持 `v0.2.0-rc.1`）。标签必须指向包含该 workflow 的提交；保存草稿不会触发发布。

Release workflow 会复用 CI 的前后端检查和 Docker 部署测试，通过后将该标签对应代码构建为以下镜像（`linux/amd64`）：

```text
ghcr.io/rarverse/osu-score-fetch-gui-api:v0.1.1
ghcr.io/rarverse/osu-score-fetch-gui-web:v0.1.1
```

发布使用 `GITHUB_TOKEN` 写入 GHCR，不依赖 `DEPLOY_ENABLED` 或 SSH 部署密钥，也不触发服务器部署或更新 `latest`。web 同样读取仓库变量 `SITE_URL`。预发布版本也会上传对应版本标签。

等待 Release workflow 的两个镜像发布任务都成功后，将镜像部署目录 `.env.deploy` 中的 `IMAGE_TAG` 设置为 `v0.1.1`，再执行上面的 pull 和 up 命令。切换或回滚到其他已发布版本时，更改 `IMAGE_TAG` 即可；若仍启用 `main` 自动部署，后续推送会再次将服务器更新为对应的 git SHA。

从旧部署切换到根目录源码部署时：

1. 复制 `.env.example` 为根目录 `.env`，迁移旧 `.env.deploy` 中的端口、网络、可信代理配置。
2. 在 `.env` 设置 `API_ENV_FILE=/etc/osu-score-api/env` 复用原有 API 配置；旧文件必须对执行 Compose 的用户可读。
3. 项目名仍是 `osu-score-api`，卷仍是 `osu-score-api_osu-data`。核对现有容器所属项目和卷名后，在根目录执行 `docker compose up -d --build`。
4. 停用旧工作目录 / Portainer / CI 对同一组服务的更新，避免相互覆盖。

Portainer 中仅使用镜像部署文件；栈名应与现有部署一致。Portainer 对栈的管理方式取决于其版本和创建方式，不能仅凭 Compose 的 `name:` 保证它会接管已有 CLI 容器。

## 5. 数据与备份

命名卷 `osu-score-api_osu-data` 挂到 API 的 `/var/lib/osu-score-api`：

- 成绩缓存：`cache/`
- 匿名使用统计：`stats/usage.json`

API 入口准备目录权限后降权到 `osu`（uid 10001）。重建镜像、重建容器和普通 `docker compose down` 保留命名卷。**不要执行 `docker compose down -v`，它会删除缓存和统计。**

从源码部署导出已有统计文件：

```sh
docker compose cp api:/var/lib/osu-score-api/stats/usage.json ./stats.json
```

完整备份应覆盖整个命名卷；备份时先停止 API 写入。更新前备份，且不要把备份或密钥提交到仓库。
