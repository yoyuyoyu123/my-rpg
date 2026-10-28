# 无界 · AI 互动小说与文字 RPG 引擎

一个面向长篇游玩的本地 AI 文字游戏。项目保留了原单文件 HTML 的世界选择、角色生成、存档、状态栏和即时流式阅读体验，同时用 FastAPI 后端接管提示词编译、模型代理、事实记忆、状态结算与剧情规划。

当前重点不是让模型“随便续写”，而是让程序分别负责规划、记忆、裁定和校验，让叙事模型专心写好眼前场景。

## 当前能力

- 10 个内置世界：武侠、仙侠、古代人间、剑与魔法、都市人间、现代都市、赛博未来、星海旅途、末日废土、诡秘怪谈，并支持自定义世界。
- 大量来自中国网文、日本 Web/轻小说与漫画类型研究的身份、题材、关系、开局和故事引擎标签。
- 多种 API 接入：DeepSeek、智谱 GLM、硅基流动、OpenRouter、本地 Ollama，以及前端保留的兼容直连方式。
- SSE 流式正文与可调显示速度；Enter 发送、Shift+Enter 换行。
- 自动存档、三个手动存档位、JSON 导入导出和真正连同游戏状态一起回滚的撤销。
- 权威角色状态：属性、资源、背包、装备、技能、人物关系与 NPC 独立知情范围由程序维护。
- SQLite 结构化叙事账本：分别保存带时间/来源的正史、事件链、承诺/拒绝、NPC 各自知识与人物分层动态状态，并拦截关键设定冲突。
- 剧情规划 Agent：维护部分有序软线程和短期 SceneContract；契约含因果事件、行动空间、明确禁区、承诺引用、压力/悬疑上限，只在开局、转场、明确接受/拒绝或契约到期时运行。
- 独立 GM 裁定、状态审计、事实抽取和玩家主权保护，避免模型替玩家决定、乱改数值或突然强塞剧情。
- 实时后台监视器：按回合展示事实检索、剧情规划、GM 裁定、场景写作、状态审计、保存与后台记忆的进度；每个 Agent 都可展开查看实际输入、深度思考、输出、耗时、重试和错误。
- DeepSeek 深度思考可按场景写手、规划、裁定、状态、记忆分别开关；辅助任务继承对应 Agent 的设置，推理内容只进入本机监视器，不混入小说正文。

## 剧情 Agent 如何协作

```text
玩家输入
  ↓
按时间、来源和 NPC 知情范围过滤的事实/事件/承诺检索
  ↓
剧情规划 Agent（仅开局/转场/场景到期）
  ├─ 最多 3 条剧情线
  ├─ 带前置条件的部分有序节点
  └─ 未来 2–6 回合的 SceneContract
  ↓
GM 裁定（仅危险或对抗行动）
  ↓
场景写手 → SSE 即时输出正文
  ↓
状态审计与事实抽取 → 存档
```

规划器保存“为什么现在发生”“人物想做什么”和幕后因果；写手只得到当前场景需要公开的部分以及明确的强度上限。玩家拒绝、NPC 承诺和私下所知会进入不同结构，不能再被一份模糊摘要混成共同知识。

设置页可以单独填写“规划模型”。留空时与叙事使用同一模型；也可以填写同一 API 服务商支持的便宜模型，降低规划调用成本。普通对话不会额外调用规划器，仍直接进入流式正文。

设置页的“后台运行监视器”会保留本次打开网页以来最近 80 个运行记录。左侧是各 Agent 和回合流水线，右侧可以展开输入／提示词、模型深度思考、输出／结构化结果和附加信息；记录可以导出为 JSON。监视器不记录 API Key 或请求头，但会显示游戏正文与提示词，因此分享导出文件前仍应检查其中是否含私人内容。

## 最简单的玩法（Windows）

以后正常玩不需要打开终端：

1. 双击项目根目录的 **`启动无界.vbs`**。
2. 启动器只打开控制面板，不会自动启动后端或打开游戏。
3. 点击 **Start and Play** 才启动后端并打开主界面。
4. 第一次使用或依赖损坏时，在启动器点 **Install / Repair**，完成后再点 **Start and Play**。
5. 需要填写或更换 API Key 时点 **API Settings**；它会直接打开网页里的后端配置区，Key 仍只保存在本机 `backend/.env`。

启动器还可以安全停止自己启动的后端、打开日志目录、创建桌面快捷方式。勾选同一局域网访问后，即使电脑走网线、手机走 Wi‑Fi，只要它们连接同一个路由器也可以访问。关闭启动器窗口不会中断正在玩的游戏；需要停止服务时重新打开启动器点 **Stop Backend**。

## 手动启动（开发与排错）

需要 Python 3.11 或其他可用的 Python 3 版本。

```powershell
cd D:\claudecode\my-rpg\backend

py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Copy-Item .env.example .env
.\dev.ps1
```

手动启动后打开：

- 游戏：<http://127.0.0.1:8000/>
- 后端接口文档：<http://127.0.0.1:8000/docs>
- 服务状态：<http://127.0.0.1:8000/health>

第一次运行可以直接在游戏的“本地后端”连接面板填写 API Key。Key 只写入本机的 `backend/.env`，不会保存进网页存档，也不应提交到 Git。

如果更喜欢手动配置，编辑 `backend/.env`：

```dotenv
DEEPSEEK_API_KEY=
ZHIPU_API_KEY=
SILICONFLOW_API_KEY=
OPENROUTER_API_KEY=
DEFAULT_PROVIDER=deepseek
```

修改配置后重新启动 `dev.ps1`，再检查 `/api/providers` 中相应模型服务是否显示 `configured: true`。

## GitHub Pages 说明

