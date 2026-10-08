# 当前架构与维护入口

核对日期：2026-10-08；基于仓库代码阅读，未运行。本文描述现有职责，不表示已完成全面后端迁移。

## 运行入口

backend/app/main.py 的 / 路由返回根目录 index.html，并挂载 /research。运行方法见 [根 README](../README.md) 和 [后端说明](../backend/README.md)。

wuji_v25_reviewed.html 是另一份保留页面；用途及是否持续维护尚待确认。tools/embed_research_db.mjs 当前只写入这份页面。

## 职责与查找位置

| 层 | 位置 | 当前职责 |
|---|---|---|
| 页面与流程编排 | index.html | 世界和角色 UI、模型调用流程、流式显示、规划触发、状态和存档交互 |
| HTTP 接口 | backend/app/routers/ | 配置、世界、对话、提示词、规划、状态、记忆与存档入口 |
| 业务实现 | backend/app/services/ | 提示词构建、模型代理、状态规则、记忆和规划解析 |
| 数据契约 | backend/app/schemas/ | 请求、结果与运行时结构校验 |
| 领域规则 | backend/app/domain/ | 世界、规则、标签、模型服务目录 |
| 持久化 | backend/app/db/ | 数据库模型与会话；与浏览器存储共同参与运行 |
| 类型研究 | research/、tools/ | 源记录、标签本体、映射、构建和校验 |

## 回合与规划

前端根据当前状态决定是否规划，调用 /api/story/plan/prompt 取得提示词，组织模型调用，再向 /api/story/plan/result 提交结果以解析校验。story_planner.py 限制剧情线和节点数量，并将场景刷新期限收紧至当前回合之后 2–6 回合。

/api/turn/prompt 接收上下文并返回编译后的 system prompt。/api/chat/stream 负责上游模型的流式代理。前端仍负责编排和显示，并通过状态、记忆和存档接口参与后续处理。接口存在不等于后端独占整局状态。

修改规划规则时同时查：
- backend/app/services/story_planner.py
- backend/app/services/prompt_builder.py
- backend/app/schemas/story.py
- index.html 中规划触发与 storyRuntime 保存/恢复逻辑
- backend/tests/test_story_agent.py、test_prompt_builder.py 及相关存档测试

## 研究数据链

原始作品 JSON + tag_ontology.json + crosswalk
→ tools/build_research_db.mjs
→ research/research_db.json
→ 页面读取或内嵌数据。

数据库字段、合并规则、证据等级与限制以 [DATABASE_GUIDE](../research/DATABASE_GUIDE.md) 为正本。tools/embed_research_db.mjs 会提取紧凑版本写入 wuji_v25_reviewed.html；index.html 也已有内嵌数据库，因此不能假定执行该脚本已更新当前入口。

## 维护原则

运行行为以代码和实际验证为依据；文档差异记录到 [STATUS](../STATUS.md)。结构性改动应明确影响的前端、接口、状态和生成物，不依赖单份 README 的概括。
