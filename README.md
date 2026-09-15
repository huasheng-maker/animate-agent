# Animate Agent（Intuition Engine Agent）

Animate Agent 是一个把技术文档、网页、文本和教学资料转换为可交互教学内容的原型项目。它的目标不是生成普通摘要页，而是逐步构建 **Interactive Knowledge Movie（交互式知识影片）**：用受控的数据结构描述知识、镜头、视觉对象和交互，再由前端渲染器播放。

当前仓库仍处于原型阶段，已经具备：

- 可直接打开的静态首页与机器人避障交互 Demo；
- URL → HTML → `DocumentIR` → JSON 的确定性解析链路；
- FastAPI 接口和用于检查 `DocumentIR` 的 Next.js 页面；
- 基于 Crawl4AI 的 URL / 原始 HTML 安全采集层，输出稳定的 `NormalizedDocument`；
- 可序列化的动画元素、交互控件和两套教学场景模板。

> 当前尚未打通 `NormalizedDocument → DocumentIR → Storyboard → Renderer` 的完整链路，也没有接入 LLM 自动生成动画。两个文档采集实现会在后文单独说明。

## 1. 当前架构

仓库中有三条可以独立使用的路径：

```text
静态视觉原型
frontend/demo/index.html → intuition-home.js → Canvas 交互演示

第一阶段文档解析链路（已接 API 和查看器）
URL → documents/fetcher.py → documents/parser.py → DocumentIR
    → data/documents/*.json → FastAPI → Next.js 查看器

新 Web 采集边界（尚未接入上述 API）
URL / 原始 HTML → Crawl4AIWebDocumentAdapter → NormalizedDocument
    → 后续待实现的 DocumentIR 转换层
```

核心边界应保持为：

```text
URL / File → 确定性 Parser / Adapter → 经过校验的 IR → AI 规划 → 受控动画 Spec → Renderer
```

网页完整 HTML 和网页中的指令都应视为不可信数据，不应直接交给模型执行；前端也不应执行模型任意生成的代码。

## 2. 快速开始

### 2.1 环境要求