<https://yoyuyoyu123.github.io/my-rpg/> 目前只能托管静态页面，不能运行 FastAPI、SQLite、事实记忆、后端 Key 管理和剧情规划接口。当前完整版应通过 `http://127.0.0.1:8000/` 使用。

如果以后要恢复可公开访问的在线版本，需要把 `backend/` 单独部署到支持 Python 和持久化磁盘的服务，再让前端 API 地址指向该后端。不要把 API Key 写进 GitHub Pages 或 `index.html`。

## 项目结构

```text
my-rpg/
├─ index.html                  # 完整前端、世界选择与游戏 UI
├─ backend/
│  ├─ app/
│  │  ├─ domain/              # 世界包、规则、标签本体、模型服务目录
│  │  ├─ routers/             # 对话、规划、状态、事实、存档与配置 API
│  │  ├─ schemas/             # Pydantic 数据契约
│  │  └─ services/            # LLM、剧情规划、记忆、校验和提示词编译
│  ├─ tests/                  # 后端契约与回归测试
│  ├─ .env.example
│  └─ dev.ps1                 # Windows 启动脚本
├─ research/                  # 中日网文、轻小说与漫画类型研究数据库
├─ tools/                     # 研究数据库构建和校验工具
└─ progress.md                # 开发记录与已知验证缺口
```

更详细的后端配置见 [backend/README.md](backend/README.md)，类型研究字段见 [research/DATABASE_GUIDE.md](research/DATABASE_GUIDE.md)。

内置世界的名称、分类、快捷动作、预设和选择卡片统一维护在 [`data/worlds/catalog.json`](data/worlds/catalog.json)；服务端私有叙事资产在 `backend/app/domain/world_content.py`。不要再把世界元数据复制回 `index.html`。

## 开发文档与工作顺序

项目的开发不再以临时修补为主，统一以 [`docs/`](docs/README.md) 为基线：

- [项目基线](docs/PROJECT_BASELINE.md)：产品边界、当前链路、权威数据和不可回退体验；
- [实现原理与目标架构](docs/ARCHITECTURE.md)：分层、回合状态机、Agent 职责和数据模型；
- [功能矩阵](docs/FEATURE_MATRIX.md)：已有功能、代码位置、验证状态和缺口；
- [标准开发生命周期](docs/DEVELOPMENT_LIFECYCLE.md)：从基线冻结到发布的阶段和质量门；
- [待改进项与依赖顺序](docs/OPEN_WORK.md)：按 P0/P1/P2/P3 排序，避免无依赖地继续加功能。

今后的代码改动必须先对应一个工作项，写明输入/输出契约、失败降级、固定回放场景和验收证据；提示词调整不能替代架构设计。

## 测试

首次运行前，在仓库根目录安装前端测试依赖和 Chromium：

```powershell
npm install
npx playwright install chromium
```

前端静态契约与本地首页浏览器冒烟测试：

```powershell
npm run test:contracts
npm run test:browser:isolation
npm run test:browser:smoke
npm run test:browser:turn
npm run test:browser:mobile
npm run test:browser:stream
```

浏览器测试会自动启动独立后端，使用操作系统分配的随机端口、临时数据库和临时配置，无需手动启动游戏后端。所有浏览器测试均拒绝 `RPG_URL` 外部地址；如果以前设置过，请先清除。测试不会调用真实模型，结束后会停止自己的后端并清理临时数据。默认使用 `backend/.venv` 中的 Python，也可通过 `RPG_TEST_PYTHON` 指定 Python 可执行文件。

`browser:isolation` 验证数据库隔离、外部地址拦截和清理；`browser:smoke` 验证首页、存档入口与监视器；`browser:turn` 验证失败回滚、撤销等待和存档恢复；另外两组验证手机视口与流式协议。截图与状态输出保存在 `.playwright-artifacts/`，不会提交到 Git。

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

当前回归集覆盖模型代理、SSE、配置、事实/事件/承诺/NPC知识记忆、状态结算、世界隔离、提示词编译、SceneContract 和存档接口。

pytest 也会自动设置独立的 `WUJI_DATA_DIR`，包括 TestClient 的应用启动过程。正常启动游戏时未设置该变量，仍使用 `backend/data/wuji.db`。

固定协议回放（不调用真实模型）可在仓库根目录执行：

```powershell
backend\\.venv\\Scripts\\python.exe tools\\run_replay.py `
  --fixture research\\regression\\fixtures\\replay_baseline.json
```

当前 seed 集为 10 个协议场景；本地已有 Playwright 首页冒烟和回合事务检查，真实模型质量回放、SSE 断流、完整读档与手机交互仍在 Phase 0 待办中。

## 当前限制

- AI 叙事质量仍取决于所选模型；规划器能改善因果和节奏，但不能保证每次生成都同样精彩。
- 首次开局会先进行一次结构化规划，因此正文开始前会比普通回合多等待一次模型调用。
- 规划模型目前与叙事模型共用同一个 provider；设置中填写的模型名必须是该 provider 实际支持的模型。
- 浏览器存档和 SQLite 事实库都以本机为中心；跨设备游玩请使用游戏内 JSON 导出/导入，并确保对应后端数据可用。
- GitHub Pages 静态地址不是当前完整版的运行环境。

## 数据与隐私

- API Key：只应保存在 `backend/.env`。
- 本机存档：由浏览器存储和后端存档接口共同维护。
- 长期事实：保存在本机 SQLite 数据库。
- 玩家输入与被检索的上下文会发送给当前选择的模型服务；请遵守对应服务的隐私与内容政策。
- 后台监视器记录只保存在当前浏览器会话的内存里，刷新页面即清空；导出 JSON 是明确的本地下载操作。
