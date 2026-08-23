# 功能矩阵

状态含义：

- **已实现**：代码存在，已有针对性测试或明确运行证据。
- **部分实现**：主路径可用，但缺少完整契约、迁移、回放或浏览器验证。
- **兼容层**：为了保留旧版体验而存在，目标是逐步收敛，不代表最终架构。
- **未实现**：文档或想法中存在，当前不能按完成处理。

## 用户可见功能

| 功能 | 状态 | 主要位置 | 当前说明 | 下一步验收 |
|---|---|---|---|---|
| 世界观选择与预设 | 已实现 | `index.html`, `domain/worlds.py` | 10 个内置世界及预设，自定义世界入口存在 | 建立单一世界包来源，避免前后端双份漂移 |
| 研究标签与题材组合 | 部分实现 | `research/`, `index.html` | 数据库已构建，前端使用仍是候选/补全逻辑 | 版本化查询契约和可解释选择记录 |
| 开局身份/关系/成长 | 部分实现 | `index.html` | 随机与手动设定均存在，旧存档兼容复杂 | 固定随机种子和开局回放测试 |
| 主界面/新局/存档入口 | 已实现 | `index.html` | 需保护不自动跳旧存档 | 浏览器回归覆盖冷启动、恢复、重置 |
| 自然语言输入 | 已实现 | `index.html` | 自由输入是一等入口 | 明确发送、取消、重试和错误恢复协议 |
| 行动选项 | 部分实现 | `index.html`, `tools/test-option-parser.mjs` | 支持多种旧格式和短修复 | 统一 `ActionOption` 结构，减少正文正则解析 |
| SSE 流式正文 | 已实现 | `index.html`, `routers/chat.py`, `services/llm.py` | 支持即时显示和显示速度 | 首 token、断流、重连、半成品保留的浏览器回归 |
| Enter / Shift+Enter | 已实现 | `index.html` | 已有静态契约 | 浏览器键盘测试 |
| 自动/手动存档 | 已实现 | `index.html`, `routers/saves.py` | 快照与服务端存档并存 | 统一存档来源、版本迁移和冲突策略 |
| 撤销/重生成 | 部分实现 | `index.html` | 前端备份与快照存在 | 和服务端 turn transaction 对齐，保证幂等 |
| API 设置 | 已实现 | `routers/config.py`, `index.html` | 本机 `.env` 写入、脱敏状态 | 权限边界、备份、并发写入测试 |
| Windows 启动器 | 部分实现 | `launcher.ps1`, VBS | 启停、安装、日志、设置入口存在 | 单独打包、升级、离线和异常进程回归 |
| Agent 监视器 | 部分实现 | `index.html`, `test_agent_monitor_contract.py` | 能看阶段、输入、推理、输出、耗时 | 统一事件 schema、敏感信息分级和持久化策略 |

## 叙事与游戏引擎

| 功能 | 状态 | 主要位置 | 当前说明 | 下一步验收 |
|---|---|---|---|---|
| 权威角色状态 | 部分实现 | `game_state.py`, `state.py`, `index.html` | 状态 patch/审计已存在 | 回合事务、幂等、版本冲突、全场景回放 |
| 事实库 | 已实现 | `models.py`, `memory.py`, `extractor.py` | facts/entities/alias 可检索 | 事实有效期、冲突解决和迁移脚本 |
| 事件账本 | 部分实现 | `narrative_memory.py` | 已有结构化事件写入 | 与 turn_id 和状态提交绑定 |
| 承诺/拒绝 | 部分实现 | `narrative.py`, `models.py` | 表和接口存在 | 统一创建/履行/违反/废弃生命周期 |
| NPC 独立知识 | 部分实现 | `NpcBelief`, `narrative_memory.py` | 有知识层和检索 trace | 加密/可见性规则与固定回放 |
| 人物动态状态 | 部分实现 | `CharacterState` | 身份/中期/短期层次已建 | 关系更新规则、衰减和可解释来源 |
| SceneContract | 部分实现 | `story.py`, `story_planner.py`, `prompt_builder.py` | 规划器输出并注入写手 | 用回放验证玩家分叉、刷新和失效 |
| 剧情规划 Agent | 部分实现 | `story_planner.py`, `index.html` | 开局/转场/契约到期触发 | 规划结果与回合事务绑定，失败降级清晰 |
| GM/规则裁定 | 部分实现 | `index.html`, `state.py` | 条件触发，模型辅助 | 把可程序化规则逐步移出提示词 |
| 状态审计/patch | 部分实现 | `index.html`, `game_state.py` | 能拒绝部分错误 patch | 统一 schema、错误码和回放差异 |
| 章节摘要 | 兼容层 | `index.html` | 浏览器侧仍有历史压缩 | 迁移为服务端、版本化、可追溯摘要 |
| 类型/风格数据库 | 部分实现 | `research/` | 研究库内容丰富 | 与运行时通过小型 affordance 查询连接 |

## 工程质量

| 能力 | 状态 | 当前证据 | 缺口 |
|---|---|---|---|
| Python 单测/API 测试 | 已实现 | `backend/tests/` | 依赖本地环境 | CI/覆盖率/数据库迁移测试 |
| 前端静态契约 | 已实现 | `tools/test-*.mjs` | 能防关键函数/格式回归 | 需要真正浏览器测试 |
| 多回合回放 | 部分实现 | `research/regression/` | 场景 fixture 已有 | 统一 replay runner 和指标输出 |
| 浏览器自动化 | 未完成 | Playwright 脚本存在但环境缺包 | 安装/锁定浏览器测试依赖 |
| API 文档 | 已实现 | FastAPI `/docs` | 业务语义和错误码不完整 | 版本化 OpenAPI 和示例 |
| 发布流程 | 部分实现 | 启动器、README、GitHub Pages 说明 | 无版本、变更日志、打包验收 | 建立 release checklist |

