# 用 Docker Compose 部署

面向一台自己的 Debian 机器。API 只在 Compose 网络里监听 `8000`，不对宿主机发布端口。web 容器里的 Caddy 反代 `/api` 和 `/health`，并托管前端静态文件。

默认由这只 Caddy 终止 TLS，证书是你自己的 PEM，不申请 ACME 证书。宿主机端口和绑定地址写在 `/opt/osu-score-api/.env.deploy`。不写时 Compose 使用 `80` 和 `443`。当前这台机器是 `1221` 和 `4463`，写在 `deploy/.env.deploy.example` 里，不写进 `compose.yaml` 的默认值。

镜像：

- `ghcr.io/rarverse/osu-score-fetch-gui-api:${IMAGE_TAG}`
- `ghcr.io/rarverse/osu-score-fetch-gui-web:${IMAGE_TAG}`

基础镜像按**精确版本标签 + 多架构 index digest** 固定在两个 Dockerfile 里（`python:3.12.13-slim-bookworm`、`ghcr.io/astral-sh/uv:0.13.1`、`node:22.23.3-bookworm-slim`、`caddy:2.10.2`）。更新基础镜像时要同时改标签和 digest。

成绩缓存和匿名统计在命名卷 `osu-data` 上，挂到容器内 `/var/lib/osu-score-api`。`CACHE_PATH` 与 `STATS_PATH` 都指到这个目录，不写进镜像层，换 `IMAGE_TAG` 不会丢掉数据。

生效的 Caddy 配置是构建 web 镜像时复制进去的 `/etc/caddy/Caddyfile`。部署任务也会把仓库里的 `deploy/Caddyfile` 拷到服务器的 `/opt/osu-score-api/Caddyfile`，但 Compose 不把这份文件挂进容器。改服务器上的副本不会改变正在跑的进程，下一次部署也会覆盖它。`SITE_DOMAIN`、`PUBLIC_HTTPS_PORT`、`CADDY_MODE` 在容器启动时从环境读入，改这三项后执行一次 `up -d` 即可，不必为了它们重做镜像。

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

浏览器和 API 走同一个站点时，请求是同源的，不用为了端口去改 `CORS_ORIGINS`。如果要把它写成公网来源，端口不是 443 时必须带上，例如 `https://scores.rarverse.com:4463`。

```sh
sudo cp deploy/.env.deploy.example /opt/osu-score-api/.env.deploy
sudoedit /opt/osu-score-api/.env.deploy
```

已经在跑的机器不要整文件覆盖。部署任务每次只改写 `.env.deploy` 里的 `IMAGE_TAG` 一行，其余行会留下。把下面的变量补进现有文件；缺了的话，下一次部署会回到 Compose 默认的 `80` / `443`。

`.env.deploy` 没有 osu! 密钥：

| 变量 | 作用 |
| --- | --- |
| `IMAGE_TAG` | 要运行的 GHCR 镜像标签。部署任务会改写这一行 |
| `CADDY_MODE` | `direct`（默认，自己的证书）或 `proxy`（前面已有反代） |
| `BIND_ADDR` | 宿主机绑定的 IPv4 地址，默认 `0.0.0.0`。只给本机反代时用 `127.0.0.1` |
| `HTTP_PORT` | 宿主机 HTTP 端口，映射到容器 `80`。默认 `80`。这台机器是 `1221` |
| `HTTPS_PORT` | 宿主机 HTTPS 端口，映射到容器 `443`。默认 `443`。这台机器是 `4463` |
| `PUBLIC_HTTPS_PORT` | 写进 HTTP 跳转地址的公网端口。不填时等于 `HTTPS_PORT`；两者都不填则是 `443`。值为 `443` 时跳转里不写端口 |
| `SITE_DOMAIN` | 主机名，不含 `https://` 和端口。证书的 SAN 要包含它 |
| `TLS_CERT_DIR` | 宿主机证书目录，只读挂到容器 `/certs`。示例是 `/opt/osu-score-api/certs` |
| `VITE_SITE_URL` | 只在**本机** `docker compose build` 时写入 `og:image` / `og:url` |

GitHub 上的部署流水线构建 web 镜像时用的是仓库变量 **`SITE_URL`**，不是 `.env.deploy` 里的 `VITE_SITE_URL`。这台机器的 `SITE_URL` 必须是：

```text
https://scores.rarverse.com:4463
```

少了 `:4463` 时，页面里的 `og:url` 和 `og:image` 会指向 443。分享卡片的抓取程序经常打不开非 443 端口。在统计访问之前，先把宿主机的 `443` 直接公布出去（`HTTPS_PORT=443`，安全组放行 443），或者在前面放 Nginx、Caddy、Cloudflare，让公网仍然使用 443。非 443 上的失败抓取不能用来判断有没有人打开站点。

`VITE_SITE_URL` 在构建时写进 `index.html`。只 `pull` 已有镜像不会改掉已经打进去的地址。

### 证书

`direct` 模式读取容器内这两个路径，文件名不能换：

