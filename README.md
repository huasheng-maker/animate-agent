# Animate Agent（Intuition Engine Agent）

Animate Agent 是一个把技术文档、网页、文本和教学资料转换为可交互教学内容的原型项目。它的目标不是生成普通摘要页，而是逐步构建 **Interactive Knowledge Movie（交互式知识影片）**：用受控的数据结构描述知识、镜头、视觉对象和交互，再由前端渲染器播放。

当前仓库仍处于原型阶段，已经具备：

- 可直接打开的静态首页与机器人避障交互 Demo；
- Web Search / 单页 Web Reader / Text / File → `SourceDocument[]` → `DocumentIR` 的统一边界；
- `DocumentIR` → `LessonIR` → `StoryboardIR` → `RenderSpec` 的动画编排链路；
- FastAPI URL 文档、课程与动画接口，以及对应的 Next.js 同源代理；
- 可直接接收接口 `RenderSpec` 的 Canvas 播放器。

> URL 动画生成会调用配置的 OpenAI-compatible LLM 两次；采集内容先被清洗、转换并通过严格 IR 校验，完整 HTML 不会直接进入模型，播放器也不会执行模型生成代码。

当前工作分支 `baseline/pre-refactor` 用于保留大规模重构前的真实实现。这里的“baseline”只有在相关源码、配置、测试和文档被审核并提交后才是可恢复快照；仅创建分支不会保存未提交工作区。

## 1. 当前架构

当前 URL 主路径为：

```text
静态视觉原型
frontend/demo/index.html → intuition-home.js → Canvas 交互演示

Query → Gemini/OpenAI/Kimi Search   ┐
URL   → local/Kimi Web Reader       ├→ SourceDocument[] → DocumentIRBuilder → DocumentIR
Text  → TextAdapter                 │
File  → FileAdapter                 ┘
    → KnowledgeAgent → LessonIR
    → StoryboardAgent → StoryboardIR
    → layout_storyboard → RenderSpec
    → FastAPI response → sessionStorage → Canvas 播放器
```

当前 Next.js 首页只暴露 URL 和 Query 两种输入。文件上传仅接到 FastAPI 的
`POST /api/lessons/from-file`，Text/File 尚未接入网页端完整动画流程。Query 搜索结果是带引用的
provider synthesis；当前不会再逐个抓取所有引用页面。默认 URL Reader 是受 SSRF、重定向、大小和
内容类型限制的静态 HTTP 单页读取器，Crawl4AI 只作为显式 optional adapter 存在。

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

默认 URL 主链路不需要浏览器。如需显式使用 optional Crawl4AI adapter：

```powershell
uv sync --extra dev --extra crawl4ai
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

### 2.4 方式二：运行 URL 文档/动画 API 与查看器

先启动 FastAPI：

```powershell
uv run uvicorn animate_agent.api:app --reload
```

默认 URL 主路径不启动 Playwright，因此不依赖浏览器事件循环。只有显式使用 optional
Crawl4AI adapter 时才会进入浏览器采集路径；生产运行仍建议去掉 `--reload`，并为浏览器采集配置
容器隔离和出口网络控制。

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

打开 `http://localhost:3000`，输入公开网页 URL 后可以选择 `Inspect DocumentIR` 检查结构，或选择“生成动画”运行完整编排并进入播放器。浏览器先请求同源的 Next.js API 路由，再由 Next.js 访问 FastAPI，因此即使 Next.js 自动切换端口，也不会产生浏览器跨域问题。文档与动画结果分别保存到：

```text
data/documents/{document_id}.json
data/generated/render-{storyboard_id}.json
```

也可以直接调用接口：

```powershell
$body = @{ url = "https://raw.githubusercontent.com/ManimCommunity/manim/main/docs/source/tutorials/quickstart.rst" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/documents/from-url" -ContentType "application/json" -Body $body

# 需要在 .env 中配置 KIMI_KEY 或 DEEPSEEK_KEY
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/animations/from-url" -ContentType "application/json" -Body $body
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

### 2.6 方式四：显式使用 optional Crawl4AI Adapter

默认 URL 入口使用轻量单页 Web Reader。只有动态网页、未来整站文档或多页任务才显式选择 Crawl4AI：

```python
import asyncio

