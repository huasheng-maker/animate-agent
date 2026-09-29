# Animate Agent

把一个问题变成可观察、可操作的解释动画：看质点怎样运动、矩阵怎样参与计算、生成的 token 怎样进入下一步。

项目使用模型规划受控计算图，再由本地计算库和渲染器执行。浏览器不会执行模型生成的 JavaScript、Python 或 HTML。

## 先体验三个示例（无需密钥、无需启动后端）

需要 Node.js 22 或 24、npm、Git。

```bash
git clone https://github.com/huasheng-maker/animate-agent.git
cd animate-agent
npm --prefix frontend ci
npm --prefix frontend run dev
```

打开 **http://localhost:3000/demos**：

| 示例 | 可以观察和改变什么 | 来源 |
| --- | --- | --- |
| 雷达避障实验 | 激光回波、安全膨胀、A* 路径；改变货架位置、机器人半径、量程 | 确定性教学实验，使用实际几何与路径计算 |
| 匀速圆周运动 | 切向速度、向心加速度；改变半径和角速度 | 真实模型生成后审核的计算图 |
| LLM 工作原理 | token、嵌入向量、概率与逐步生成 | 真实模型生成后审核的教学示例 |

演示文件随仓库提供，不会因为打开或拖动滑杆而调用付费 API。示例数值是教学模型，不能视为真实训练参数或设备测量值。雷达实验的已知地图模式与单帧传感模式有不同的信息边界，界面会明确显示。

LLM 示例实际计算嵌入查表、softmax、贪心选择与三轮反馈；反馈部分是仅依赖上一个 token 的简化模型，不包含完整 Attention、FFN 或 KV cache。生成任务 ID 和审核改动见 [示例来源记录](frontend/public/demos/provenance.json)。审核修正了输入绑定与简化边界文案；它不是未经审核的模型原始回复，也不保证每次自动生成都达到相同质量。

想生成自己的动画，继续下面的配置。

## 运行完整生成流程

