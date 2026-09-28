# Render 部署：小艺比赛演示版

仓库根目录的 [`render.yaml`](../render.yaml) 定义两台 Render Web Service。
后端用 Python 3.11、单实例/单 Uvicorn worker，`data/runs` 挂 1 GB 持久磁盘；
前端使用 Next.js Node Web Service。两者都禁止自动部署，避免推送代码时直接
中断正在进行的任务。Blueprint 使用付费计算规格，创建前请在 Render 页面
确认费用。Render 自带公网 HTTPS 域名，无需本仓库安装证书或 Docker。

## 在 Render 上创建

1. 把已验证的比赛版本推送到你控制的 Git 分支。Render 只看到远端分支，
   看不到本机未提交改动。确认仓库不含 `.env`、模型密钥、运行记录或个人文件。
2. 在 Render 创建 Blueprint，连接该 GitHub 仓库和上述分支，选根目录的
   `render.yaml`。检查会创建 **两个付费 Web Service 和一个持久磁盘**，确认
   规格、区域和费用后再创建。若服务名冲突，在 Blueprint 中改名。
3. 后端健康检查应为 `https://<api>.onrender.com/health`，返回
   `{"status":"ok"}`。默认数据目录不修改：磁盘挂载在
   `/opt/render/project/src/data/runs`，恰好覆盖 SQLite、上传任务输入和
   `data/runs/<run_id>` 生成文件；仓库中的 `data/samples` 仍可读取。
4. 在后端 Environment 设置 `XIAOYI_PUBLIC_ORIGIN` 为前端公网 HTTPS origin
   （只填域名，不带末尾 `/` 或路径），再设置真实生成所需的模型和 Web Search
   环境变量。`XIAOYI_PLUGIN_TOKEN` 由 Blueprint 生成；只在 Render 环境页查看，
   不复制到仓库、Next 客户端变量或日志。
5. 在前端 Environment 设置 `BACKEND_API_BASE_URL` 为后端公网 HTTPS origin。
   这个变量只在 Next.js 服务端使用。保存环境变量并手动部署两个服务。
6. 在小艺开放平台创建云插件：调用
   `POST https://<api>.onrender.com/api/xiaoyi/jobs`，把同一个 token 配成
   `Authorization: Bearer <token>`；绑定返回的 `watch_url` 到卡片 `webURL`。
   详细字段见 [小艺接入指南](xiaoyi-integration.md)。

## 验收与运行边界

- 未传 token 调用小艺提交接口应返回 401；旧
  `POST /api/animation-jobs`、`POST /api/animations/from-query` 和
  `/openapi.json` 在公开模式下应返回 403。`/health` 返回 200。
- 用小艺控制台发起一条明确的测试问题后，立即得到 `watch_url`。在手机打开，
  核对任务状态、完成后播放器的真实内容和交互。这一步可能产生搜索与模型费用。
- 后端长任务在同一进程后台运行，提交接口不等待模型。观看页每 5 秒读取状态；
  它不依赖浏览器长连接。Render 部署、重启或故障会把未完成任务标为
  `interrupted`，不会自动重复付费请求。应在没有进行中任务时手动部署。
- 小艺提交请求只等任务入队，故不会占用整个模型生成时长；模型自身的请求
  超时由 `LLM_TIMEOUT_SECONDS` 控制（仓库示例默认 600 秒）。这不保证 Render
  进程能连续运行该时长，重启仍会中断任务。
- 仅挂载路径内文件持久化。磁盘空间不足会让生成失败；定期查看磁盘用量。
  Render 持久磁盘绑定单实例，因此不要横向扩容或增加 Uvicorn worker。
- 1 GB 和计算规格只是演示起点，需要根据实际任务耗时、内存、磁盘增长和
  小艺云端访问结果调整。Render 区域在 Blueprint 中设为 Singapore；需要从
  小艺控制台和目标鸿蒙设备实测网络可达性。

官方文档：[Blueprint 字段](https://render.com/docs/blueprint-spec)、
[持久磁盘](https://render.com/docs/disks)、
[环境变量](https://render.com/docs/configure-environment-variables)、
[Next.js Web Service](https://render.com/docs/deploy-nextjs-app)。
