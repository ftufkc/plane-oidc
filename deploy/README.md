# 全新部署

应用底座为官方 v1.4.2，移植 jiyang1018 `preview-v2` 的全部定制功能。
采用独立的 Compose 项目 `plane-oidc-v142` 和全新数据卷。

1. 运行 GitHub Actions 的 `Build OIDC v1.4.2`，确认后端定向测试通过。
2. 下载五个 `plane-*-oidc-amd64` artifact，核对 `image.sha256`，执行
   `docker load -i image.tar.gz`。在 `.env` 中将 `PLANE_IMAGE_TAG` 设为构建提交的完整 SHA。
3. 将本目录的 `compose.yaml`、`Caddyfile`、`pat_server.py` 和私有 `.env` 放在部署目录。可参考 `env.example`，必须替换其中的密钥占位符。
4. 显式确认旧 Compose 项目后执行 `docker compose down --volumes --remove-orphans`。
   此操作删除旧数据库和附件，仅用于明确不保留历史数据的全新部署。不要清理其他应用。
5. 在新部署目录执行 `docker compose up -d --pull never`，确认 migrator 以状态 0 退出。
6. 初始化 God Mode 管理员，配置 Keycloak discovery、client ID、client secret 和回调。
   Client 回调为 `${WEB_URL}/auth/oidc/callback/`，需要 email/profile scope。未验证邮箱仅允许首次注册或已绑定的 OIDC 身份登录，不能关联已有账号。
7. 用 Chrome 验证 OIDC 登录、管理员成员管理、默认工作空间及角色、移动入口。

## PAT MCP

公网入口复用现有 TCP 3307 转发，MCP 仅公开 `/http/api-key/mcp`。
容器不向主机发布额外端口，也不启用 OAuth 授权入口。

- 传输：Streamable HTTP
- Header：`Authorization: Bearer <个人 PAT>`
- Header：`X-Workspace-slug: <工作空间 slug>`

PAT 继承所属用户在 Plane 的权限，Header 不构成权限隔离。
HTTP 部署依赖现有可信网络；令牌不能写入 Git、公共日志或共享文档。
当前 MCP 固定为官方 v0.3.4 的 digest，须对实际使用的社区版工具逐项验收。

## 后续升级

保持 OIDC 改动独立于官方底座。升级先在独立数据库中运行迁移与定向测试，
再验证 Keycloak 和 MCP。发布记录应包含源码 SHA、镜像 ID、配置文件哈希和测试结果。

后端单独修复且前端源码未变时，可设置 `PLANE_BACKEND_IMAGE_TAG` 覆盖后端镜像提交；其余镜像继续使用 `PLANE_IMAGE_TAG`。