需要 Python 3.11 或 3.12，以及 [uv](https://docs.astral.sh/uv/)。开发验证使用 Python 3.12 和 Node.js 24。

在项目根目录安装后端依赖：

```bash
uv sync --frozen --extra dev
```

创建本地配置。PowerShell：

```powershell
Copy-Item .env.example .env
```

macOS / Linux：

```bash
cp .env.example .env
```

只在本机编辑 `.env`。下面是使用一把 Kimi 密钥的最小配置：

```dotenv
KIMI_KEY=填写自己的密钥
KIMI_MODEL=kimi-k2.6
WEB_SEARCH_PROVIDER=kimi
KIMI_WEB_SEARCH_MODE=pro
WEB_READER_PROVIDER=local
```

真实生成会产生所选服务商的费用。正文读取选择 `local` 时使用项目自带的受控 HTTP 读取器，不需要额外模型密钥。

终端一，在项目根目录启动后端：

```bash
uv run python -m uvicorn animate_agent.api:app --reload --host 127.0.0.1 --port 8000
```

终端二，启动前端：

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

打开 **http://localhost:3000**，选择 Query，输入普通问题，然后点击 CREATE。也可以选择 URL 或上传受支持的文档。

- 后端健康检查：http://127.0.0.1:8000/health
- API 文档：http://127.0.0.1:8000/docs
- 后端默认端口为 8000；前端默认端口为 3000。
- 更改 `.env` 后重启后端。终端已有环境变量优先于 `.env`；`--reload` 不保证重新加载配置文件。
- 修改前端到后端的地址时，设置 `BACKEND_API_BASE_URL`，然后重启前端。

无需为了本地生成安装 Crawl4AI、Playwright 浏览器或 Docker。Crawl4AI 是可选采集适配器，不在默认网页读取路径中。

## 模型与搜索分别如何选择

| 环节 | 当前选择规则 | 配置 |
| --- | --- | --- |
| 内容规划、分镜生成 | 有 `KIMI_KEY` 时用 Kimi；否则使用 DeepSeek | `KIMI_MODEL` / `DEEPSEEK_MODEL` |
| 问题检索 | 显式选择 Gemini、Kimi 或 OpenAI | `WEB_SEARCH_PROVIDER` |
| 正文读取 | 本地 HTTP 或 Kimi Reader | `WEB_READER_PROVIDER` |

使用 Gemini 搜索：

```dotenv
WEB_SEARCH_PROVIDER=gemini
GEMINI_API_KEY=填写自己的密钥
GEMINI_WEB_SEARCH_MODEL=gemini-2.5-flash
```

这会将**搜索**切换为 Gemini。仍需配置 Kimi 或 DeepSeek 用于分镜生成；只填写 Gemini 密钥不会自动切换生成模型。不要把密钥值粘贴到日志、截图或 GitHub。

搜索保留最多三个强相关来源，优先读取两篇正文，并按输入、过程、输出、示例检查材料深度。缺少关键环节时最多补查一次。检查是启发式规则，不代表材料已经完成事实核验。网页正文先经过清洗，不会把完整 HTML 当成模型指令。

## 生成流程与错误处理

```text
Query → 搜索与正文读取 → DocumentIR → 意图分镜
URL / File / Text → 受控适配器 → DocumentIR → 课程大纲 → 分镜
                                       ↓
                         Schema / 来源 / 维度 / 数值校验
                                       ↓
                         确定性编译 → AnimationIR / RenderSpec
                                       ↓
                       Remotion + JSXGraph + mathjs 播放器
```

可组合基础能力包括小球、矢量、载具、轨迹、曲线、矩阵、token 序列、概率图和读数。模型通过受限算子声明计算关系，可以选择参数、查表、矩阵乘法、softmax 等，不需要为每个问题编写一套场景代码。

生成是后台任务。界面显示真实阶段、耗时与修复状态；刷新后可恢复任务。优先使用 SSE，连接失败时轮询状态。GET 状态请求不等于重复调用大模型。

模型输出仍可能不符合结构、数值或来源约束。服务会返回具体错误并进行有限修复；耗尽次数后停止，不会无限重试，也不会把无效数据强行送入播放器。

每次运行的诊断产物保存在 `data/runs/<run_id>/`：

- `01-source-document.json`、`02-document-ir.json`：采集材料及标准化证据；
- `04-storyboard-ir.json`：通过校验的分镜；
- `05-animation-ir.json`、`06-render-spec.json`：编译后的播放器数据；
- `*-attempt-*-raw.txt` / `*-error.txt`：被拒绝的模型输出及原因。

只有成功阶段才会留下相应文件。Query 路径不调用课程大纲模型。运行数据、SQLite 任务库、密钥和临时预览不会提交到仓库。

## 检查与生产构建

```bash
uv run pytest -q
uv run ruff check src tests
uv run mypy src
npm --prefix frontend run test:player
npm --prefix frontend run typecheck
```

停止前端开发服务器后再构建，避免开发与生产共享 `.next`：

```bash
npm --prefix frontend run build
npm --prefix frontend run start
```

本地 API 不应直接作为开放的公共生成服务；公开部署需要鉴权、限流、费用控制与出站网络隔离。现有部署说明：[Azure](docs/azure-vm-deploy.md)、[华为云](docs/huaweicloud-ecs-deploy.md)、[小艺接入](docs/xiaoyi-integration.md)。具体可用部署文件以仓库内容为准。

## 主要文件

- `src/animate_agent/sources/`：受控检索、正文读取与来源保留。
- `src/animate_agent/visualization/`：问题意图驱动的分镜与有限修复。
- `src/animate_agent/composition.py`：可组合计算图和图元的 Schema。
- `src/animate_agent/composition_math.py`：后端数值预检。
- `frontend/player/composable/`：浏览器算子与 ElementRegistry。
- `frontend/app/player/`：通用播放器与参数交互。
- `frontend/app/demos/`、`frontend/public/demos/`：可直接体验的示例及审核后的数据。

详细说明：[组件库](docs/element-registry.md) · [检索深度](docs/search-depth.md) · [雷达实验](docs/lidar-demo-report.md)。

本项目仍是研究原型。Schema 通过不等于教学内容必然正确；发布示例需要同时检查数值关系、来源与实际画面。第三方库的许可适用各自条款，Remotion 的商业使用要求请按其官方许可确认。
