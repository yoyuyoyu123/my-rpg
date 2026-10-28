# ADR：`my-rpg` 的证据驱动叙事运行架构

**状态**：Phase 0 complete；Phase 1 implemented；Phase 2 core implemented  
**日期**：2026-08-21  
**依据**：`interactive_narrative_systematic_review.md`  
**目标**：先解决已观察到的遗忘、突发剧情、人物知识串线、无关描写与玩家选择无影响，同时保护现有成熟前端体验。

## 决策

采用“**结构化叙事状态 + 短视窗场景契约 + 单写手流式输出 + 风险触发式导演/修复**”架构。

不采用常开多 Agent 会议、每 NPC 一次模型调用、每回合全文批评重写，也不把完整类型数据库直接塞进每回合 prompt。

## 不可回退的体验验收

任何后端或 Agent 改造都必须同时保留：

1. 18 个既有世界包及自由世界生成；
2. 既有供应商/自定义 OpenAI 兼容 API 分类；
3. 主界面、开局和存档选择，不自动跳入上次存档；
4. 长文本配置和即时 SSE 显示；
5. Enter 发送、Shift+Enter 换行；
6. 2–4 个可点击行动选项和自由输入；
7. 前端设置、调试导出与后台监视器；
8. 后端不可用时的明确错误或安全兼容路径，不静默损坏存档。

## 运行职责

| 组件 | 是否每回合运行 | 职责 | 明确不负责 |
|---|---|---|---|
| State/Memory Compiler（程序） | 是 | 读取正史、事件、人物知识、承诺、关系状态；按时间/来源过滤 | 写小说、猜隐藏事实 |
| Risk Gate（程序） | 是 | 判断是否跨场景、破坏承诺、涉及高风险裁定或低置信记忆 | 生成自由评论 |
| Scene Planner（模型） | 仅开局/场景切换/契约失效 | 生成 2–4 回合的场景契约与软承诺 | 写正文、规定玩家选择、强制未来节点 |
| Rules/Adjudicator（程序优先） | 条件触发 | 数值、物品、时间、位置、知识传播、显式动作可行性 | 决定文风 |
| Narrative Writer（模型） | 是 | 只写当前回合正文和行动参考，保持 SSE | 修改权威状态、偷看幕后答案、扩写新主线 |
| Patch Validator（程序） | 有 patch 时 | 检查状态变化、来源、边界和幂等性 | 用审美改写正文 |
| Targeted Critic（模型） | 仅硬检查无法判定且风险高 | 对指定冲突证据作二元判断并限定修复范围 | 阅读/重写全文、自由提出新剧情 |
| Memory Extractor（后台） | 回合后异步 | 将已发生事件转成候选事实并去重 | 阻塞正文展示、直接覆盖正史 |

普通回合目标：**一次叙事模型调用**。场景切换回合通常两次（planner + writer）。只有风险闸门命中且程序无法确定时才允许第三次调用。

## 结构化状态

### 1. CanonFact：不可被摘要覆盖的正史

```json
{
  "id": "fact-uuid",
  "scope": "world|player|npc|location|item",
  "subject_id": "npc:chen-qi",
  "predicate": "alive",
  "value": true,
  "valid_from_turn": 4,
  "valid_to_turn": null,
  "source_turn": 4,
  "source_kind": "observed|told|player_set|system",
  "certainty": 1.0,
  "status": "active|superseded|disputed"
}
```

同一 subject/predicate 的新事实不能简单追加；必须关闭旧有效区间或标成 disputed。世界包事实和玩家明确设定优先级高于模型抽取。

### 2. EventRecord：带因果和参与者的事件

```json
{
  "id": "event-uuid",
  "turn": 18,
  "time_key": "day1-14:30",
  "location_id": "loc:market",
  "participants": ["player", "npc:merchant"],
  "action": "玩家拒绝护送委托",
  "cause_ids": ["commitment:escort-offer"],
  "result_fact_ids": ["fact:merchant-knows-refusal"],
  "visibility": "public|participants|private"
}
```

### 3. NpcBelief：人物各自的知识，不再共用一个 lore 文本

```json
{
  "npc_id": "npc:merchant",
  "fact_id": "fact:player-refused-escort",
  "mode": "observed|told|inferred|rumor",
  "confidence": 1.0,
  "learned_turn": 18,
  "source_id": "player",
  "status": "known|doubted|retracted"
}
```

只有 `observed/told` 且来源链成立的内容才能作为 NPC 的确定知识；`inferred/rumor` 在 prompt 中必须带不确定标记。

### 4. Commitment：承诺、拒绝和必须守住的局部条件