- `/certs/fullchain.pem`：叶子证书在前，后面接中间证书
- `/certs/privkey.pem`

先把目录建好再 `up`。目录还不存在时，Docker 会建一个空目录并挂进去，Caddy 随即在打开 PEM 时退出。`restart: unless-stopped` 会把它拉起来再退出，`docker compose ps` 里看到 `Restarting`，主机 syslog 里没有 ACME 日志。错误在 `docker compose logs web`。

当前 web 镜像是 `caddy:2.10.2`，镜像配置里没有 `USER`，进程是 uid 0。uid 0 可以读 root 拥有的 `600` 私钥，也可以进入 `750` 的目录。

```sh
sudo install -d -o root -g root -m 750 /opt/osu-score-api/certs
sudo cp /path/to/fullchain.pem /opt/osu-score-api/certs/fullchain.pem
sudo cp /path/to/privkey.pem /opt/osu-score-api/certs/privkey.pem
sudo chown root:root /opt/osu-score-api/certs/fullchain.pem /opt/osu-score-api/certs/privkey.pem
sudo chmod 644 /opt/osu-score-api/certs/fullchain.pem
sudo chmod 600 /opt/osu-score-api/certs/privkey.pem
```

以后如果给 `web` 设了非 root 的 `user:`，容器里的 uid 0 不再等于宿主机的 root（rootless 或 userns 时本来就不是）。那时目录保持 `750`，私钥用 `640`（或仍用 `600`，但所有者必须是容器里的那个 uid），组要设成进程的 gid，目录组也要能进入：

```sh
sudo chgrp CONTAINER_GID /opt/osu-score-api/certs /opt/osu-score-api/certs/privkey.pem
sudo chmod 750 /opt/osu-score-api/certs
sudo chmod 640 /opt/osu-score-api/certs/privkey.pem
```

续期时覆盖这两个文件名，然后让 Caddy 重新读配置（它会重读 PEM）。在 `/opt/osu-score-api` 下：

```sh
docker compose --env-file .env.deploy -f compose.yaml exec web caddy reload --config /etc/caddy/Caddyfile
```

仓库根目录、Compose 文件还在 `deploy/` 里时，对应的是：

```sh
docker compose --env-file /opt/osu-score-api/.env.deploy -f deploy/compose.yaml exec web caddy reload --config /etc/caddy/Caddyfile
```

只改了端口、域名或 `CADDY_MODE` 时要 `up -d`，`reload` 不会改 Docker 已经发布的端口。

卷 `caddy-data`（容器内 `/data`）和 `caddy-config`（`/config`）不是证书目录。站点 PEM 只放在 `TLS_CERT_DIR`。

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

API 容器入口先准备数据目录，再以降权用户 `osu`（uid 10001）启动 **一个** uvicorn worker。进程监听 `0.0.0.0:8000`，但 Compose 没有把该端口映射到宿主机。Caddy 通过服务名 `api:8000` 访问它。`direct` 模式下 Caddy 在容器内监听 `80` 和 `443`；`proxy` 模式只监听 `80`。宿主机上看到的是 `HTTP_PORT` 和 `HTTPS_PORT`。

Caddy 只启用 HTTP/1.1 和 HTTP/2。HTTP/3 的 `alt-svc` 会公布容器内的 `:443`，浏览器会去连公网 UDP 443，而映射出去的端口是 `HTTPS_PORT`（这台机器是 4463）。

## 5. 健康检查

API 镜像自带 `HEALTHCHECK`，请求容器内 `http://127.0.0.1:8000/health`。宿主机上不直接访问 8000。

在 `/opt/osu-score-api` 读取正在使用的端口后再测。下面按这台机器的域名写；换域名时改 `--resolve` 和 URL 里的主机名。

```sh
cd /opt/osu-score-api
set -a && . ./.env.deploy && set +a
docker compose --env-file .env.deploy -f compose.yaml ps
docker compose --env-file .env.deploy -f compose.yaml logs web --tail=200
curl -I "http://127.0.0.1:${HTTP_PORT}"
curl -vk --resolve "scores.rarverse.com:${HTTPS_PORT}:127.0.0.1" "https://scores.rarverse.com:${HTTPS_PORT}/health"
```

`ps` 里 api 应为 `healthy`。web 应为 `Up`。web 若是 `Restarting`，先看 `logs web`，不要只看主机上的证书申请日志。

`direct` 模式下，本机 HTTP 的 `curl -sI` 应是 `301`，`Location` 为 `https://scores.rarverse.com:4463/`（`PUBLIC_HTTPS_PORT=443` 时没有端口）。HTTPS 那条应完成握手，证书主题对得上 `scores.rarverse.com`，`/health` 返回 `{"status":"ok","modes":[...]}`。

日志里应有 `automatic HTTPS is completely disabled`。不应再出现 ACME 申请成功或失败的记录。证书有问题时常是下面三句之一：

- `open /certs/fullchain.pem: no such file or directory`
- `open /certs/privkey.pem: permission denied`
- `tls: private key does not match public key`

### 外面仍然打不开时

