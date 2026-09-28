# 知识驱动的教学动画：实现核查与 Demo 验证

日期：2026-09-22。依据当前工作区代码，包括开始任务时已经存在的 Remotion 播放器、分镜约束等未提交改动；没有把这些已有改动计为本次完成的工作。

## 运行与体验

当前入口：<http://localhost:3000/demos/lidar>。首页右上角新增“雷达绕障实验”。只需前端服务，无模型凭证、后端服务或网络请求：

```powershell
cd D:\桌面\animate-agent\frontend
npm run dev
```

浏览器打开 `/demos/lidar`，点击播放，或直接选下面的四个章节。24 秒讲解结束后可拖动进度条或重新选章节。修改参数会暂停并跳回相关章节，重新计算全部结果。

建议依次验证：

1. 默认播放：看到首个表面回波、安全禁区、真实 A* 访问顺序、机器人沿 14.8 m 栅格路线绕过货架。
2. 移动货架：路线变化；不是让机器人沿固定曲线做同一动作。
3. 选择窄门：半径 0.17 m 可通过，增大到 0.50 m 后停驶。
4. 选择封路：搜索结束但无路径，机器人保持起点。
5. 缩短量程：已知地图模式路线不变；切换“仅起点单帧雷达”后，未知空间禁行，可能不能证明通路存在。

## 当前实际生成链路

| 层 | 当前实现及代码证据 | 能力与边界 |
|---|---|---|
| 输入与采集 | [`SourceResolver.resolve`](../src/animate_agent/sources/resolver.py)，[`api.py`](../src/animate_agent/api.py) | Query → Search，URL → Reader，Text → TextAdapter，File → FileAdapter；路由由代码决定。当前公开动画端点包含 URL、Query、File 及固定样例，不应把内部 TextSourceInput 能力称作已有文本动画端点。 |
| 文档 | [`ingest_source`](../src/animate_agent/documents/service.py)、[`DocumentIRBuilder`](../src/animate_agent/documents/builder.py)、[`DocumentIR`](../src/animate_agent/documents/models.py) | 转成有来源与 block ID 的段落、代码、方程、图片等；结构化内容不是物理世界或算法执行模型。 |
| 教学理解 | [`generate_animation`](../src/animate_agent/animation/service.py) | Query 保留用户问题，走 `generate_intent_storyboard`，跳过 LessonIR；URL/File/Text 走 `generate_lesson` → `generate_storyboard`。LessonIR 已有 concepts、causal/spatial 等 relationships，不能说项目完全没有知识关系。 |
| 语义分镜 | [`StoryboardIR/StoryboardStep`](../src/animate_agent/storyboard/models.py)、[`visualization/prompts.py`](../src/animate_agent/visualization/prompts.py)、[`validation.py`](../src/animate_agent/storyboard/validation.py) | 已有教学目标、问题、claims/source_refs、visual_pattern、对象状态和控件。模型不写坐标或执行代码；校验并重试结构、引用和可绘制性错误。 |
| 布局 | [`layout_storyboard`](../src/animate_agent/rendering/layout.py) | 语义角色确定性落入预设槽位；不是任意空间布局或碰撞世界。产生 RenderSpec v1。 |
| 动画编译 | [`compile_storyboard/_compile_beat`](../src/animate_agent/animation_ir/compiler.py)、[`AnimationIR`](../src/animate_agent/animation_ir/models.py) | 产生受控变换、样式与语义轨道，编译高亮/描线/缩放等；嵌入 `RenderSpec.animation_ir` 并保存各阶段文件。 |
| 播放 | [`player/page.tsx`](../frontend/app/player/page.tsx)、[`KnowledgeMovieComposition`](../frontend/app/player/KnowledgeMovieComposition.tsx) | `normalizeRenderSpec` → `buildBeatSeries` → Remotion Player/Series；帧驱动每个 beat，带字幕与来源。 |
| 运行时 | [`runtime.js`](../frontend/player/runtime.js)、[`timeline.js`](../frontend/player/timeline.js)、[`behaviors.js`](../frontend/player/behaviors.js) | 轨道采样 + 可回放行为 → Scene State；支持用户覆盖、seekFrame 和确定性重放。GSAP 为既有缓动实现，没有必要另造时间引擎。 |
| 绘制 | [`canvas2d-renderer.js`](../frontend/player/canvas2d-renderer.js)、[`registry.js`](../frontend/player/registry.js)、[`primitives.js`](../frontend/player/primitives.js) | 消费已经解算的 Scene State。实际有 11 种 drawer，包括 body/emitter/trace/vector/axis/dimension 等；region/wave 明确 pending。`body.glyph` 会报错，不能把 schema 或词表中的 robot/lidar 名字当作已有图形资产。 |

## 单调的原因：观察与推断分开

