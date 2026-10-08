# 当前状态

最后核对：2026-10-08。代码基线：[fe457ce05b7f](https://github.com/yoyuyoyu123/my-rpg/tree/fe457ce05b7f3791b0cca73e8372548cb6aad91a)。
本页记录仓库可确认的现状；本次未运行应用、模型 API 或测试。

## 当前定位

本地 AI 互动小说与文字 RPG 引擎。当前主入口是 FastAPI 提供的 index.html；GitHub Pages 仅提供静态页面，不能提供完整后端能力。未从仓库确认下一阶段的用户优先级。

## 能力与证据

| 能力 | 仓库证据 | 验证状态 |
|---|---|---|
| 前端与 API 同源托管 | backend/app/main.py | 已读代码，未启动验证 |
| 对话与 SSE 代理 | backend/app/routers/chat.py；backend/tests/test_stream.py | 代码与测试存在；本轮未运行 |
| 回合提示词编译 | backend/app/routers/turn.py；backend/app/services/prompt_builder.py | 已读接口；前端仍负责流程编排 |
| 剧情规划与结果校验 | backend/app/services/story_planner.py；backend/tests/test_story_agent.py | 代码存在；真实叙事效果未验证 |
| 状态结算、事实记忆与存档 | backend/app/services/game_state.py、memory.py；相关 routers 与 tests | 前后端共同参与；未验证恢复一致性 |
| 类型研究数据库 | research/DATABASE_GUIDE.md；tools/build_research_db.mjs | 已有数据口径与构建链；本轮未重建 |
| 历史验证记录 | progress.md | 记录曾报告 161 项通过；不是本轮测试结果 |

## 当前缺口

1. **入口与生成链同步待核对。** 服务入口是 index.html，tools/embed_research_db.mjs 的目标是 wuji_v25_reviewed.html；两份 HTML 都有代码。应先确定后者定位，再决定调整生成脚本或维护流程。
2. **真实体验回归未补齐。** 历史记录仍有浏览器检查缺口；规划时机、流式显示、撤销和读档需在同一局实际验证。
3. **当前机器的运行状态未知。** 历史进程、端口、虚拟环境与密钥检查不代表现在可用；使用前重新检查。
4. **长期开发优先级待用户确认。** 历史提到章节总结等候选，尚不能当作已批准路线。

## 下一步建议

以下是基于仓库检查的建议，未替用户确定功能路线。

1. 明确两份 HTML 的维护定位，并验证研究数据更新是否能进入实际入口。
2. 在开发环境重跑后端测试，记录实际命令、环境、结果与失败。
3. 做一次完整浏览器回归：新开局 → 普通回合 → 转场 → 存档 → 读档 → 撤销；核对规划调用和事实/状态恢复。
4. 按实际体验结果选择下一项功能或修复。

## 本轮完成

2026-10-08：建立通用协作规则、当前状态入口、架构与溯源说明；从代码和既有材料归纳约束；保留历史记录并标明其效力。纯文档整理，未调整运行代码。

历史见 [progress.md](progress.md)，设计依据见 [docs/decisions.md](docs/decisions.md)。
