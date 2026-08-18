# 无界·叙事引擎 · 后端

FastAPI 后端。当前阶段：**对话代理**（把 API key 从浏览器收归服务端）。

## 快速开始

```bash
cd backend
cp .env.example .env        # 然后编辑 .env 填入你的 API key
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

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

## 当前进度

- [x] 对话代理（`POST /api/chat`）— key 不再下发前端
- [x] 后端目录（`GET /api/providers`）
- [x] 重试与错误分类
- [ ] 提示词组装搬后端
- [ ] 状态结算搬后端
- [ ] 存档持久化