```json
{
  "id": "commitment:escort-offer",
  "kind": "player_choice|npc_promise|deadline|story_soft|world_hard",
  "owner_id": "player",
  "text": "玩家已拒绝同一护送委托",
  "status": "active|fulfilled|violated|abandoned|superseded",
  "created_turn": 18,
  "due": null,
  "hard": true,
  "satisfy_when": [],
  "forbid": ["换名字再次强塞同一护送入口"]
}
```

`world_hard/player_choice/npc_promise` 通常是硬约束；`story_soft` 允许 planner 暂停或放弃。不得把“玩家最终会爱上某人/接受任务/成为英雄”写成承诺。

### 5. CharacterDynamicState：稳定人格和动态反应分离

```json
{
  "npc_id": "npc:friend",
  "identity_anchors": ["重视平等", "不喜欢公开示弱"],
  "relationship": {"trust": 34, "closeness": 20, "tension": 5},
  "mid_term": ["连续两次被玩家放鸽子，失望正在累积"],
  "short_term": {"emotion": "恼火", "intensity": 0.55, "cause_event": "event-17"},
  "decay_after_turns": 3
}
```

短期情绪到期后衰减；只有持续事件才能改变中期状态，只有重大长期经历和明确文本证据才能修订 identity anchors。

### 6. SceneContract：替代“完整剧情线 beats”作为写手的主要输入

```json
{
  "id": "scene-uuid",
  "valid_from_turn": 18,
  "refresh_after_turn": 21,
  "situation": "玩家刚拒绝委托，仍在公开营业的市场",
  "causal_bridge": ["event-18"],
  "focus": "让商人对拒绝作出正常反应，并保留其他生活行动",
  "participant_intents": {"npc:merchant": "尽快找到替代人手"},
  "known_information": ["fact:offer-details"],
  "affordances": ["继续购物", "询问其他工作", "离开", "解释拒绝原因"],
  "pressure_budget": 1,
  "mystery_budget": 0,
  "forbidden": ["同一委托换皮重发", "神秘组织突然登场"],
  "stop_before": ["需要玩家答应新条件", "需要玩家离开当前位置"],
  "soft_commitments": []
}
```

`affordances` 是可能性，不是强制生成的四个选项；自由输入仍是第一等入口。

## 每回合链路

```text
玩家输入
  -> 程序解析显式实体/行动/否定/承诺信号
  -> 检索候选事实
  -> 按时间、人物可知性、来源、状态过滤
  -> Risk Gate
       -> 场景契约有效：直接写作
       -> 场景切换/硬承诺受影响：刷新 SceneContract
       -> 明确规则行动：程序裁定
  -> 组装最小上下文
  -> Narrative Writer SSE
  -> 解析 options / state patch
  -> 硬规则验证
       -> 通过：应用 patch
       -> 可定位冲突：拒绝 patch 或只修冲突句
       -> 含糊高风险：Targeted Critic
  -> 保存回合
  -> 异步事实抽取/摘要
```

## 与当前代码的映射

### 保留并收窄

- `backend/app/services/story_planner.py`
  - 保留 JSON 清洗、长度限制和开局/场景切换触发。
  - 将 `threads[].beats` 从写手主要约束降级为后台软线程；planner 主要输出 `SceneContract`、承诺变更和触发原因。
  - `private_cause` 不进入写手 prompt，这一现有设计继续保留。

- `backend/app/services/prompt_builder.py`
  - 保留 `AGENT_WRITER_RULES`、权威状态、精确 `OPTION_RULES` 和场景公开摘要。
  - 逐步把 `_relevant_lore()` 的纯关键词命中替换为后端已过滤的结构化 context；编译器不自行猜哪些 NPC 知道什么。
  - 类型标签只编译与当前 scene affordance 相关的少量说明，不恢复全库硬规则。

- `index.html`
  - 保留 SSE、打字速度、选项解析/补救、Enter、存档与监视器。
  - 监视器增加 risk reason、注入的事实 ID、过滤掉的知识、契约刷新原因和 patch 拒绝原因；不展示/伪造模型隐藏思维链。

### 扩展

- `backend/app/db/models.py`
  - 在不破坏现有 facts 表的迁移中增加 event、belief、commitment、character_dynamic_state、scene_contract；先新增表，不直接删除旧字段。

- `backend/app/services/memory.py`
  - 检索分两步：候选召回 -> 结构过滤；返回引用 ID 和过滤理由。

- `backend/app/services/game_state.py`
  - 统一应用硬状态 patch 和事实有效期；保证重试幂等。

### 新增但保持小模块

- `backend/app/services/narrative_risk.py`
  - 纯程序规则：场景期限、实体变化、否定/拒绝、硬承诺、位置切换、状态 patch 风险。

