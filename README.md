# 无界 · AI 互动小说与文字 RPG 引擎

一个面向长篇游玩的本地 AI 文字游戏。项目保留了原单文件 HTML 的世界选择、角色生成、存档、状态栏和即时流式阅读体验，同时由 FastAPI 后端提供提示词编译、模型代理、事实记忆、状态结算与剧情规划服务，前端仍负责回合编排、显示和状态交互。

当前重点不是让模型“随便续写”，而是让程序分别负责规划、记忆、裁定和校验，让叙事模型专心写好眼前场景。

## 项目文档

- [当前状态](STATUS.md)：已实现内容、验证缺口与下一步。
- [协作规则](AGENTS.md)：交接顺序、信息状态与维护要求。
- [当前架构](docs/architecture.md)：前后端职责、入口与研究数据链。
- [决策与约束](docs/decisions.md)：现有依据和待确认事项。
- [溯源规则](docs/provenance.md)：正本分工、来源和验证记录。
- [开发历史](progress.md)：保留历史过程，其中旧待办不代表当前计划。

以下能力描述以仓库实现为基础；当前验证状态以 STATUS.md 为准。

## 当前能力

- 10 个内置世界：武侠、仙侠、古代人间、剑与魔法、都市人间、现代都市、赛博未来、星海旅途、末日废土、诡秘怪谈，并支持自定义世界。
- 大量来自中国网文、日本 Web/轻小说与漫画类型研究的身份、题材、关系、开局和故事引擎标签。
- 多种 API 接入：DeepSeek、智谱 GLM、硅基流动、OpenRouter、本地 Ollama，以及前端保留的兼容直连方式。
- SSE 流式正文与可调显示速度；Enter 发送、Shift+Enter 换行。
- 自动存档、三个手动存档位、JSON 导入导出和真正连同游戏状态一起回滚的撤销。
- 权威角色状态：属性、资源、背包、装备、技能、人物关系与 NPC 独立知情范围由程序维护。
- SQLite 事实档案：长期保存人物身份、地点、关系、承诺和重要事件，并拦截关键设定冲突。
- 剧情规划 Agent：维护部分有序剧情节点和短期场景卡；只在开局、转场或场景卡到期时运行。
- 独立 GM 裁定、状态审计、事实抽取和玩家主权保护，避免模型替玩家决定、乱改数值或突然强塞剧情。

## 剧情 Agent 如何协作

```text
玩家输入
  ↓
事实检索与权威状态
  ↓
剧情规划 Agent（仅开局/转场/场景到期）
  ├─ 最多 3 条剧情线
  ├─ 带前置条件的部分有序节点
  └─ 未来 2–6 回合的公开场景卡
  ↓
GM 裁定（仅危险或对抗行动）
  ↓
场景写手 → SSE 即时输出正文
  ↓
状态审计与事实抽取 → 存档
```

规划器保存“为什么现在发生”“人物想做什么”和幕后因果；写手只能看到当前场景需要公开的部分。这样可以减少突然天命、毫无铺垫的宏大危机、全员谜语人和无关景物堆砌。

设置页可以单独填写“规划模型”。留空时与叙事使用同一模型；也可以填写同一 API 服务商支持的便宜模型，降低规划调用成本。普通对话不会额外调用规划器，仍直接进入流式正文。

## Windows 快速启动

需要 Python 3.11 或其他可用的 Python 3 版本。

```powershell
cd D:\claudecode\my-rpg\backend

py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Copy-Item .env.example .env
.\dev.ps1
```

启动后打开：

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

## 测试

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

当前回归集覆盖模型代理、SSE、配置、事实记忆、状态结算、世界隔离、提示词编译、剧情规划结构和存档接口。

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
