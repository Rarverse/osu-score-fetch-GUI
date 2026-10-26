# 管理员后台部署

[返回项目首页](../README.md) · [部署说明](../deploy/README.md) · [运行维护](operations.md)

管理员入口为 `/admin`。默认关闭；关闭时登录入口返回 404，公开查分功能不依赖数据库或观测组件。

后台提供：

- API、网页、日志存储和 osu! 上游可用性状态；
- 每次查分的输入用户名、解析后用户名、状态、耗时和当次返回结果；
- 按级别、请求编号和关键字检索的高可读日志时间线；
- OIDC 授权码流程、PKCE、服务端不透明会话、CSRF 防护和管理员角色校验；
- 密码加邮箱 OTP 二次验证；未分配管理员角色的账号无法进入。

## 1. 外部准备

需要现有 authentik 实例、可发送验证码的邮件配置和一个正式 HTTPS 域名。无需额外部署 ZITADEL 或其他身份系统。生产环境不要用 HTTP，也不要将 PostgreSQL、Loki 或 Prometheus 端口发布到公网。

在 authentik 中：

1. 创建组 `raru-admin`，只加入实际管理员。
2. 创建 OAuth2/OpenID Connect Provider，Client type 选择 Confidential，启用 Authorization Code，Redirect URI 使用 Strict 并填写 `https://你的域名/api/admin/auth/callback`。
3. 为 Provider 选择 RSA Signing Key，保留每 Provider 一个 issuer 的默认模式，并启用 **Include claims in id_token**。Scopes 至少包含 `openid`、`profile`、`email`；`profile` 会提供 `groups` 声明。
4. 创建 Application 并关联 Provider，在 **Policy / Group / User Bindings** 中只绑定 `raru-admin` 组。这样 authentik 自身和本项目后端会各做一次授权检查。
5. 为这个 Application 建立专用 Authentication Flow：Identification → Password → Authenticator Validation → User Login。Authenticator Validation 只允许 **Email** device class，Not configured action 使用 `Deny`，并关闭最近验证跳过功能。
6. 配置 authentik 全局邮件发送；通过 Email Authenticator Setup Stage 预先为每位管理员登记邮箱验证器。不要在这个专用 Flow 中开放外部来源、Passkey、TOTP 或免密码入口。

`OIDC_ISSUER` 应复制 Provider 的 issuer，默认类似 `https://auth.example.com/application/o/raru-admin/`，不要只填 authentik 根地址。后端会验证 ID Token 的非对称签名、issuer、audience、有效期、nonce、邮箱、authentik 的 `pwd + mfa` 认证方法及 `raru-admin` 组。由于专用 Flow 只允许 Email 验证器，`mfa` 在这里代表本次完成了邮箱 OTP。OIDC token 不保存到浏览器或数据库；浏览器只有 `HttpOnly + Secure + SameSite=Strict` 的随机会话 cookie。

authentik 2025.10 及之后默认不会仅因账号存在邮箱就返回 `email_verified=true`。本项目默认不依赖该资料声明，而依赖本次登录的 Email MFA。如果你另外维护了可靠的邮箱验证状态，可设置 `ADMIN_REQUIRE_VERIFIED_EMAIL=true` 并按照 authentik 官方方式配置自定义 `email` Scope Mapping。

## 2. 生成密钥并配置

从 `.env.example` 复制 `.env`，设置数据库密码并分别生成两个不同的 32 字节密钥：

```sh
openssl rand -base64 32
openssl rand -base64 32
```

然后填写：

```dotenv
ADMIN_ENABLED=true
ADMIN_PUBLIC_ORIGIN=https://scores.example.com

POSTGRES_DB=raru
POSTGRES_USER=raru
POSTGRES_PASSWORD=replace-with-a-long-random-password
DATABASE_URL=postgresql+psycopg://raru:replace-with-a-long-random-password@postgres:5432/raru

OIDC_ISSUER=https://auth.example.com/application/o/raru-admin/
OIDC_CLIENT_ID=replace-with-client-id
OIDC_CLIENT_SECRET=replace-with-client-secret
OIDC_REDIRECT_URI=https://scores.example.com/api/admin/auth/callback
OIDC_SCOPES=openid profile email
ADMIN_ROLE_CLAIM=groups
ADMIN_REQUIRED_ROLE=raru-admin
ADMIN_REQUIRED_AMR=pwd,mfa

AUDIT_ENCRYPTION_KEY=first-generated-key
AUDIT_LOOKUP_KEY=second-generated-key

LOG_FORMAT=json
LOKI_URL=http://loki:3100
LOKI_TENANT_ID=raru-production
PROMETHEUS_URL=http://prometheus:9090
```

