# LLM 互动叙事系统综述：检索日志

**执行日期**：2026-08-21  
**协议**：`interactive_narrative_systematic_review_protocol.md` 1.0  
**用途**：为 `my-rpg` 的体验改进寻找可验证方法，不用于宣称穷尽全部学术文献。

## 检索边界

- 时间：2018-01-01 至 2026-08-21；早期互动叙事工作只作背景。
- 语言：英文/中文全文或足够完整的英文技术材料。
- 主要来源：ACL Anthology、ACM/IEEE 论文元数据、arXiv；Scholar 类搜索只用于定位，关键结论回到论文页或全文核验。
- 本轮是“查询捕获集”：搜索接口不稳定提供数据库总命中数，因此不把搜索结果页的近似数字写成 PRISMA 数据库总量。流程计数只描述保存并实际筛选的唯一记录。

## 查询组与实际使用的检索式

### S1 长篇规划、控制与修订

```text
("long-form story" OR "long story generation" OR narrative generation)
AND (LLM OR "large language model")
AND (planning OR outline OR coherence OR revision OR critic)
```

补充定向检索：`Re3 recursive reprompting revision`、`DOC detailed outline control`、`DOME dynamic hierarchical outline memory`、`CritiCS collective critics`、`CONCOCT story pacing`。

捕获重点：Re³、DOC、CONCOCT、DOME、CritiCS、Plan-Write-Revise、长篇叙事能力分析、长篇修订回归研究。

### S2 互动叙事、戏剧导演与玩家能动性

```text
("interactive narrative" OR "interactive drama" OR "interactive storytelling")
AND (LLM OR "large language model")
AND (agency OR director OR actor OR plot OR emergence OR storylet)
```

补充定向检索：`IBSEN director actor`、`From Role-Play to Drama-Interaction`、`immersion agency interactive drama`、`Player-Driven Emergence`、`Drama Llama storylets`、`StoryVerse`、`Open-Theatre`。

捕获重点：有真实玩家或作者研究的系统优先；只有系统演示的工具只作为实现参考。

### S3 角色扮演、人格演化与知识边界

```text
(role-play* OR persona OR character agent)
AND (LLM OR "large language model")
AND (consistency OR fidelity OR knowledge boundary OR temporal OR dynamic)
```

补充定向检索：`TimeChara`、`CharacterBox`、`Memory-Driven Role-Playing`、`Dynamic Persona Coherence`、`CharacterEval`、`InCharacter`。

捕获重点：区分静态角色卡忠实、时间点知识、持续心理状态和真实长程互动。

### S4 叙事记忆、检索与结构化状态

```text
(narrative OR role-playing OR conversation)
AND (long-term memory OR retrieval OR world state OR temporal graph OR neuro-symbolic)
AND (LLM OR agent)
```

补充定向检索：`LoCoMo`、`LoCoMo-Plus`、`RMM multi-granularity memory`、`Generative Agents`、`world-state transformations narrative`、`NCP-Bench`。

捕获重点：长期上下文与 RAG 的局限、时间/人物知识过滤、结构化事实与承诺。

### S5 生成质量、一致性与评估可靠性

```text
(story generation OR narrative OR role-playing)
AND (benchmark OR evaluation OR metric OR human evaluation OR consistency)
AND (LLM OR language model)
```

补充定向检索：`OpenMEVA`、`HANNA`、`ConStory-Bench`、`Mary cheeseburger vegetarian`、`PersonaEval`、`Illusions of the Gold Standard`。

捕获重点：自动指标/LLM 裁判能否替代人类、长篇错误分布、细微人设冲突的检测难度。

## 引文追踪

- 从 Re³ 向前追踪 DOC、CONCOCT、DOME、CritiCS。
- 从 IBSEN 与 Drama-Interaction 向前追踪 Enhanced Immersion and Agency、Open-Theatre。
- 从 Generative Agents 向前追踪角色轨迹与记忆系统。
- 从 LoCoMo 向前追踪 RMM、LoCoMo-Plus 与时间分层记忆。
- 从 OpenMEVA/HANNA 向前追踪长篇一致性和人工评价可靠性。

## 筛选计数（查询捕获集）

| 阶段 | 数量 | 说明 |
|---|---:|---|
| 保存的候选记录 | 48 | 五组查询与引文追踪中保存的标题 |
| 去重后唯一记录 | 42 | 合并正式论文页、预印本和重复版本 |
| 标题/摘要排除 | 6 | 与叙事过远、仅短文本/通用 Agent、无可检查结果 |
| 进入全文/扩展摘要核验 | 36 | 核验方法、对照、评价与适用边界 |
| 全文后排除 | 5 | 训练型角色问答、纯工具演示或无法支持本项目结论 |
| 最终纳入综合 | 31 | 其中若干只承担反证或评估边界，不等于 31 项实现建议 |

完整决定见 `interactive_narrative_screening.csv`。

## 协议偏差

1. 原协议希望记录每个数据库的完整命中数，但当前检索接口只稳定返回排序后的候选，无法可靠导出 ACL/ACM/IEEE 的全量命中数。本轮改为记录实际捕获并筛选的唯一文献，不虚构总量。
2. 2026 年 8 月出现了与项目高度直接但极新的预印本（例如 NCP-Bench）；保留为 [B]，不能覆盖成熟同行评审证据。
3. 部分 ACM/IEEE 论文使用作者公开的 arXiv 全文核验；同行评审状态按正式 venue 元数据记录。
4. 未执行统计合并：任务从离线 2,000 字故事到 100 回合模拟差异过大，效应量不可直接汇总。

## 复核规则

- 每项 [A] 结论至少复核摘要、方法/评价段与局限；数值只在能回到论文页或全文时记录。
- 只有自动评分或单一脚本/少量作者研究的结论降为 [B]/[C]。
- 论文声称“interactive”但实际只让人编辑大纲，不视为玩家逐回合互动证据。
- 多 Agent 论文必须同时记录调用数/流程长度；未报告成本不得解释为“免费提升”。
