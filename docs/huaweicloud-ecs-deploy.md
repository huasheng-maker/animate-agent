# 华为云 ECS 部署：小艺比赛演示版

本项目在一台 Ubuntu ECS 上运行 FastAPI、Next.js 和 Caddy。任务 SQLite 数据库 `data/runs/jobs.sqlite3` 与所有任务生成文件保存在挂载的 EVS 云硬盘上。FastAPI 只运行一个容器、一个 Uvicorn worker。仓库中的 `compose.azure.yaml` 和 `Caddyfile.azure` 虽沿用最初的文件名，但只使用标准 Docker Compose 与 Caddy 功能，不调用 Azure 服务，可直接在华为云 ECS 上使用。

## 控制台准备

1. 使用 Ubuntu ECS，不选择可能被回收的竞价实例。按生成任务的 CPU、内存需求选规格，并核对 ECS、EVS、EIP 与带宽费用。保持 ECS 运行；关机后小艺无法访问。华为云说明，普通按需 ECS 关机后部分计算费用可能停止，但 [EVS、EIP 与带宽仍可能继续计费](https://support.huaweicloud.com/ecs_faq/zh-cn_topic_0018124776.html)。**华南-广州是中国大陆区域。如果新域名要通过华为云为这台 ECS 备案，华为云要求 ECS 为包年包月且累计至少 3 个月；当前按需实例不能作为备案资源。**先核对[备案服务器条件](https://support.huaweicloud.com/prepare-icp/icp_02_0003.html)及改计费模式的费用，再决定是否转换。
2. 创建一块**非共享 EVS 数据盘**并挂到 ECS。按照[华为云 EVS 指南](https://support.huaweicloud.com/intl/zh-cn/ally-visitor-1-usermanual-evs/evs_01_2708.html)，仅对确认是**新空盘**的设备分区、格式化 ext4，以 UUID 配置 `/etc/fstab`，挂载到 `/srv/animate-agent-data`。已有数据的磁盘绝不能重新格式化。
3. 申请并绑定同区域的 [EIP](https://support.huaweicloud.com/intl/zh-cn/usermanual-ecs/ecs_03_0701.html)。安全组入方向开放公网 TCP 80、443；SSH 22 只允许你的管理 IP；不要开放 3000、8000。参见[安全组说明](https://support.huaweicloud.com/usermanual-ecs/zh-cn_topic_0140323157.html)。
4. 购买一个域名并完成实名认证，域名持有者信息须与备案主体一致。广州 ECS 提供公网网站前，应先通过华为云完成[ICP备案](https://support.huaweicloud.com/icp_faq/icp_05_0145.html)，不要用未备案域名指向该 ECS 对外服务。备案通过后，在域名 DNS 控制台添加 `demo` 子域名的 A 记录，记录值为 ECS 的 EIP；[华为云 DNS 文档](https://support.huaweicloud.com/usermanual-dns/dns_usermanual_0006.html)给出了具体字段。Caddy 用该域名申请公开可信的 HTTPS 证书；证书签发前 DNS 必须已生效，80/443 必须可达。
5. 按 [Docker 官方 Ubuntu 指南](https://docs.docker.com/engine/install/ubuntu/)安装 Docker Engine 与 Compose 插件，运行 `docker compose version` 确认。

## ECS 内部署

将分支 `codex/harmony-competition-deploy` 克隆到 ECS。先确认磁盘确实挂在约定目录：

```bash
findmnt -M /srv/animate-agent-data
sudo install -d -m 700 -o 10001 -g 10001 /srv/animate-agent-data/runs
sudo install -d -m 700 /etc/animate-agent
sudo nano /etc/animate-agent/backend.env
sudo chmod 600 /etc/animate-agent/backend.env
```

`findmnt` 没有显示 EVS 挂载时必须停止。`backend.env` 至少包含一个随机的、长度不小于 32 字符的 `XIAOYI_PLUGIN_TOKEN`，以及模型和搜索服务实际用到的密钥；变量名和默认值见 [`.env.example`](../.env.example)。不要把密钥提交到 Git 或发送到聊天。另建 `/etc/animate-agent/domains.env`，内容只需：

```dotenv
APP_DOMAIN=demo.example.com
```

在仓库根目录运行：

```bash
docker compose --env-file /etc/animate-agent/domains.env -f compose.azure.yaml config --quiet
docker compose --env-file /etc/animate-agent/domains.env -f compose.azure.yaml up -d --build
docker compose --env-file /etc/animate-agent/domains.env -f compose.azure.yaml ps
curl --fail https://demo.example.com/health
```

如当前账户不能操作 Docker，给上述 `docker` 命令加 `sudo`。Caddy 负责 HTTPS；FastAPI 与 Next.js 仅在容器网络暴露 8000、3000。Next.js 的 `BACKEND_API_BASE_URL=http://api:8000` 在服务端生效；公网请求统一走 `https://demo.example.com`。Caddy 将 `/api/xiaoyi/*` 直接代理到 FastAPI，其余 `/api/animation-jobs/*` 等前端 API 经 Next.js 代理，保证观看页和播放器继续读取同一任务。

## 小艺接入与验收

- 云插件请求地址：`POST https://demo.example.com/api/xiaoyi/jobs`，请求头 `Authorization: Bearer <XIAOYI_PLUGIN_TOKEN>`；将返回的 `watch_url` 绑定到小艺卡片 `webURL`。请求体和返回字段见[小艺接入指南](xiaoyi-integration.md)。
- `/health` 应返回 `{"status":"ok"}`。未带 token 提交小艺任务应返回 401。公开演示模式下旧任务创建接口应返回 403。
- 提交接口在任务入队后立即返回；数分钟的模型生成在单个后端进程内继续，观看页轮询状态。`LLM_TIMEOUT_SECONDS` 控制模型请求超时，示例为 600 秒。ECS 不因空闲自动休眠；人为关机、维护、容器重启或重新部署仍会中断进行中的任务，并在重启后标记为 `interrupted`。
- 请在没有进行中任务时更新镜像。备份 EVS 数据盘或其中的 `runs` 目录；检查剩余磁盘空间。公开任务读取接口可被知道任务 ID 的人访问，演示中不要提交隐私或机密内容。

这些仓库文件已备齐；真实 HTTPS、小艺控制台联调和长任务验收需要 ECS、EIP、域名及模型密钥就绪后执行。
