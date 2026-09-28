# Azure VM 部署：小艺比赛演示版

当前任务状态和生成文件使用 `data/runs/jobs.sqlite3` 与 `data/runs/<run_id>`。本方案在**一台 Ubuntu Azure VM** 上运行 Docker Compose，并把 Azure 托管数据磁盘的 ext4 文件系统挂到 `/srv/animate-agent-data`。后端只启动一个 Uvicorn worker 和一个容器；Next.js 与 Caddy 是另两个容器。Caddy 对一个域名提供公网 HTTPS，将 `/api/xiaoyi/*` 和 `/health` 送到 FastAPI，其余请求送到 Next.js。

Azure App Service 或 Container Apps 的 Azure Files 挂载虽然能保存文件，但 Azure [明确不建议将 SQLite 等依赖文件锁的数据库放在 App Service 存储挂载上](https://learn.microsoft.com/en-us/azure/app-service/configure-connect-to-azure-storage)。因此比赛阶段优先采用 VM 和块设备文件系统。以后若改为托管容器，应先把任务数据库迁到受支持的数据库。

## Azure 门户中完成

1. 创建资源组和 Ubuntu Linux VM。选**普通持久 OS 磁盘**，不要选临时 OS 磁盘或可被驱逐的 Spot VM。按真实生成任务选择 CPU/内存，先在 Azure 价格计算器查看 VM、磁盘与公网 IP 的预计费用。
2. 给 VM 附加一块**托管数据磁盘**，在 VM 内按 [Azure 官方 Linux 数据磁盘指南](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/attach-disk-portal)识别新磁盘、格式化为 ext4、按 UUID 加入 `/etc/fstab`，挂载到 `/srv/animate-agent-data`。**只格式化经核实的新空盘；不要格式化已有数据的磁盘。**
3. 给 VM 分配稳定公网 IP，并为该 IP 设置 [Azure DNS 名称标签](https://learn.microsoft.com/en-us/azure/virtual-machines/create-fqdn)，或把你自己的域名 A 记录指向它。网络安全组只对公网放行 TCP 80、443；SSH 22 限制为你的管理 IP。不要向公网开放 3000 或 8000。
4. 在 Ubuntu 按 [Docker 官方安装文档](https://docs.docker.com/engine/install/ubuntu/)安装 Docker Engine 和 Compose 插件；完成后运行 `docker compose version`。

## VM 上部署

把仓库分支 `codex/harmony-competition-deploy` 克隆到 VM。以下命令在仓库根目录执行：

```bash
findmnt -M /srv/animate-agent-data
sudo install -d -m 700 -o 10001 -g 10001 /srv/animate-agent-data/runs
sudo install -d -m 700 /etc/animate-agent
sudo nano /etc/animate-agent/backend.env
sudo chmod 600 /etc/animate-agent/backend.env
```

`findmnt` **必须显示数据磁盘已挂载**，否则停止部署。`backend.env` 至少设置 `XIAOYI_PLUGIN_TOKEN`（随机、至少 32 字符）及你所选模型和搜索服务需要的密钥，例如：

```dotenv
XIAOYI_PLUGIN_TOKEN=<在 VM 本地生成的随机密钥>
DEEPSEEK_KEY=<模型密钥>
WEB_SEARCH_PROVIDER=gemini
GEMINI_API_KEY=<搜索密钥>
LLM_TIMEOUT_SECONDS=600
```

按实际供应商配置，可参考 [`.env.example`](../.env.example)。密钥只放在 VM 的受限文件中，不要写入仓库、Compose 文件、终端共享记录或发送到聊天。另建只含域名的 `/etc/animate-agent/domains.env`：

```dotenv
APP_DOMAIN=app.example.com
```

先确认域名已解析到 VM 公网 IP，然后启动：

```bash
docker compose --env-file /etc/animate-agent/domains.env -f compose.azure.yaml config --quiet
docker compose --env-file /etc/animate-agent/domains.env -f compose.azure.yaml up -d --build
docker compose --env-file /etc/animate-agent/domains.env -f compose.azure.yaml ps
curl --fail https://app.example.com/health
```

若 Docker 命令提示权限不足，在命令前加 `sudo`，并向 `sudo` 显式传入 `--env-file` 的绝对路径。Caddy 需要 DNS、80/443 公网可达才能自动签发和续期 HTTPS 证书。Compose 中 Next.js 服务端的 `BACKEND_API_BASE_URL=http://api:8000` 只走私有容器网络；浏览器与小艺使用 HTTPS 公网域名。

## 小艺与验收

- 小艺云插件地址：`POST https://app.example.com/api/xiaoyi/jobs`；请求头 `Authorization: Bearer <XIAOYI_PLUGIN_TOKEN>`。返回的 `watch_url` 指向同一域名的前端页面，接到小艺卡片的 `webURL`。详细字段见[小艺接入指南](xiaoyi-integration.md)。
- 未带 token 的提交请求应返回 401；公开模式下旧写入接口应返回 403。不要把 token 放入前端环境变量或网页代码。
- Python 任务在同一后端进程中持续运行几分钟，提交接口很快返回；前端按任务 ID 轮询。VM 不会因为空闲而自动休眠，但人为关机、Azure 维护、容器重启或部署会中断进行中的任务。应用会在重启时标记未完成任务为 `interrupted`。
- `LLM_TIMEOUT_SECONDS` 是模型客户端超时，不是任务成功保证。不要在任务进行中执行 `docker compose up -d --build`。部署前备份数据磁盘，尤其是 `jobs.sqlite3` 和运行目录；磁盘容量与备份策略需按实测增长调整。
- `docker compose` 的后端和前端均无公网端口映射；只有 Caddy 暴露 80/443。API 的 `/api/xiaoyi/jobs` 由 Bearer 鉴权，公开演示模式拒绝大多数旧接口。`/health` 与已知任务的读取接口可公网访问，因此不要把任务内容视为私密数据。

此文档和 Compose 文件完成了部署准备；仍需有 Azure 订阅、Azure DNS 名称标签或自有域名、模型密钥，以及在 Azure 门户创建 VM 和磁盘后才能进行真实线上验收。