- Python 3.11 或更高版本；
- 与 Next.js 15 兼容的 Node.js 环境（运行查看器时需要）；
- 推荐使用 [uv](https://docs.astral.sh/uv/) 管理 Python 依赖；也可以使用传统 `venv + pip`。

### 2.2 安装 Python 依赖

推荐方式：

```powershell
uv sync --extra dev
```

如需使用真实的 Crawl4AI 浏览器采集，再安装浏览器运行环境：

```powershell
uv run crawl4ai-setup
```

如果上一步没有成功安装 Chromium：

```powershell
uv run python -m playwright install chromium
```

不使用 uv 时：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pip install -e .
```

### 2.3 方式一：查看静态交互 Demo

直接用浏览器打开：

```text
frontend/demo/index.html
```

也可以启动一个静态文件服务器，避免浏览器对本地文件的限制：

```powershell
python -m http.server 4173 --directory frontend/demo
```

然后访问 `http://127.0.0.1:4173`。页面可以填写文本、选择示例、导入本地文件，并体验机器人避障的 Canvas 动画与参数控件。当前“生成”过程是前端原型逻辑，不会调用后端或 AI。

### 2.4 方式二：运行 DocumentIR API 与查看器

先启动 FastAPI：

```powershell
uv run uvicorn animate_agent.api:app --reload
```

或使用虚拟环境：

```powershell
.\.venv\Scripts\python.exe -m uvicorn animate_agent.api:app --reload
```

API 默认地址为 `http://127.0.0.1:8000`，交互式接口文档位于 `http://127.0.0.1:8000/docs`。
只运行前端而没有启动这个 API 时，页面无法连接 `localhost:8000`，浏览器会显示连接后端的提示。

另开一个 PowerShell 窗口安装并启动前端：

```powershell
npm --prefix frontend install
npm --prefix frontend run dev
```

打开 `http://localhost:3000`，输入公开网页 URL 后即可查看解析出的章节、段落、代码、列表和图片。浏览器先请求同源的 Next.js API 路由，再由 Next.js 访问 FastAPI，因此即使 Next.js 自动切换端口，也不会产生浏览器跨域问题。成功请求会把经过 Pydantic 校验的结果保存到：

```text
data/documents/{document_id}.json
```

也可以直接调用接口：

```powershell
$body = @{ url = "https://docs.manim.community/en/stable/tutorials/quickstart.html" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/documents/from-url" -ContentType "application/json" -Body $body
```

如后端不在默认地址运行，可在启动 Next.js 前设置服务端代理地址：

```powershell
$env:BACKEND_API_BASE_URL = "http://127.0.0.1:8000"
npm --prefix frontend run dev
```

只有在明确需要浏览器直接跨域请求 FastAPI 时，才设置公开变量 `NEXT_PUBLIC_API_BASE_URL`。

### 2.5 方式三：在 Python 中生成动画 Scene Spec

现有模板会生成受控、可序列化的场景数据，并不会直接渲染动画：

```python
import json

from animate_agent.animation.templates import build_robot_obstacle_avoidance_scene

scene = build_robot_obstacle_avoidance_scene()
print(json.dumps(scene.to_spec(), ensure_ascii=False, indent=2))
```

运行示例：

```powershell
uv run python your_script.py
```

也可以使用 `build_ros_pub_sub_scene()` 生成 ROS Publisher / Topic / Subscriber 教学场景。

### 2.6 方式四：单独使用 Crawl4AI Web 采集层

这条链路用于将 URL 或原始 HTML 规范化为 `NormalizedDocument`，目前不会写入 JSON，也不会调用 `DocumentIR`、Storyboard 或渲染器。

```python
import asyncio

from animate_agent.ingestion import UrlInput, WebIngestionConfig
from animate_agent.ingestion.web import Crawl4AIWebDocumentAdapter


async def main() -> None:
    config = WebIngestionConfig(
        allowed_domains=frozenset({"docs.example.com"}),
        timeout_seconds=20,
    )
    async with Crawl4AIWebDocumentAdapter(config) as adapter:
        document = await adapter.ingest(
            UrlInput(url="https://docs.example.com/guide")
        )
        print(document.title)
        print(document.text_content)


asyncio.run(main())
```

原始 HTML 输入可改为：

```python
from animate_agent.ingestion import RawHtmlInput

document = await adapter.ingest(
    RawHtmlInput(html="<main><h1>Hello</h1><p>World</p></main>")
)
```

详细的安全策略、保留策略和升级方法见 [`docs/web-ingestion-crawl4ai.md`](docs/web-ingestion-crawl4ai.md)。

## 3. 目录与文件说明

下面列出仓库中的源码、配置、测试和主要文档。运行时生成的 `.venv/`、`node_modules/`、`.next/`、缓存和 `data/documents/*.json` 不属于源码，因此不逐项列出。

### 3.1 根目录

| 文件 | 功能 | 常见修改场景 |
| --- | --- | --- |
| `README.md` | 项目总览、安装、运行、文件职责和扩展指南。 | 入口、依赖、目录或运行方式变化时同步更新。 |
| `pyproject.toml` | Python 包元数据、运行依赖、dev 依赖以及 pytest、Ruff、mypy 配置。 | 新增依赖、调整 Python 版本或质量规则。 |
| `uv.lock` | uv 锁定的完整依赖版本，用于可复现安装。 | 修改依赖后通过 uv 重新生成，不建议手工编辑。 |
| `requirements.txt` | pip 方式使用的运行依赖。 | 新增生产依赖时与 `pyproject.toml` 保持同步。 |
| `requirements-dev.txt` | pip 方式使用的开发、测试和静态检查依赖。 | 新增开发工具时更新。 |
| `.env.example` | 本地环境变量示例，目前记录应用环境、主机、端口和静态 Demo 目录。 | 增加配置项时只写示例，不写真实密钥。 |
| `.gitignore` | 排除虚拟环境、依赖、缓存、构建结果和生成数据。 | 出现新的本地产物时补充精确规则。 |
| `AGENTS.md` | 仓库内自动化 Agent 的工作与安全协议，不是业务代码。 | 仅在明确维护 Agent 协议时修改。 |

### 3.2 配置与样例数据

| 文件 | 功能 | 常见修改场景 |
| --- | --- | --- |
| `config/app.example.yaml` | 应用、路径、允许的渲染器和 Agent 约束的示例配置。当前源码尚未自动加载它。 | 设计统一配置加载器时可作为 schema 起点。 |
| `data/samples/robot_obstacle_avoidance.md` | 机器人避障教学内容样例。 | 测试新的解析、分镜或模板生成流程。 |
| `data/samples/ros_pub_sub.md` | ROS 发布/订阅教学内容样例。 | 验证 ROS 知识对象和场景模板。 |
| `data/documents/*.json` | URL 解析接口生成的 `DocumentIR` 文件。默认被 Git 忽略。 | 调试解析结果；不应当作手写源码维护。 |

### 3.3 Python 包：`src/animate_agent/`

| 文件 | 功能 | 适合扩展的位置 |
| --- | --- | --- |
| `__init__.py` | Python 包入口和当前版本号。 | 发布新版本时更新版本策略。 |
| `api.py` | 创建 FastAPI 应用，提供 `POST /api/documents/from-url`，并配置本地 Next.js CORS。 | 添加健康检查、生命周期管理、新输入接口和统一错误响应。 |
| `documents/models.py` | 定义严格校验的 `DocumentSource`、`DocumentBlock`、`Section` 和 `DocumentIR`。 | 增加跨来源都稳定的语义字段；变更时同步 API、前端和测试。 |
| `documents/fetcher.py` | 使用 httpx 下载 HTML，处理重定向、超时、HTTP 错误和内容类型。 | 调整请求头、超时或注入更严格的网络安全策略。 |
| `documents/parser.py` | 确定性清洗 HTML，优先 `main/article/[role=main]`，提取标题、章节、段落、代码、列表和图片。 | 增加表格、引用等 block 类型，或针对站点完善噪声选择器。 |
| `documents/service.py` | 串联下载、解析、校验和 JSON 持久化。 | 改存储后端、增加去重/缓存，或接入新解析适配器。 |
| `documents/__init__.py` | 导出常用 DocumentIR 类型和 `parse_html()`。 | 新增稳定公共 API 时更新。 |
| `animation/elements.py` | 定义动画元素、ROS 对象、时间线步骤和 `Scene`，并负责序列化为 Spec。 | 新增可复用视觉对象、时间线字段或渲染器无关属性。 |
| `animation/templates.py` | 提供机器人避障和 ROS 发布/订阅两套 Scene 模板。 | 增加新的教学主题模板或组合已有元素。 |
| `animation/__init__.py` | 汇总导出动画公共类型。 | 新元素成为公共 API 时更新。 |
| `interaction/controls.py` | 定义 slider、toggle、button 和拖拽目标等交互 Spec。 | 新增选择器、输入框、时间线控制等控件。 |
| `interaction/__init__.py` | 交互子包入口。 | 需要公开稳定交互 API 时补充导出。 |
| `rendering/__init__.py` | 预留渲染层包，目前尚无实际渲染器。 | 实现 Canvas、SVG、Three.js 等 Renderer Adapter。 |
| `storyboard/__init__.py` | 预留分镜层包，目前尚无 Storyboard IR。 | 实现知识结构到镜头/时间线的转换。 |

### 3.4 新采集边界：`src/animate_agent/ingestion/`

| 文件 | 功能 | 适合扩展的位置 |
| --- | --- | --- |
| `models.py` | 定义 URL/原始 HTML 输入、`WebIngestionConfig`、保留/缓存策略和稳定的 `NormalizedDocument`。 | 添加跨采集后端稳定的字段；避免暴露 Crawl4AI 私有结构。 |
| `base.py` | 定义通用异步 `DocumentAdapter` 协议。 | PDF、PPTX、DOCX、Markdown 等新适配器实现此协议。 |
| `router.py` | 根据输入类型选择已注册的 Adapter。 | 注册新的文档来源，不在路由器中写供应商逻辑。 |
| `security.py` | 校验 URL、DNS、域名白名单和浏览器子请求，阻止私网、localhost 与元数据地址。 | 根据部署网络增加策略；生产环境仍应配合容器和出口防火墙。 |
| `exceptions.py` | 定义稳定、可安全展示的采集错误类型。 | 新失败类别应保持用户信息与开发诊断分离。 |
| `web/contracts.py` | 定义应用自有的 Crawl 快照 DTO 和 Invoker 协议。 | 适配其他浏览器采集器时复用或实现等价边界。 |
| `web/crawl4ai_adapter.py` | 唯一直接接触 Crawl4AI API 的兼容层，并管理浏览器生命周期。 | Crawl4AI 升级时优先只检查和修改此文件。 |
| `web/normalizer.py` | 将采集快照纯转换为章节、代码、表格、图片、链接等规范结构。 | 改进无副作用的内容归一化规则。 |
| `web/__init__.py` | 对外导出 `Crawl4AIWebDocumentAdapter`。 | Web 采集公共 API 变化时更新。 |
| `ingestion/__init__.py` | 汇总导出路由器、输入、配置和标准输出模型。 | 新类型成为稳定入口时更新。 |

### 3.5 前端

| 文件 | 功能 | 常见修改场景 |
| --- | --- | --- |
| `frontend/package.json` | Next.js 项目依赖与 `dev/build/start/typecheck` 命令。 | 添加 UI 依赖或脚本。 |
| `frontend/package-lock.json` | npm 的精确依赖锁。 | `npm install` 后自动更新，不建议手工编辑。 |
| `frontend/tsconfig.json` | TypeScript 编译配置。 | 调整严格度、路径别名或编译目标。 |
| `frontend/next-env.d.ts` | Next.js 自动生成的类型声明入口。 | 通常不手工编辑。 |
| `frontend/app/layout.tsx` | App Router 根布局与页面 metadata。 | 修改全局语言、标题、图标或全局 Provider。 |
| `frontend/app/page.tsx` | DocumentIR 查看器：提交 URL、调用 FastAPI、选择章节并渲染 block。 | 拆分组件、增加 block 类型、错误态和后续动画入口。 |
| `frontend/app/api/documents/from-url/route.ts` | 同源 API 代理，把浏览器请求转发给本地 FastAPI，避免浏览器 CORS 和 loopback 限制。 | 后端地址变化时设置 `BACKEND_API_BASE_URL`，或在这里增加超时与统一错误格式。 |
| `frontend/app/globals.css` | Next.js 查看器的全局样式与响应式布局。 | 修改查看器视觉系统和移动端适配。 |
| `frontend/app/icon.svg` | Next.js 页面图标。 | 更换品牌图标。 |
| `frontend/demo/index.html` | 静态首页结构、输入区、结果区和机器人 Canvas。 | 调整原型信息架构或新增静态 Demo 面板。 |
| `frontend/demo/intuition-home.js` | 当前静态首页的输入、文件读取、示例切换、生成状态和 Canvas 动画逻辑。 | 修改原型交互、绘制算法或接入受控后端接口。 |
| `frontend/demo/intuition-home.css` | 当前首页特有的视觉样式。 | 修改品牌、输入区、结果布局和动画效果。 |
| `frontend/demo/styles.css` | 静态 Demo 的基础样式与旧课件样式，当前 `index.html` 仍会加载。 | 修改共享布局时注意不要破坏旧样式。 |
| `frontend/demo/app.js` | 早期 ROS/机器人互动课件逻辑；当前 `index.html` 没有加载它。 | 可作为旧交互参考；重新启用前应明确独立入口或模块化。 |

### 3.6 测试

| 文件 | 覆盖内容 |
| --- | --- |
| `tests/fixtures/manim_quickstart.html` | 确定性 HTML 解析测试使用的离线页面夹具。 |
| `tests/unit/test_document_ingestion.py` | httpx 下载、HTML 清洗、DocumentIR、API 和 JSON 持久化。 |
| `tests/unit/test_animation_elements.py` | 动画元素与场景 Spec 序列化。 |
| `tests/unit/test_animation_templates.py` | 两套教学场景模板的结构。 |
| `tests/unit/test_ingestion_security.py` | URL、DNS、域名白名单、私网和子资源安全策略。 |
| `tests/unit/test_web_document_adapter.py` | Crawl4AI Adapter、保留策略、归一化、错误和生命周期。 |
| `tests/integration/test_crawl4ai_smoke.py` | 使用真实浏览器的可选 Crawl4AI smoke test。默认测试不会运行它。 |

### 3.7 文档与设计资料

| 文件/目录 | 功能 |
| --- | --- |
| `docs/document-ingestion-milestone.md` | 第一阶段 URL → DocumentIR → JSON → Viewer 的运行与验证说明。 |
| `docs/web-ingestion-crawl4ai.md` | 新 Web 采集层的架构、安全、配置、使用和升级说明。 |
| `docs/poject-overall/PROJECT_EXPECTATIONS.md` | 产品愿景、体验目标、Agent 工作流和当前范围。目录名 `poject-overall` 是现有历史命名。 |
| `docs/poject-overall/TECH_STACK.md` | 后端、前端、动画 Spec 与模板库技术选型。 |
| `docs/poject-overall/TODO.md` | MVP 功能清单和质量标准。 |
| `docs/poject-overall/PLAN.md` | 技术栈、任务拆分和阶段计划。 |
| `docs/interaction-flow/INTERACTION_FLOW.md` | 用户从输入资料到进入交互知识影片的流程说明。 |
| `docs/interaction-flow/interaction-flow.drawio` | 可继续编辑的 draw.io 流程图源文件。 |
| `docs/interaction-flow/*.png` | 流程图的预览或导出图片。 |
| `docs/prompt/Animate Agent 架构分析与技术路线设计.md` | 早期架构分析需求与设计思路，属于参考材料，不是运行时配置。 |

## 4. 哪些地方可以灵活扩展

### 4.1 增加 PDF、PPTX、DOCX 或 Markdown 输入

推荐在 `src/animate_agent/ingestion/` 下新增 Adapter：

1. 定义输入模型；
2. 实现 `DocumentAdapter.supports()` 与异步 `ingest()`；
3. 输出统一的 `NormalizedDocument`；
4. 在 `DocumentIngestionRouter` 的组装位置注册；
5. 用离线 fixture 添加单元测试。

不要让路由器依赖 PDF/PPTX 库的内部对象，也不要把供应商专有字段直接塞入稳定模型。

### 4.2 打通 `NormalizedDocument → DocumentIR`

这是当前最自然的下一层。建议新建独立、确定性的转换 service：

```text
NormalizedDocument → DocumentIR mapper → Pydantic validation → persistence/API
```

转换层不应导入 Crawl4AI；这样未来更换采集器或增加文件 Adapter 时，后续 AI 与动画模块无需改变。

### 4.3 扩展 DocumentIR

可以在 `documents/models.py` 增加表格、引用、公式、术语、来源定位等稳定语义类型，但需要同步修改：

- `documents/parser.py` 的提取逻辑；
- `frontend/app/page.tsx` 的类型和渲染分支；
- fixture 与 `test_document_ingestion.py`；
- 已持久化 JSON 的兼容或迁移策略。

### 4.4 增加动画对象和教学模板

- 通用视觉对象放在 `animation/elements.py`；
- 可操作参数放在 `interaction/controls.py`；
- 某一教学主题的组合放在 `animation/templates.py`；
- 浏览器渲染实现放在 `rendering/`，不要把 React、Three.js 或 Canvas 实例写进 Scene 数据模型。

模板适合按“教学主题”扩展，例如 Transformer 注意力、算法执行、网络请求链路、机械臂运动学等。

### 4.5 实现 Renderer Router

`rendering/` 当前为空，可以按 Scene 类型或能力选择：

- Canvas 2D：大量对象、粒子和实时交互；
- SVG：结构图、节点连线、流程动画；
- Three.js：空间结构和 3D 机械对象；
- 视频渲染器：需要离线导出时使用。

Renderer 应只消费受控 Spec，并对支持的元素与控件做显式校验。

### 4.6 接入 AI

AI 最适合放在经过校验的 IR 之后，用于：

- 识别教学目标与关键概念；
- 规划 Storyboard；
- 从已登记的模板和视觉组件中选择组合；
- 生成旁白、镜头参数和交互提示。

AI 输出仍应通过 Pydantic/JSON Schema 校验，并限制为允许的模板、元素、属性和动作；不要让模型输出任意前端代码再执行。

### 4.7 调整采集安全与内容保留

`WebIngestionConfig` 可调整域名白名单、超时、重定向、最大 HTML 大小、JavaScript、缓存、链接/图片提取和 `minimal/standard/full` 保留策略。生产环境不要仅依赖 Python 校验，还应使用隔离容器和出口网络规则阻止私网访问。

## 5. 开发与验证

运行 Python 单元测试和静态检查：

```powershell
uv run pytest
uv run ruff check src tests
uv run mypy src
```

运行前端检查：

```powershell
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

真实 Crawl4AI 浏览器测试是可选集成测试，需要已安装浏览器，并可能访问网络：

```powershell
$env:RUN_CRAWL4AI_INTEGRATION = "1"
uv run pytest -m integration tests/integration/test_crawl4ai_smoke.py
```

普通 `uv run pytest` 会跳过该集成测试。前端 `typecheck/build` 只能证明编译通过；修改视觉或交互后，还应在真实浏览器中检查布局、输入、错误态和操作流程。

## 6. 当前限制与建议开发顺序

当前限制：

- Crawl4AI 的 `NormalizedDocument` 尚未接入 FastAPI 的 DocumentIR 接口；
- `storyboard/` 与 `rendering/` 仍是预留包；
- 静态 Demo 的生成流程主要是演示，不代表真实 Agent 已接通；
- `config/app.example.yaml` 与 `.env.example` 尚未形成统一配置加载机制；
- 当前 API 的直接 httpx 下载链路不具备新 Crawl4AI 层同等级别的 SSRF 防护，不适合原样暴露到不受信任的公网环境；
- 尚未提供 PDF/PPTX/DOCX 的实际 Adapter，也没有 LLM 调用与密钥配置。

建议开发顺序：

1. 实现并测试 `NormalizedDocument → DocumentIR` 转换层；
2. 让 FastAPI 使用统一的 `DocumentIngestionRouter` 和生命周期管理；
3. 定义 Storyboard IR 与 JSON Schema；
4. 实现一个只支持少量元素的 Canvas/SVG Renderer；
5. 最后在 IR 与模板边界之间接入 AI，并添加 schema 校验、重试和可观测性。

更完整的产品目标和交互流程可继续阅读 [`docs/poject-overall/PROJECT_EXPECTATIONS.md`](docs/poject-overall/PROJECT_EXPECTATIONS.md) 与 [`docs/interaction-flow/INTERACTION_FLOW.md`](docs/interaction-flow/INTERACTION_FLOW.md)。
