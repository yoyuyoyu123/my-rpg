# 实现原理与目标架构

这份文档把“当前实现”与“目标实现”分开。目标不是继续增加 Agent，而是让状态、回合和责任边界清晰。

## 1. 目标分层

```text
Presentation Layer
  浏览器 UI / SSE 渲染 / 选项 / 设置 / 监视器

Application Layer
  GameLoop / TurnService / SaveService / AgentOrchestrator

Domain Layer
  GameState / Rules / SceneContract / Commitments / NPC Knowledge

Memory Layer
  Facts / Events / Beliefs / Character State / Summaries / Retrieval

Infrastructure Layer
  SQLite / LLM Providers / SSE / .env / filesystem / launcher
```

当前 `index.html` 同时承载 Presentation、Application 的一部分和若干 Domain 逻辑；这正是后续必须逐步收敛的主要结构问题。

## 2. 回合状态机

```text
IDLE
  -> VALIDATING_INPUT
  -> RETRIEVING_CONTEXT
  -> RISK_GATE
       ├─ no_refresh -> COMPILE_PROMPT
       ├─ scene_refresh -> PLAN_SCENE -> COMPILE_PROMPT
       └─ rule_action -> APPLY_RULE -> COMPILE_PROMPT
  -> STREAM_NARRATIVE
  -> PARSE_OUTPUT
  -> VALIDATE_PATCH
       ├─ accepted -> COMMIT_TURN
       ├─ rejected -> KEEP_NARRATIVE_AND_REJECT_PATCH
       └─ ambiguous_high_risk -> TARGETED_REVIEW
  -> QUEUE_MEMORY_EXTRACTION
  -> IDLE

任何阶段 -> FAILED
FAILED 必须保留用户输入、错误原因和可恢复状态，不得清空历史。
```

### 一回合的事务边界

服务端最终应以 `turn_id` 为幂等键，保存：

1. 玩家输入；
2. 使用的状态版本和 SceneContract 版本；
3. 检索到的事实 ID 与过滤理由；
4. 规划/裁定/写手的模型调用记录；
5. 原始正文和解析后的选项；
6. 候选 patch、审计结果和最终应用 patch；
7. 事件、承诺、事实抽取任务；
8. 完成、失败或部分完成状态。

这样重试不会重复扣钱、重复发物品或重复推进时间。

## 3. Agent 职责

| Agent/模块 | 运行时机 | 输入 | 输出 | 禁止事项 |
|---|---|---|---|---|
| Context Compiler（程序） | 每回合 | 状态、事实、事件、人物知识、玩家输入 | 可追踪上下文 | 不写小说、不猜秘密 |
| Risk Gate（程序） | 每回合 | 输入、SceneContract、状态 | 是否刷新/裁定/审计 | 不生成剧情 |
| Scene Planner（模型） | 开局、换场、契约失效 | 事实与目标 | SceneContract/软线程 | 不写正文、不预定玩家选择 |
| Rules/GM（程序优先） | 高风险行动 | 规则、状态、行动 | 结果和可应用 patch | 不改文风、不替玩家决定 |
| Narrative Writer（模型） | 每回合 | SceneContract、公开事实、输入 | 正文、选项、候选 patch | 不修改权威状态、不偷看 private cause |
| Patch Validator（程序） | 有候选 patch 时 | 当前状态、patch、规则 | 接受/拒绝/错误 | 不凭审美改剧情 |
| Targeted Reviewer（模型） | 硬规则无法判定时 | 指定冲突证据 | 二元判断/局部修复建议 | 不全文重写 |
| Memory Extractor（后台） | 回合后 | 已完成回合 | 候选事实/事件/人物状态 | 不阻塞正文、不覆盖正史 |

默认目标是普通回合一次写手模型调用；场景刷新回合增加一次 planner；高风险且程序无法判定时才增加 reviewer。

## 4. 数据模型

### `GameSession`

一局游戏的身份、世界、预设、版本、当前回合、状态快照和运行配置。

### `CanonFact`

不可被普通摘要覆盖的正史。关键字段：`id`、`scope`、`subject_id`、`predicate`、`value`、`source_kind`、`valid_from`、`valid_to`、`certainty`、`status`。

### `EventRecord`

按时间排列的行动与结果，包含参与者、地点、因果 ID、可见性和来源。

### `NpcBelief`

某个 NPC 自己知道、听说、推测或误解的内容；不能把整个世界事实表直接给所有 NPC。

### `Commitment`

玩家承诺、NPC承诺、拒绝、期限和软剧情约束。必须显式记录状态，防止同一钩子换名重发。

### `CharacterDynamicState`

身份锚点、长期目标、中期变化、短期情绪、关系数值和衰减规则分离保存。

### `SceneContract`

写手当前只能使用的场景契约：处境、因果桥、参与者意图、公开信息、行动空间、禁止项、压力/悬疑预算、停点和刷新时间。

## 5. 记忆检索原则

```text
实体/行动识别
  -> 候选召回（FTS/别名/结构字段）
  -> 按 session、时间、source、visibility、speaker 过滤
  -> 事实有效期与冲突处理
  -> 重要度/新近度排序
  -> 编译成短上下文 + included/excluded trace
```

向量检索只能作为候选召回，不能绕过人物知识和可见性过滤。研究标签也只能作为创作候选，不是每回合规则墙。

## 6. API 契约分组

| 分组 | 现有接口 | 目标 |
|---|---|---|
| 系统/配置 | `/health`、`/api/config`、`/api/providers` | 本机配置和服务诊断 |
| 世界 | `/api/worlds` | 世界/预设目录，未来由版本化世界包提供 |
| 对话 | `/api/chat`、`/api/chat/stream` | 供应商代理和 SSE |
| 回合 | `/api/turn/prompt`、`/api/state/apply` | 当前兼容层；最终由 `TurnService` 统一编排 |
| 规划 | `/api/story/plan/prompt`、`/api/story/plan/result` | SceneContract 生成与校验 |
| 记忆 | `/api/sessions/*` | 事实、事件、承诺、NPC知识和上下文检索 |
| 存档 | `/api/saves/*` | 快照保存、读取、删除和槽位管理 |

API 以后必须补充：契约版本、错误码、幂等键、超时语义和向后兼容策略。

## 7. 目标目录结构

不立即重写单文件前端，先以职责为目标建立边界：

```text
my-rpg/
  frontend/
    index.html
    app.js
    styles.css
    modules/
      api-client.js
      game-store.js
      turn-controller.js
      streaming-renderer.js
      save-ui.js
      monitor-ui.js

  backend/app/
    api/              # HTTP 路由和 DTO
    application/      # GameLoop、TurnService、AgentOrchestrator
    domain/            # 状态、规则、SceneContract、承诺
    memory/            # 检索、账本、抽取、摘要
    infrastructure/   # SQLAlchemy、LLM provider、文件系统
    schemas/           # 版本化 API 契约

  data/
    worlds/           # 版本化世界包
    research/         # 研究数据库构建产物
    migrations/       # 数据库迁移

  tests/
    unit/
    contract/
    replay/
    browser/
    fixtures/

  docs/
  tools/
```

迁移原则：先把接口和职责抽出来，再移动文件；禁止一次性重写前端和后端。

