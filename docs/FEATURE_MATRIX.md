# 功能矩阵

状态含义：

- **已实现**：代码存在，已有针对性测试或明确运行证据。
- **部分实现**：主路径可用，但缺少完整契约、迁移、回放或浏览器验证。
- **兼容层**：为了保留旧版体验而存在，目标是逐步收敛，不代表最终架构。
- **未实现**：文档或想法中存在，当前不能按完成处理。

## 用户可见功能

| 功能 | 状态 | 主要位置 | 当前说明 | 下一步验收 |
|---|---|---|---|---|
| 世界观选择与预设 | 已实现 | `data/worlds/catalog.json`, `domain/worlds.py`, `index.html` | 10 个内置世界的公开元数据只有一个版本化来源；私有 prompt 留在后端，自定义世界入口保留 | 新增世界时用契约测试检查状态模板和扩展映射 |
| 研究标签与题材组合 | 部分实现 | `research/`, `index.html` | 数据库已构建，前端使用仍是候选/补全逻辑 | 版本化查询契约和可解释选择记录 |
| 开局身份/关系/成长 | 部分实现 | `index.html` | 随机与手动设定均存在，旧存档兼容复杂 | 固定随机种子和开局回放测试 |
| 主界面/新局/存档入口 | 已实现 | `index.html` | 需保护不自动跳旧存档 | 浏览器回归覆盖冷启动、恢复、重置 |
| 自然语言输入 | 已实现 | `index.html` | 自由输入是一等入口 | 明确发送、取消、重试和错误恢复协议 |
| 行动选项 | 部分实现 | `index.html`, `backend/app/services/writer_output.py`, `tools/test-option-parser.mjs` | 支持纯文本兼容、结构化写手信封和短修复；结构化开关默认关闭 | 固定剧本比较结构化/纯文本的延迟、完整度和状态拒绝率 |
| SSE 流式正文 | 已实现 | `index.html`, `routers/chat.py`, `services/llm.py` | 支持即时显示、显示速度和半截断流诊断；浏览器验收覆盖分段回调与完成标记缺失 | 真实供应商断流、重连、完整读档回归 |
| Enter / Shift+Enter | 已实现 | `index.html` | 已有静态契约 | 浏览器键盘测试 |
| 自动/手动存档 | 已实现 | `index.html`, `routers/saves.py` | 服务端为准、本地镜像降级；版本冲突有本机/服务端/稍后处理选择；浏览器已验证服务端写入、读取并恢复到游戏界面 | 真实多设备并发和完整读档长历史验收 |
| 撤销/重生成 | 已实现 | `index.html`, `turn_rollback.py` | 等待服务端回滚后再改本地历史；失败保持原剧情，账本原地更新可逐级恢复 | 最终并入服务端 TurnService 的单事务提交 |
| API 设置 | 已实现 | `routers/config.py`, `index.html` | 本机 `.env` 写入、脱敏状态 | 权限边界、备份、并发写入测试 |
| Windows 启动器 | 部分实现 | `launcher.ps1`, VBS | 启停、安装、日志、设置入口存在 | 单独打包、升级、离线和异常进程回归 |
| Agent 监视器 | 部分实现 | `index.html`, `routers/agent_runs.py`, `test_agent_monitor_contract.py` | 运行记录已有 run/parent/session/turn ID，能看阶段、输入、推理、输出、耗时；后端模式会尽力写入 `agent_runs`，打开监视器可按会话回读，API 与前端都支持回合/Agent/状态筛选与分页；提交/恢复/冲突已有专门生命周期记录 | 权限/保留策略和敏感信息分级 |

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
| 状态审计/patch | 部分实现 | `index.html`, `game_state.py`, `rules_engine.py` | 背包/资源/属性/技能/NPC/位置与风险检定已由程序结算；移动/交易/任务已有 `/api/rules/action` 契约 | 浏览器自然语言意图接入、统一错误码 |
| 服务端 TurnService | 部分实现 | `application/turn_service.py`, `schemas/turn_commit.py`, `index.html` | 后端模式的 HTML 最终提交已接入：以 commit_id 幂等原子提交叙事账本、会话回合号和自动存档；直接 API/后端不可用仍保留兼容路径 | 将检索、规划、裁定、流式写作和状态审计逐段迁入同一状态机，并补 pending commit 恢复 |
| 章节摘要 | 兼容层 | `index.html` | 浏览器侧仍有历史压缩 | 迁移为服务端、版本化、可追溯摘要 |
| 类型/风格数据库 | 部分实现 | `research/` | 研究库内容丰富 | 与运行时通过小型 affordance 查询连接 |

## 工程质量

| 能力 | 状态 | 当前证据 | 缺口 |
|---|---|---|---|
| Python 单测/API 测试 | 已实现 | `backend/tests/` | 依赖本地环境 | CI/覆盖率/数据库迁移测试 |
| 前端静态契约 | 已实现 | `tools/test-*.mjs` | 覆盖开局、选项、诊断、回合事务和世界目录漂移 | 随功能迁移继续减少纯字符串断言 |
| 多回合回放 | 部分实现 | `backend/replay/`, `research/regression/fixtures/`, `quality_metrics.py` | 10/10 确定性协议场景稳定通过；历史对局可计算冲突、穿越、世界风味、选项完整度和谜语人信号 | 接入真实 Planner、玩家分叉差异、因果连续和无关描写评价 |
| 浏览器自动化 | 已实现 | Playwright、本地 Chromium | 覆盖首页、存档入口、世界目录、失败回滚、撤销等待、深快照、服务端读档恢复、SSE 半截正文和 390px 手机视口 | 真实模型与多设备并发 |
| API 文档 | 已实现 | FastAPI `/docs` | 业务语义和错误码不完整 | 版本化 OpenAPI 和示例 |
| 发布流程 | 部分实现 | 启动器、README、GitHub Pages 说明 | 无版本、变更日志、打包验收 | 建立 release checklist |