- **已观察：语义变化要求偏弱。** `StoryboardStep._must_change_something` 接受仅 highlights 的步骤。它保证“画面变了”，不保证“解释了一个机制”。已有 evidence 校验很有价值，但不能验证观众能否理解。
- **已观察：编译器表达趋同。** `_compile_beat` 对多类对象应用相似 glow/scale/phase 轨道，对 link/trace 做描线。不同知识可以得到外观很相似的动画；加更多缓动仍不会自动得到算法模型。
- **已观察：既有避障不是 A*。** `behaviors.js` 的 proximity_gate/clearance_choice 依据附近物体和上下净空做局部偏移。没有全局栅格搜索、最短路径或不可达证明，不能拿它展示“路径规划算法已经运行”。
- **已观察：视觉对象有落地缺口。** drawer 能画圆、多边形、向量和测量注释，不只是矩形；但 glyph 数据与绘制并未连通。固定预设布局也无法表达任意障碍空间。
- **推断：缺少教学目标到领域模型的桥梁，是主要瓶颈之一。** 当前有知识关系，但缺少“这个关系必须用哪种可计算模型证明”的受控选择与验收。Demo 复用原有播放器和运行时便能展示更有意义的变化，支持这一判断。
- **未验证：不能断言具体 LLM 没理解意图。** 本次没有调用付费模型，也未复现某次历史生成输入/输出。模型理解、提示词和资料质量对最终生成质量的贡献仍需后续对照实验。

## 本次实现

先写了[手工教学设计](lidar-teaching-plan.md)，再实现四拍、三个环境和六个交互参数。

- [`model.js`](../frontend/player/lidar/model.js)：射线与矩形的最近交点；量程裁剪；观测 free/occupied/unknown；保守配置空间膨胀；四邻接 A*；实际访问顺序和 g/h/f 数值。
- [`scene.js`](../frontend/player/lidar/scene.js)：确定性领域适配器，把路径转换为现有 AnimationIR 受控位置/朝向轨道；没有模型生成的执行代码。
- [`LidarComposition`](../frontend/app/demos/lidar/LidarComposition.tsx)：复用 `createAnimationRuntime`、`createCompositionStage`、`createCanvas2DRenderer` 和 `body` drawer。领域覆盖层负责栅格、射线、回波、路线、货架与轮子细节。
- [`page.tsx`](../frontend/app/demos/lidar/page.tsx)：复用已安装的 Remotion Player；参数、章节、预测问题与答案。没有新增 npm 依赖。
- 原 renderer 只新增默认保持开启的 `chrome` 选项，让 Demo 关闭通用车道背景，用领域栅格替代；原播放器行为不变。

本例是静态二维离散教学模型，不是 ROS/Nav2 仿真器。默认规划使用完整先验地图，雷达负责展示当前观测；只有单帧模式用扫描证据构建规划输入。单帧模式中的场景实物仍可供观众看到，但规划器只读取观测，未知格禁行。执行时重新测距用于显示，不做在线 SLAM、地图累计或边走边重规划。交互重新规划会重新从起点解释。

路线在当前四邻接图上最短，不宣称是连续空间的全局最短曲线。膨胀加半格保守修正，执行忽略动力学及转弯半径；这些假设也展示在页面上。

## Visual Plan 最小契约

可执行验证定义：[`visual_planning.py`](../src/animate_agent/visual_planning.py) 的 `VisualPlan`；实例：[`visual-plan.json`](../frontend/player/lidar/visual-plan.json)。用 `VisualPlan.model_json_schema()` 可直接导出 JSON Schema。当前仅允许 `lidar-grid-v1`，不是声称支持所有知识领域的通用 schema。

| 字段 | 本阶段用途 | 与既有 IR 的分工 |
|---|---|---|
| version | 契约版本 | 不改 RenderSpec/AnimationIR 版本 |
| goal | 可检验的学习目标 | 对应 Storyboard 教学目标 |
| source_refs | DocumentIR block ID | 不重复存原文；校验全部存在 |
| relations | cause → effect，最多 6 条 | 选出本次必须解释的核心关系，不另建知识图谱 |
| model | 受控模型 ID + 简化假设 | 选择本地可信计算能力；不允许代码或未知引擎 |
| beats | id/title/change/explanation/source_ref | 关键可见变化；可映射 Storyboard steps，旁白来自这里 |
| interactions | 白名单参数 → 预期观察 | 描述教学实验；范围和默认值由可信实现约束 |
| checks | 问题、答案、关联实验 | 检查是否理解机制；不声称机器已评价人类学习效果 |

已验证：合法实例；额外任意代码字段被拒绝；未知模型拒绝；拍顺序/证据/实验引用错误拒绝；来源绑定到实际[手工 DocumentIR](../data/samples/documents/lidar_navigation.document.json) 的三个 block。

兼容接入建议：`DocumentIR + 学习意图 → VisualPlan → 已有 StoryboardIR → 领域适配器/AnimationIR → Runtime → Renderer`。现有 LessonIR 可供 plan 选择关系，不再抄一份 LessonIR 全量内容。Visual Plan 作为可选旁路产物保存，旧 API 不需要新增必填字段。