按这个顺序看，停在第一个失败的地方：

1. `docker compose ps`：web 不是 `Up` 就先看 `logs web`。
2. `ss -lntp`：应能看到宿主机在听 `HTTP_PORT` 和 `HTTPS_PORT`（常见进程名是 `docker-proxy`）。只看到 `80` / `443`、看不到 `1221` / `4463`，说明 `.env.deploy` 里没有这两项，或改完后没有 `up -d`。
3. 上面的两条 `curl`。本机 HTTP 都失败，是容器没在听。本机 HTTPS 成功、公网失败，继续看防火墙和 DNS。
4. `sudo ufw status verbose`。ufw 处于 active 时放行实际端口，例如 `sudo ufw allow 1221/tcp` 和 `sudo ufw allow 4463/tcp`。
5. `sudo iptables -L INPUT -n -v` 或 `sudo nft list ruleset`。默认丢弃时要允许 TCP `HTTP_PORT` 和 `HTTPS_PORT`。
6. 云厂商安全组或面板防火墙同样要放行这两个 TCP 端口。只放行 80 和 443 时，`1221` / `4463` 从外网仍然超时。
7. DNS：`getent hosts scores.rarverse.com` 的 A 记录应是这台机器的公网地址。
8. 证书和私钥是否一对，SAN 是否包含 `SITE_DOMAIN`：

```sh
openssl x509 -in /opt/osu-score-api/certs/fullchain.pem -noout -subject -ext subjectAltName
openssl x509 -in /opt/osu-score-api/certs/fullchain.pem -noout -pubkey | openssl sha256
openssl pkey -in /opt/osu-score-api/certs/privkey.pem -pubout | openssl sha256
```

后两行的摘要必须相同。

## 6. 前面已经有 Nginx 或 Caddy

Immich 的 Compose 默认公布 HTTP `2283`，TLS 放在反代上，并要求反代转发 `Host`、`X-Forwarded-For`、`X-Forwarded-Proto`。Vaultwarden 的常见示例只绑定 `127.0.0.1:8080:80`，公网 URL 写在 `DOMAIN`。那边都是应用只出 HTTP。

这台机器已经有证书、也不走 ACME，所以默认是 `CADDY_MODE=direct`：证书挂进 web 容器。宿主机上已经有 Nginx 或 Caddy 占着 `443` 时改用 `proxy`，这时和那两个项目一样，TLS 在门口结束。

`.env.deploy`：

```text
CADDY_MODE=proxy
BIND_ADDR=127.0.0.1
HTTP_PORT=8080
HTTPS_PORT=8443
```

`compose.yaml` 始终会发布容器的 `443`。`proxy` 模式下 Caddy 不监听 `443`，也不打开 `/certs`。`HTTPS_PORT` 不要设成 `443`，否则会和门口的反代抢端口；`8443` 只绑在 `127.0.0.1` 上，没有进程接受连接。反代的上游是 `127.0.0.1:8080`。

改完后 `up -d`。本机 `curl -I http://127.0.0.1:8080/health` 的状态应是 `200`。`proxy` 模式不对 HTTP 做跳转。

Nginx 示例是 `deploy/nginx.conf.example`：`location /` 原样转发，并保留 `Host`、`X-Real-IP`、`X-Forwarded-For`、`X-Forwarded-Proto`、`X-Forwarded-Host`。不要在 Nginx 里去掉 `/api` 或 `/health`。

门口如果也是 Caddy，由它申请或使用证书，再反代到本机 HTTP：

```caddy
scores.rarverse.com {
	reverse_proxy 127.0.0.1:8080
}
```

Caddy 的 `reverse_proxy` 会自己设置 `X-Forwarded-For`、`X-Forwarded-Proto` 和 `X-Forwarded-Host`。

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

`--env-file` 与上面的启动命令相同：compose 文件会展开 `IMAGE_TAG` 和 `SITE_DOMAIN`。

不要为了清缓存删掉卷 `osu-data`。`docker compose down -v` 和 `docker volume rm` 会把 `usage.json` 和缓存一起删掉。只删除缓存目录，保留 `stats/`：

```sh
docker compose --env-file /opt/osu-score-api/.env.deploy -f deploy/compose.yaml exec api rm -rf /var/lib/osu-score-api/cache
```

下次写入缓存时服务会重新创建该目录。不要删除 `/var/lib/osu-score-api/stats`。

公网端口不是 443 时，先不要用这份统计判断站点有没有人用。分享卡片的抓取常常连不上 `https://主机:4463/og.png`，抓取失败不会记成一次成功的查询。先让 `443` 或前面的反代通了，再看 `usage.json`。

## 构建时的依赖约束

- 前端：`npm ci --ignore-scripts`，仓库根 `.npmrc` 同样设置了 `ignore-scripts=true`。
- API：`uv sync --locked --no-dev`，以已提交的 `apps/api/uv.lock` 为准。
- 不要把 `/etc/osu-score-api/env`、GHCR token 或 `.env.deploy` 里的生产域名以外的密钥提交进 git。
