# 小艺云插件接入：问题 → 后台任务 → 手机观看 → 播放器

本仓库提供一个短请求桥接层。小艺调用 `POST /api/xiaoyi/jobs` 后立即取得
`run_id` 和 `watch_url`；生成继续在后端运行。用户打开 `watch_url` 后，页面查询
既有任务状态，完成后进入原有播放器。小艺也可以用 `GET /api/xiaoyi/jobs/{run_id}`
查询状态。桥接层只接受文本问题；文件和 URL 的采集能力不对小艺插件开放。

## 需要准备

1. 一台可从小艺云插件访问的 HTTPS 后端，以及可在鸿蒙设备打开的 HTTPS
   Next.js 前端。`localhost` 仅用于本机调试，手机和小艺云端无法访问电脑的
   `127.0.0.1`。后端保持单 worker；任务快照保存在 `data/runs/jobs.sqlite3`。
2. 在后端的服务端环境变量中设置 `XIAOYI_PLUGIN_TOKEN`（至少 32 个随机字符）
   和 `XIAOYI_PUBLIC_ORIGIN`（前端 HTTPS origin，例如
   `https://movie.example`，不要加路径）。不要把 token 放进 Next.js 的
   `NEXT_PUBLIC_*` 变量或客户端代码。前端服务端设置
   `BACKEND_API_BASE_URL` 指向后端的内部地址。
3. 在小艺开放平台创建智能体及云插件工具，将工具服务地址设为后端的
   `https://<backend-host>/api/xiaoyi/jobs`，方法为 `POST`，请求头配置
   `Authorization: Bearer <XIAOYI_PLUGIN_TOKEN>`，`Content-Type: application/json`。
   若控制台不能配置固定 Bearer 头，请使用你控制的 HTTPS 网关为该插件请求注入，
   不要把密钥塞入 URL 或 prompt。

## 工具契约

提交工具输入：

```json
{"question":"为什么机器人过不了窄门？","request_id":"550e8400-e29b-41d4-a716-446655440000"}
```

`question` 必填，不超过 500 字。`request_id` 可省略；若平台能提供每次用户
请求的稳定 UUID，请传入它以保证网络重试不会重复付费。相同 `request_id`
配不同问题会返回 409，需要换新 ID。若省略，每次调用都会创建新任务。

提交和查询都返回扁平 JSON，便于绑定小艺的输出变量：

```json
{
  "run_id": "550e8400e29b41d4a716446655440000",
  "status": "running",
  "stage": "source_ingestion",
  "message": "",
  "ready": false,
  "watch_url": "https://movie.example/xiaoyi/watch/550e8400e29b41d4a716446655440000"
}
```

状态查询工具：`GET https://<backend-host>/api/xiaoyi/jobs/{run_id}`，同样携带
Bearer 头。`ready=true` 才表示播放器结果已持久化。失败、取消或服务重启后，
`status` 会分别为 `failed`、`cancelled` 或 `interrupted`；不要自动重提交。

小艺编排建议：让智能体在收到解释机制的问题时调用提交工具；回复用户
“已开始制作，可打开卡片查看进度”，将 `watch_url` 绑定到卡片的 `webURL`
跳转变量。观看页自己继续查询，所以不需要让小艺工作流阻塞等待模型。
如果需要在聊天里回答“做好了吗”，再调用状态查询工具。平台的卡片变量、
绑卡和发布操作需在你的小艺工作空间内完成，仓库代码无法替你操作账号。

## 验收

1. 本地无模型测试：`uv run pytest tests/test_xiaoyi_bridge.py -q`。它验证认证、
   重试去重、状态和原播放器结果接口；不会访问外网或产生模型费用。
2. 控制台调试提交工具：确认返回 `run_id`、`watch_url`，且重复相同
   `request_id` 不产生第二个任务；查看后端任务日志确认真实生成完成。
3. 在鸿蒙手机上点击卡片：观看页应从真实状态变为“动画已准备好”；点击
   “播放并探索动画”后进入现有播放器，并可暂停、跳节拍、操作控件。
4. 用错误 token、空问题、未知任务 ID 各试一次，分别应得到 401、422、404。

## 公网部署边界

Render 双服务部署的具体配置见 [Render 部署指南](render-deploy.md)。

`watch_url` 包含不可猜测的任务 UUID；拿到链接的人可以查看该任务结果，
所以仅向预期用户发出，不要写入公开日志。当前 Studio 和原始
`/api/animation-jobs` 提交接口仍是本地开发接口，没有面向公网的用户认证
及配额。Render Blueprint 设置 `PUBLIC_DEMO_MODE=1` 后，后端只开放小艺桥接、
任务状态与结果 GET、健康检查，其他原有开发接口返回 403。小艺提交接口仍
要求 Bearer token。后台还需监控并发与费用。不要把未启用公开模式的开发服务
直接暴露公网。

官方资料：[小艺开放平台](https://developer.huawei.com/consumer/cn/celia)、
[云插件](https://developer.huawei.com/consumer/cn/doc/doccenter-celia/cloud-plug-in-0000002471344189)、
[卡片跳转](https://developer.huawei.com/consumer/cn/doc/doccenter-celia/multi-jump-0000002485633457)、
[上架流程](https://developer.huawei.com/consumer/cn/doc/doccenter-celia/process-introduction-0000002509696971)。
平台目前说明个人智能体使用私有云插件时只能页面调试，不能上架；发布前请
按你的账号类型与插件可见性在控制台再次确认。