**实现边界：**本次 Demo 用手工 Visual Plan 提供教学文本，用本地模型求解，再直接适配到现有 AnimationIR。尚未实现 LLM 自动生成 Visual Plan、Visual Plan → StoryboardIR 的通用编译，或让现有任意主题生成端点调用这个模型。普通 `/player` 也不会仅凭一份通用 RenderSpec 自动获得本例专用雷达覆盖层。

## 验证结果

| 检查 | 结果 |
|---|---|
| `npm run test:player` | 32 项通过；包含既有运行时回归及 7 项领域/轨道测试 |
| A* 正确性 | 独立 BFS oracle 对照三个环境 × 三种半径；路径边仅四邻接，不穿膨胀区 |
| 几何正确性 | 六个货架位置，沿连续路径分段采样检查半径 + 余量净空；射线首交点/遮挡/量程检查；沿路线观测不会把实体占用格记为空闲 |
| 时间线 | 正向/反向 seek 同帧同结果；到达目标；无路径无运动；环境变更替换轨迹 |
| Visual Plan | 标准库 unittest 2 个测试方法通过，包含 5 类错误输入子案例及失效文档引用案例 |
| TypeScript | `npm run typecheck` 通过 |
| Production build | 在 `output/lidar-build-check` 独立复制源码、链接本地 node_modules 后 `next build` 通过，含 `/demos/lidar` 静态页面；没有与正在运行的开发服务共享 `.next` |
| 浏览器 | Playwright 真实 Chromium：播放/暂停、章节跳转、运动/到达、货架移动、已知地图量程不变、未知禁行、大小机器人过窄门、完全封路、重置、答案展开均通过 |
| 移动端 | 390 × 844，无横向溢出；截图查看通过。建议桌面查看栅格细节 |
| 错误与警告 | 浏览器无应用 pageerror；Remotion 自带许可提示 warning 保留，没有通过设置“已确认许可”来掩盖它 |
| 未执行 | pytest 全套、Ruff、strict mypy：当前 `.venv` 和系统 Python 均缺相应模块。没有安装额外工具；不能把 unittest/tsc 成功等同于这些检查成功 |
| 未验证 | 真实 LLM 自动生成、真实机器人、动态世界、长期用户学习效果、其他浏览器；本阶段没有 MP4 交付要求 |

复现本次新增验证：

```powershell
npm --prefix frontend run test:player
npm --prefix frontend run typecheck
.venv/Scripts/python.exe -m unittest discover -s tests -p test_visual_plan.py -v
playwright-cli -s=lidar open http://localhost:3000/demos/lidar
playwright-cli -s=lidar run-code --filename=scripts/verify-lidar-browser.cjs
```

## 关键画面

- [安全膨胀](../output/playwright/lidar-inflation.png)
- [A* 搜索展开](../output/playwright/lidar-search.png)
- [沿规划路线绕障](../output/playwright/lidar-route.png)
- [到达目标](../output/playwright/lidar-arrived.png)
- [大机器人无法通过窄门](../output/playwright/lidar-narrow-door.png)
- [未知空间禁行](../output/playwright/lidar-unknown.png)
- [封路停驶](../output/playwright/lidar-no-route.png)
- [移动端](../output/playwright/lidar-mobile.png)

截图为本机 `output/playwright/` 验证产物，属于被 Git 忽略的输出目录；需要分享报告时应一并复制这些文件。

## 后续建议（未实现）

1. 先把 `lidar-grid-v1` 做成一个受控领域能力入口：返回状态与执行轨迹，由编译器映射到已有轨道/专用覆盖层；再让规划器在白名单里选择它。不要让 LLM 生成 A* 或射线代码。
2. 建立小规模教学验收集：是否看见关键关系、交互是否改变结果、失效条件是否正确、是否存在“会动但没有解释”的拍。保持原有来源校验，再增加领域不变量校验。
3. 把 Visual Plan 的 `change` 从单纯描述逐步绑定到领域输出字段，例如 visited/path/reachable；只为第二个真实案例增加必要 schema 字段，不提前建设大而全 DSL。
4. 视觉资产按需要补 robot/sensor 等少量受控对象，并同时补布局、validator 和真实 drawer。先修词表到可见对象的闭环，再考虑单个需要的第三方引擎。
5. 用同一文档和问题比较“原自动链路”与“带受控 Visual Plan 的链路”。这一步需真实模型调用与用户评估，才能判断自动生成是否也达到教学目标。

原理参考：[Nav2 机器人轮廓与半径](https://docs.nav2.org/rolling/configuration_and_development/first_time_robot_setup_guide/footprint/setup_footprint/)、[Nav2 膨胀层](https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/costmap_2d/costmap_plugins/inflation/)、[A* 网格启发式](https://theory.stanford.edu/~amitp/GameProgramming/Heuristics.html)。本例只采用这些基本原理，不声称复制了 Nav2 的代价地图或运动控制实现。
