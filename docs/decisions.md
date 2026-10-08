# 决策与现有约束

整理日期：2026-10-08。下面是从已有材料和代码归纳的约束，并非补写用户决策历史。未找到原始授权时，不标注为“用户决定”。

| ID | 当前约束或事实 | 记录性质与依据 | 适用范围 |
|---|---|---|---|
| D001 | 完整本地入口是 FastAPI 托管的 index.html | 实现事实：backend/app/main.py；README.md | 运行与入口修改；不代表在线部署已定 |
| D002 | 前端编排与后端服务共同完成回合 | 实现事实：index.html；backend/app/routers/turn.py、chat.py | 不将“有后端接口”写成“全部迁移完成” |
| D003 | 规划与正文分离，幕后因果不应直接交给正文写手 | 既有设计：README.md；story_planner.py、prompt_builder.py；progress.md 的 2026-08-21 记录 | 剧情规划与提示词修改 |
| D004 | 规划不应替玩家预定行动或反应 | 既有规则：story_planner.py 的硬规则 | 规划、裁定、叙事和回归 |
| D005 | 研究标签用于可组合叙事约束，不代表市场份额或文学质量 | 既有数据口径：research/DATABASE_GUIDE.md、RESEARCH_REPORT.md | 数据解释、标签与玩法 |
| D006 | research_db.json 由源记录、本体和 crosswalk 构建 | 构建事实：tools/build_research_db.mjs；DATABASE_GUIDE.md | 修改源数据后重建，不直接补生成物 |

上述路径未带链接的代码均位于仓库；模块位置见 [架构](architecture.md)。历史动机无法由当前实现单独证明。

## 待确认

- wuji_v25_reviewed.html 的维护定位，以及研究数据嵌入脚本是否应改为当前入口。
- 下一阶段功能优先级。章节总结/时间事实等仅见于历史候选，未据此确认为路线。

## 后续记录方式

有实质决定时追加：ID、决定日期、内容、状态（暂定/已确认/已替代）、决定主体、原始依据、影响范围，以及替代的 ID。没有决定就不新增条目。用户原话与技术建议区分保存；从实现归纳的事实不能升级为用户授权。