- `backend/app/services/context_compiler.py`
  - 把结构化状态编译成短、可追踪上下文，输出 `included_ids/excluded_ids/reasons`。

- `backend/app/services/commitment.py`
  - 创建、履行、违反、废弃与替代承诺；禁止隐式重开已拒绝入口。

不新增“creative critic agent”“continuity agent”“NPC agent farm”等常开服务。

## 分阶段实施与停止条件

### Phase 0：先建回归集，不改生成架构

产物：8 类固定多回合存档、回放输入、硬错误计数、首 token/总耗时/调用数记录。

停止条件：如果现有存档不能稳定重放，先修存档与测试，不进入新架构。

### Phase 1：事实、人物知识与承诺分层

只新增表、读写 API、过滤器和监视器信息；writer/prompt 外观尽量不变。

验收：知识串线、承诺遗忘、拒绝换皮重发在固定回放中显著减少；普通回合模型调用数不增加；SSE/选项/存档全通过。

### Phase 2：SceneContract 取代强 beats

planner 输出当前场景契约、软承诺和刷新原因；线程大纲不再强迫写手完成节点。

验收：同一开局的不同玩家输入产生可观察后续差异；5 回合日常测试不自动升级为阴谋；无关描述减少；首 token 延迟只在场景刷新回合增加。

### Phase 3：局部风险修复 A/B

只对程序无法判断的高风险冲突试验 targeted critic；与“直接拒绝 patch/保留正文”对照。

停止条件：如果硬错误没有至少减少 30%，或中位回合时间增加超过 25%，或引入范围外改写，则删除该 critic 路径。

### Phase 4：可选的高互动 Director-Actor 实验

只用于用户明确选择的戏剧/群像模式或关键对峙，不作为默认。先在固定场景比较一次写手与额外导演，不为每个 NPC 独立调用。

停止条件：真人盲评的玩家影响/人物可信没有稳定提升，或每回合成本超过基础两倍而收益不明显，则保持关闭。

## A/B 验收表

| 故障 | 固定场景 | 主要指标 | 防回归指标 |
|---|---|---|---|
| 忘记前文 | 20回合前的承诺到期 | 承诺硬错误数 | 输入token/延迟 |
| NPC全知 | 私聊秘密后与第三人对话 | 未授权知识次数 | 对话自然度 |
| 强塞剧情 | 玩家连续拒绝任务 | 同钩子重发次数 | 世界仍有可玩行动 |
| 选择无影响 | 同存档分叉两条输入 | 后续状态/关系差异 | 两条都保持世界事实 |
| 悬疑剧味 | 低压经营/日常5回合 | 无铺垫危机和谜语人次数 | 有趣性/进展感 |
| 无关描写 | 明确购买/问路行动 | 无因果句比例 | 文本不过短 |
| 人设僵硬/漂移 | 连续刺激后恢复 | 身份锚点错误+情绪演化评分 | 不重复固定口癖 |
| UX回归 | 任意流式长回复 | SSE首token/选项/Enter/存档 | 全部零回归 |

## 被否决的替代方案

### A. 每回合多个 Agent 自由讨论

否决原因：高延迟、高 token、批评可能破坏连贯，直接互动证据小且多用预定义戏剧。后台监视器能看流程，不等于需要扩大流程。

### B. 把所有网文/日轻/漫画标签加入 system prompt

否决原因：注意力稀释、标签互相污染、易触发套路堆砌。数据库应生成开局候选和场景 affordance，不是每回合规则墙。

### C. 全上下文或向量 RAG 解决记忆

否决原因：长上下文仍有时间/因果缺陷；语义相似会召回角色不该知道的内容。结构过滤先于向量优化。

### D. 生成后让模型全文检查并重写

否决原因：细微人设冲突检测不可靠，修订会引发范围外回归，也破坏已经流式展示的体验。

## 下一步

Phase 0 回归基线已经冻结。Phase 1 已新增事件、承诺、NPC belief、人物分层状态的独立表、读写 API、时间/来源/可见性过滤和检索 trace；旧 facts 表与旧存档保持兼容。Phase 2 已把 SceneContract 的因果事件、affordances、强度预算、禁止项和承诺引用接入 planner 与 writer，旧 `allowed_developments` 会自动升级。

下一步不继续堆提示词或常开 Agent。先用固定多回合场景做真实 A/B：拒绝钩子、私聊秘密、低压日常、人物情绪恢复与分叉选择；确认硬错误下降且 SSE/选项/Enter/存档零回归后，才决定是否进入 Phase 3 的局部风险修复实验。