`.env` 权限应为 `600`。也可通过 `OIDC_CLIENT_SECRET_FILE`、`AUDIT_ENCRYPTION_KEY_FILE` 和 `AUDIT_LOOKUP_KEY_FILE` 从只读文件加载密钥。密钥文件必须挂载进 API 容器；不要将密钥写进前端变量、Compose 文件或 Git。

仅在 localhost 本地联调时还需设置 `ADMIN_SECURE_COOKIES=false`；生产环境必须保持默认的 `true`。数据库密码若含有 URL 保留字符，写入 `DATABASE_URL` 前需要进行 URL 编码。

`AUDIT_ENCRYPTION_KEY` 使用 AES-256-GCM 加密用户名、查询输入和结果快照；`AUDIT_LOOKUP_KEY` 只用于不可逆索引。两把密钥必须不同并纳入独立备份。当前实现使用 `v1` 密钥标识；更换密钥前需先实施数据重加密，直接替换会使旧记录无法读取。

## 3. 启动

从源码部署：

```sh
docker compose --profile admin up -d --build
docker compose --profile admin ps
```

API 容器启动时会自动执行 Alembic 迁移。首次完成后访问 `https://你的域名/admin`，确认：

1. 未登录时只能看到安全登录页；
2. 无管理员角色的账号返回 403；
3. 管理员必须完成密码与邮箱验证码；
4. 完成一次公开查分后，请求记录中能查看该次结果；
5. 总览出现服务状态，日志中心能按同一 Request ID 串联事件。

仅运行 `docker compose up -d` 不会启动 profile 内的 PostgreSQL、Loki、Alloy、Prometheus 和 Blackbox Exporter。管理员已启用但这些组件未启动时，API 会因数据库不可用而拒绝启动，这是有意的安全失败方式。

## 4. 数据保留与权限

默认保留策略：

| 数据 | 默认保留期 |
| --- | --- |
| 完整查询结果快照 | 7 天 |
| 查询审计元数据 | 30 天 |
| 管理员操作审计 | 180 天 |
| Loki 日志 | 30 天 |
| Prometheus 指标 | 30 天 |

可分别用 `QUERY_RESULT_RETENTION_DAYS`、`QUERY_METADATA_RETENTION_DAYS` 和 `ADMIN_AUDIT_RETENTION_DAYS` 调整。过期清理由 API 启动时及之后每小时执行；结果详情访问时也会立即清除已过期快照。

敏感查询内容不会写入普通应用日志或 Nginx 访问日志。普通日志只保留请求编号、状态、阶段、缓存、耗时和错误类别；用户名与当次响应只进入应用层加密的 PostgreSQL 审计表。查看某次完整结果和搜索日志都会写入管理员审计记录。

需要备份的命名卷包括 `postgres-data`、`loki-data` 和 `prometheus-data`。不要使用 `docker compose down -v`。数据库备份必须与审计加密密钥分开保存；任何一方单独泄露都不应能够还原用户名或结果。

## 5. 运维注意

- Alloy 为读取容器标准输出，以只读方式挂载 Docker socket。专用服务器可直接使用；共享 Docker 主机建议改用受限 socket proxy 或主机级采集器。
- Loki、Prometheus 和 PostgreSQL 仅位于内部 `backend` 网络。不要为了查看原始界面临时发布公网端口。
- 公开反代必须保留 HTTPS；`ADMIN_SECURE_COOKIES=false` 只适用于 localhost 测试。
- 管理后台发生 503 时，先检查 `postgres`、`loki`、`prometheus`、`blackbox`、`alloy` 容器及 API 迁移日志。
- 删除管理员权限应先从 authentik 的 `raru-admin` 组移除用户；已有本地会话最长可持续 8 小时，紧急撤权时同时重启 API 或删除对应 `admin_sessions` 记录。
