# 无界·叙事引擎 · 后端

FastAPI 后端：剧情规划、提示词编译、状态结算、存档、事实记忆与流式对话代理。

正常游玩请直接双击仓库根目录的 `启动无界.vbs`。图形启动器只打开控制面板；点击 `Start and Play` 后才会隐藏终端启动后端并打开游戏。它还负责停止、首次安装/修复、打开网页设置和日志；下面的命令只用于开发或排错。

## 快速开始

```bash
cd backend
cp .env.example .env        # 然后编辑 .env 填入你的 API key
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

Windows PowerShell：

```powershell
cd D:\claudecode\my-rpg\backend
py -3.11 -m venv .venv             # 只需首次执行；若系统没有 3.11 可换成已安装版本
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
# 至少填写一项，例如：DEEPSEEK_API_KEY=sk-你的密钥
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

`.env` 只放在 `backend/` 目录，不要提交到 Git。修改密钥后必须重启后端；
打开 `http://127.0.0.1:8000/api/providers`，看到对应后端的 `configured: true`
才表示配置生效。叙事默认关闭 DeepSeek V4 思考模式，避免思考内容耗尽输出预算；
设置页可以为场景写手、剧情规划、GM 裁定、状态审计和事实记忆分别启用。
DeepSeek 返回的 `reasoning_content` 会由非流式接口和 SSE 原样保留，前端只在本机
“后台运行监视器”显示，不会拼进小说正文或权威状态。

`.env` 中的 provider 配置如下（不需要的可以留空）：

```dotenv
DEEPSEEK_API_KEY=sk-xxxxxxxx
ZHIPU_API_KEY=xxxxxxxx
SILICONFLOW_API_KEY=sk-xxxxxxxx
OPENROUTER_API_KEY=sk-or-xxxxxxxx
DEFAULT_PROVIDER=deepseek
```

保存后重新启动 `dev.ps1`。如果 `/api/providers` 中某项仍是
`configured: false`，通常是 key 为空、变量名拼错，或后端进程没有重启。

也可以直接在游戏的“本地后端”面板中填写并保存 API Key。后端会把它写入
`backend/.env`，只允许本机浏览器访问配置接口；已有 key 只显示脱敏提示，留空不会覆盖。

打开 http://127.0.0.1:8000/docs 看接口文档。

**想用手机玩**（同一 WiFi）：

```bash
.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

手机浏览器访问 `http://<电脑局域网IP>:8000/`（用 `ipconfig` 查 IP）。

## 目录结构

| 目录 | 职责 |
|---|---|
| `app/config.py` | 配置。密钥从环境变量读，不进代码 |
| `app/domain/` | 领域数据。各 LLM 后端的调用差异集中在这里 |
| `app/schemas/` | API 契约。Pydantic 模型，自动校验+生成文档 |
| `app/services/` | 业务逻辑。真正调 API、重试、解析 |
| `app/routers/` | HTTP 层。只做收发和错误翻译，不含业务逻辑 |
| `tests/` | 测试。固化前端依赖的契约 |

分层原则：**routers 不写业务，services 不碰 HTTP**。这样业务逻辑能脱离 Web 框架单独测试。

## 测试

```bash
.venv/Scripts/python.exe -m pytest tests/ -v
```

协议级固定回放（不调用真实模型）在仓库根目录执行：

```powershell
cd D:\\claudecode\\my-rpg
backend\\.venv\\Scripts\\python.exe tools\\run_replay.py `
  --fixture research\\regression\\fixtures\\replay_baseline.json
```

它会固定模型响应，同时真实运行后端的 SQLite 账本、事实检索、提示词编译、状态结算和存档提交；当前 seed 集包含 10 个场景，覆盖普通冒险、武侠、仙侠、现代、赛博、NPC 知识、资源交易、分支和穿越入口。

## 当前进度

- [x] 对话代理（`POST /api/chat`）— key 不再下发前端
- [x] 流式 SSE 转发（`POST /api/chat/stream`）— 保留上游分帧
- [x] 后端目录（`GET /api/providers`）
- [x] 重试与错误分类
- [x] 提示词编译（`POST /api/turn/prompt`）
- [x] 剧情规划 Agent（`POST /api/story/plan/prompt` + `/api/story/plan/result`）— 维护部分有序剧情线和短期场景卡，叙事模型不读取幕后原因
- [x] 状态结算（`POST /api/state/apply`）
- [x] 存档持久化（`/api/saves`）
- [x] 结构化叙事账本（`POST/GET /api/sessions/{sid}/ledger`）— 事件、承诺/拒绝、NPC 独立知识、人物分层状态
- [x] 可解释上下文检索（`GET /api/sessions/{sid}/context`）— 按回合、来源、可见性和说话者过滤，并返回 trace
- [x] SceneContract — 因果事件、affordances、压力/悬疑预算、明确禁止项与承诺引用；旧场景卡自动兼容升级