from animate_agent.sources.crawl4ai import Crawl4AIAdapter
from animate_agent.sources.models import UrlSourceInput


async def main() -> None:
    async with Crawl4AIAdapter() as adapter:
        documents = await adapter.resolve(UrlSourceInput(url="https://docs.example.com/guide"))
        print(documents[0].title)
        print(documents[0].content)


asyncio.run(main())
```

统一来源架构见 [`docs/source-ingestion.md`](docs/source-ingestion.md)；Crawl4AI 专项策略见 [`docs/web-ingestion-crawl4ai.md`](docs/web-ingestion-crawl4ai.md)。

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
| `.env.example` | LLM、Web Search、Web Reader 和本地服务环境变量示例。 | 增加配置项时只写空值或非敏感默认值，不写真实密钥。 |
| `.gitignore` | 排除虚拟环境、依赖、缓存、构建结果和生成数据。 | 出现新的本地产物时补充精确规则。 |
| `AGENTS.md` | 仓库内自动化 Agent 的工作与安全协议，不是业务代码。 | 仅在明确维护 Agent 协议时修改。 |

### 3.2 配置与样例数据

| 文件 | 功能 | 常见修改场景 |
| --- | --- | --- |
| `config/app.example.yaml` | 应用、路径、渲染器和 Agent 约束示例；当前代码实际加载 `knowledge`、`storyboard` 和 `animation`，但不读取 `app`、`paths`、`llm`。 | 调整 Agent 约束时同步校验代码；未接入的区段不能当作运行时事实。 |
| `data/samples/robot_obstacle_avoidance.md` | 机器人避障教学内容样例。 | 测试新的解析、分镜或模板生成流程。 |
| `data/samples/ros_pub_sub.md` | ROS 发布/订阅教学内容样例。 | 验证 ROS 知识对象和场景模板。 |
| `data/documents/*.json` | URL 解析接口生成的 `DocumentIR` 文件。默认被 Git 忽略。 | 调试解析结果；不应当作手写源码维护。 |

### 3.3 Python 包：`src/animate_agent/`

| 文件 | 功能 | 适合扩展的位置 |
| --- | --- | --- |
| `__init__.py` | Python 包入口和当前版本号。 | 发布新版本时更新版本策略。 |
| `api.py` | 提供 URL/Query 文档与动画、URL 课程和文件课程 API，并将采集异常映射为 HTTP 状态。 | 添加健康检查、生命周期管理或统一错误响应。 |
| `documents/models.py` | 定义严格校验的 `DocumentSource`、`DocumentBlock`、`Section` 和 `DocumentIR`。 | 增加跨来源都稳定的语义字段；变更时同步 API、前端和测试。 |
| `documents/builder.py` | 只消费 `SourceDocument[]`，确定性构建带 provenance 的 `DocumentIR`。 | 扩展统一内容格式映射；不得加入 HTTP、搜索或供应商 SDK。 |
| `documents/fetcher.py` | 早期 legacy httpx 下载器；当前 URL API 不再使用。 | 仅用于兼容或离线实验，不应绕过统一安全入口。 |
| `documents/parser.py` | 确定性清洗 HTML，优先 `main/article/[role=main]`，提取标题、章节、段落、代码、列表和图片。 | 增加表格、引用等 block 类型，或针对站点完善噪声选择器。 |
| `documents/normalized.py` | 兼容性桥接：将旧采集边界 `NormalizedDocument` 转为 `DocumentIR`；不在默认 URL 主路径。 | 在明确保留旧边界时维护，不应导入 Crawl4AI 私有类型。 |
| `documents/service.py` | 串联安全采集、转换、校验和 DocumentIR 持久化。 | 改存储后端、增加去重/缓存，或接入新解析适配器。 |
| `documents/__init__.py` | 导出常用 DocumentIR 类型和 `parse_html()`。 | 新增稳定公共 API 时更新。 |
| `animation/elements.py` | 旧手写 Scene 数据结构，仅供模板基线和 CLI 兼容路径使用。 | 不应作为新的 LLM 生成链路扩展点。 |
| `animation/templates.py` | 旧机器人避障和 ROS 手写模板，通过 `rendering/legacy.py` 转为当前 `RenderSpec`。 | 仅维护基线对照；新能力优先进入 Storyboard/RenderSpec。 |
| `animation/service.py` | 编排 URL → lesson → storyboard → layout，并持久化 `RenderSpec`。 | 增加任务队列、结果状态或存储后端。 |
| `animation/__init__.py` | 汇总导出动画公共类型。 | 新元素成为公共 API 时更新。 |
| `interaction/controls.py` | 定义 slider、toggle、button 和拖拽目标等交互 Spec。 | 新增选择器、输入框、时间线控制等控件。 |
| `interaction/__init__.py` | 交互子包入口。 | 需要公开稳定交互 API 时补充导出。 |
| `rendering/layout.py` / `rendering/models.py` | 将语义 Storyboard 确定性布局为严格 `RenderSpec`。 | 增加受控图元、预设与布局规则。 |
| `storyboard/` | 定义、生成并校验 `StoryboardIR`。 | 扩展语义角色、规则和模型提示。 |

### 3.4 来源解析与可选采集基础设施

`src/animate_agent/sources/` 是默认业务边界：`models.py` 定义 `SourceDocument` / `SourceInput`，`resolver.py` 做 query/url/text/file 确定性路由，`adapters.py` 实现 hosted Web Search、单页 Reader、Text 与 File adapter，`crawl4ai.py` 提供显式 optional adapter。

`src/animate_agent/ingestion/` 保留 URL 安全策略、静态 HTTP reader 基础设施和 Crawl4AI 兼容层：

| 文件 | 功能 | 适合扩展的位置 |
| --- | --- | --- |
| `models.py` | 定义旧 URL/原始 HTML 采集输入、`WebIngestionConfig` 和 `NormalizedDocument`。 | 主要服务 Crawl4AI 兼容层；默认业务来源模型位于 `sources/models.py`。 |
| `base.py` | 定义旧 `NormalizedDocument` 采集协议。 | 仅在继续维护该兼容边界时扩展。 |
| `router.py` | 旧采集路由器；当前 API 和 `SourceResolver` 没有调用它。 | 不应与 `sources/resolver.py` 同时扩展，需先决定是否保留。 |
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
| `frontend/app/page.tsx` | URL/Query 输入、DocumentIR 查看器、动画生成入口及 `sessionStorage` 播放器交接。 | 拆分组件、增加 block 类型、进度和错误状态。 |
| `frontend/app/api/documents/from-url/route.ts` | 同源 API 代理，把浏览器请求转发给本地 FastAPI，避免浏览器 CORS 和 loopback 限制。 | 后端地址变化时设置 `BACKEND_API_BASE_URL`，或在这里增加超时与统一错误格式。 |
| `frontend/app/api/animations/from-url/route.ts` | 动画生成接口的同源代理。 | 接入异步任务状态或统一超时策略。 |
| `frontend/app/player/route.ts` | 将 `/player?spec=...` 保持同源地转到播放器运行时。 | 增加可分享的持久化结果 URL。 |
| `frontend/app/player-runtime/[asset]/route.ts` | 通过白名单复用现有播放器静态资源。 | 播放器拆包或部署目录改变时更新白名单。 |
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
| `tests/test_source_pipeline.py` | SourceResolver 路由、各 Web Search/Reader provider、SourceDocument schema、provenance 和文件来源。 |
| `tests/test_url_animation_pipeline.py` | NormalizedDocument 兼容转换、安全 URL 拒绝、统一来源摄取和完整动画编排。 |

> 当前 `.gitignore` 工作区修改包含过宽的 `tests` 规则，会让这两份测试从普通 `git status` 中消失；建立 baseline 提交前必须移除或缩窄该规则，并确认测试文件被 Git 跟踪。

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

### 4.1 增加新的输入来源

推荐在 `src/animate_agent/sources/` 下新增 Adapter：

1. 定义输入模型；
2. 实现 `resolve()`；
3. 输出统一的 `SourceDocument[]`；
4. 在 `SourceResolver` 注册确定性路由；
5. 用离线 fixture 添加单元测试。

不要让路由器依赖 PDF/PPTX 库的内部对象，也不要把供应商专有字段直接塞入稳定模型。

### 4.2 扩展 `SourceDocument[] → DocumentIR`

当前已有独立、确定性的转换 service：

```text
SourceDocument[] → DocumentIRBuilder → Pydantic validation → persistence/API
```

Builder 不得导入 Crawl4AI、Web Search、HTTP fetch 或供应商 response 类型。

### 4.3 扩展 DocumentIR

可以在 `documents/models.py` 增加表格、引用、公式、术语、来源定位等稳定语义类型，但需要同步修改：

- `documents/parser.py` 的提取逻辑；
- `frontend/app/page.tsx` 的类型和渲染分支；
- `test_source_pipeline.py` / `test_url_animation_pipeline.py` 及相关 fixture；
- 已持久化 JSON 的兼容或迁移策略。

### 4.4 扩展 Storyboard 与 RenderSpec

- 语义对象、步骤和控件契约放在 `storyboard/models.py`；
- 可用 role、primitive、prop 和 behavior 放在 `rendering/registry.py`；
- 确定性坐标与几何转换放在 `rendering/layout.py`；
- 浏览器绘制和行为分别放在 `frontend/player/primitives.js` 与 `behaviors.js`。

新增 primitive 时必须同步 Python registry/layout、严格 `RenderSpec` 模型和 JavaScript player；未知类型应显式失败，不能静默丢弃。

### 4.5 Renderer 能力边界

当前真正实现并接入的是 Canvas 2D。配置中的 `svg_2d`、`three_3d` 只是允许值，尚无对应编译器或播放器；`renderer_hint` 当前不会选择另一套引擎。

在新增 SVG、Three.js 或视频渲染器前，应先定义能力矩阵、路由位置和版本兼容策略。Renderer 只能消费受控 Spec，并对支持的元素与控件做显式校验。

### 4.6 扩展 AI 阶段

当前已经有两个模型阶段：Knowledge Agent 生成 `LessonIR`，Storyboard Agent 生成 `StoryboardIR`。扩展时仍应只用于：

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

当前仓库没有 `tests/integration/test_crawl4ai_smoke.py`。真实 Crawl4AI 或外网验证必须单独、显式运行；普通测试应使用 fake client/snapshot。前端 `typecheck/build` 只能证明编译通过；修改视觉或交互后，还应在真实浏览器中检查布局、输入、错误态和操作流程。

## 6. 当前限制与建议开发顺序

当前限制：

- URL 动画生成是同步请求，两次 LLM 调用与单页读取可能耗时较长，尚无队列和进度 API；
- `RenderSpec` 虽会落盘，但当前网页使用 `sessionStorage` 交给播放器，尚无可分享结果 ID 页面；
- Python 与 JavaScript 各自维护一份 render vocabulary，存在 primitive/prop 漂移风险；播放器尚未检查 `spec_version`；
- 配置允许 `svg_2d`、`three_3d`，但当前只有 Canvas 2D 实现；
- FileAdapter 当前经过 `DocumentIR → Markdown → SourceDocument → DocumentIR` 的重复转换；
- `SourceDocument` 主路径与 `NormalizedDocument` 兼容路径并存，边界尚未收敛；
- Crawl4AI 应用层检查不能替代生产环境的容器隔离和网络出口控制；
- legacy `documents/fetcher.py` 仍保留，但当前 URL API 已不再调用它；
- query 搜索默认需要 `GEMINI_API_KEY`，也可选择 OpenAI 或 Kimi Tools Search；URL 默认走本地安全 Reader，也可选择 Kimi Tools Fetch；Kimi 搜索、抓取及后续 LLM 阶段可以复用同一项目 `KIMI_KEY`。

建议开发顺序：

1. 审核并提交 `baseline/pre-refactor`：修正测试忽略规则，纳入两份测试，排除 secret、生成物和临时目录；
2. 让 renderer 配置与真实 Canvas 能力一致，并让播放器拒绝不支持的 `spec_version`；
3. 消除 FileAdapter 的重复解析，同时用聚焦测试证明各文件格式的结构与 provenance 不退化。

更完整的产品目标和交互流程可继续阅读 [`docs/poject-overall/PROJECT_EXPECTATIONS.md`](docs/poject-overall/PROJECT_EXPECTATIONS.md) 与 [`docs/interaction-flow/INTERACTION_FLOW.md`](docs/interaction-flow/INTERACTION_FLOW.md)。
