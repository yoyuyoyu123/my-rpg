# AI 当 DM：研究与跑团经验地图

日期：2026-10-28  
问题：① 有没有"AI 作为 DM 的类 DnD 游戏"的专业研究？② 2.0 需不需要新方法？  
配套：[RETRO_1X.md](./RETRO_1X.md)（1.x 哪些目标在现有方法上做不到）。1.x 已有的综述 `research/interactive_narrative_systematic_review.md` 覆盖了长篇规划、记忆、角色扮演一致性，**没有覆盖 AI DM / 跑团**，本文补这一块。

**核实说明**：下列 arXiv 条目（标 ✔）已于 10-28 用 arXiv 元数据逐条核对标题与日期；会议论文多为检索代理打开过页面或只读到元数据（标 ◐）；跑团经验以作者原站或官方 SRD 为准（标 ✔），二手来源标 ◐，未核实标 ✗。数字只引用读到的摘要级结果。检索以英文为主，中日文研究可能遗漏。

---

## 结论先行

1. **有专门的研究方向，而且 2025–2026 很活跃。** "LLM 当 GM"已有数据集、基准、系统和用户研究，集中在 Wordplay 研讨会、AIIDE、ACL 系会议。
2. **研究的结论和 1.x 的教训高度一致：** 规则、资源、事实交给程序；LLM 当裁判会被玩家话术说服；多 Agent 互评不能代替程序规则。
3. **没有找到把整条链做全的工作**——规划意图 → 程序裁定的结构化事件 → 写手渲染 → 程序账本，且"LLM 只能提议事件、不能直接改世界"这条硬边界没人测过。这正是 2.0 的位置，也是作品集的亮点（注意：检索有英文偏向，不宣称"首个"）。
4. **人类 GM 已经有成熟的"算法"**，而且大多能直接编码成数据结构，而不是提示词规则：开局约定（Session Zero）、进度钟、三线索规则、GM 行动清单、局势与效果、威胁阵线。
5. **所以 2.0 的主体不需要发明新算法**，需要的是把现成的拼起来并守住边界。真正可能需要新方法的只有四处（见 §4）。

## 1. 学术研究地图

### 1.1 AI GM 与跑团数据

| 工作 | 要点 | 对我们 |
|---|---|---|
| Callison-Burch et al., *Dungeons and Dragons as a Dialog Challenge for AI*, EMNLP 2022 ✔ [arXiv 2210.07109](https://arxiv.org/abs/2210.07109) | 把 DnD 定义为"生成下一轮"与"从对话预测游戏状态"两个任务；约 900 局、80 万轮 | 状态追踪与生成并列是领域共识 |
| Zhu et al., *FIREBALL*, ACL 2023 ◐ [ACL](https://aclanthology.org/2023.acl-long.229) | 约 2.5 万场 Discord 实际游戏 + 机器人维护的结构化状态；LLM 可输出可执行的游戏指令 | "LLM 提议结构化事件、程序执行"的先例 |
| Zhou et al., *I Cast Detect Thoughts*, ACL 2023 ✔ [arXiv 2212.10060](https://arxiv.org/abs/2212.10060) | DM 模型先定意图、再生成引导话语，并预测玩家反应 | 意图与表层文字分离；引导而不强推 |
| Zhu et al., *CALYPSO*, AIIDE 2023 ◐ [AAAI](https://ojs.aaai.org/index.php/AIIDE/article/view/27534) | LLM 当 DM 助手，人类 DM 保留创作控制 | 全自动 GM 的证据较弱 |
| Song et al., *Enhancing AI Game Masters with Function Calling*, Wordplay@ACL 2024 ✔ [arXiv 2409.06949](https://arxiv.org/abs/2409.06949) | 用函数调用做骰子和状态修改，叙事质量与状态一致性提升 | **最接近"程序账本 + 骰子工具"的已发表先例**；区别是 LLM 仍自己决定何时调用工具 |
| Minari et al., *TRPG Game Mastering Using LLM-Based Multi-Agent System*, Wordplay ◐ [PDF](https://wordplay-workshop.github.io/pdfs/20.pdf) | 单个 GPT-4o 当 GM：误解规则、偏离故事、剧透；加多 Agent 反馈后推进变好，但**规则违反和剧透反而增加**、响应变慢 | 印证 1.x 综述 §5：LLM 互评不能代替程序规则 |
| Jorgensen et al., *Static vs. Agentic Game Master AI*, 2025 预印本 ✔ [arXiv 2502.19519](https://arxiv.org/abs/2502.19519) | 多 Agent + ReAct 的 GM 在维持游戏进行、沉浸、好奇心上优于单提示词 GM | 单人跑团的节奏与卡关 |
| Berlaimont et al., *CriticaLLM*, 2026 预印本 ✔ [arXiv 2610.21525](https://arxiv.org/abs/2610.21525) | 全自动 GM（剧情、探索、战斗），比较 4 个模型的剧情与反派多样性，有真人试玩 | 少数测量"剧情雷同"的 GM 工作 |
| Ismayilov et al., *DungeonBench*, 2026 预印本 ✔ [arXiv 2607.29577](https://arxiv.org/abs/2607.29577) | 前沿模型能赢单场战斗，但在资源规划、休息时机和规则战术上吃力 | 资源与规则别交给 LLM |
| Li et al., *Setting the DC*, NeurIPS 2025 workshop ◐ [页面](https://neurips.cc/virtual/2025/128312) | Agent 只能通过函数调用行动；作者指出叙事好看与战术正确会分歧 | 文风与正确性的取舍 |

### 1.2 剧情层与文字层分离（戏剧管理）

| 工作 | 要点 | 对我们 |
|---|---|---|
| Mateas & Stern, *Façade*, AIIDE 2005 ◐ [AAAI](https://ojs.aaai.org/index.php/AIIDE/article/view/18722) | 戏剧管理器按节拍排序剧情，角色行为单独实现 | 经典的"规划 / 表演"分离 |
| Riedl & Bulitko, *Interactive Narrative: An Intelligent Systems Approach*, AI Magazine 34(1) ◐ [AAAI](https://ojs.aaai.org/aimagazine/index.php/aimagazine/article/view/2449) | 领域约 20 年的综述，含戏剧管理与玩家建模分类 | 术语与分类的入口 |
| Aylett, *Emergent Narrative, Social Immersion and "Storification"*, 1999/2000 ◐ [页面](https://www.macs.hw.ac.uk/~ruth/Papers/narrative/NILE00.html) | 提出"叙事悖论"：玩家自由行动与叙事结构的张力 | 1.x E 类问题的学名 |
| Louchart & Aylett, *Solving the Narrative Paradox in VEs – Lessons from RPGs*, IVA 2003 ◐ | 明确向跑团 GM 学习如何化解叙事悖论 | **"AI 当 DM"的思路学界 20 多年前就提出了** |
| Sun et al., *Drama Llama*, 2025 预印本 ✔ [arXiv 2501.09099](https://arxiv.org/abs/2501.09099) | 作者用自然语言写剧情触发条件，LLM 判断何时触发 | 故事意图写成"条件 → 动作"数据 |
| Wang et al., *Dramamancer*, Wordplay@EMNLP 2025 ✔ [arXiv 2601.18785](https://arxiv.org/abs/2601.18785) | 条件满足时把作者写的指令插入上下文 | 同上；按局、按情境下达指令，而不是常驻规则 |
| Wang et al., *StoryVerse*, FDG 2024 ✔ [arXiv 2405.13042](https://arxiv.org/abs/2405.13042) | 作者写"抽象幕"，LLM 规划器按世界状态展开成具体角色行动 | 规划 → 事件 |
| Bang et al., *SNAP*, 预印本 ✔ [arXiv 2601.11529](https://arxiv.org/abs/2601.11529) | 故事切成带明确计划的"格"，上下文限定在格内 | 防漂移、防剧透 |
| Ma et al., *NCP-Bench*, 2026 预印本 ✔ [arXiv 2608.08160](https://arxiv.org/abs/2608.08160) | 最好的模型 20 回合后"存活率"仅 42%，事实冲突率 40–68%；"语言质量高不保证守住承诺" | **程序账本的最强证据**（1.x 综述已引用） |

### 1.3 玩家建模与节奏

| 工作 | 要点 | 对我们 |
|---|---|---|
| Thue et al., *PaSSAGE*, AIIDE 2007 ◐ [AAAI](https://ojs.aaai.org/index.php/AIIDE/article/view/18780) | 学习玩家风格并据此挑选剧情内容 | LLM 之前唯一扎实的"按玩家调节"先例 |
| Rahmati & Zhao, *Epistemic Pacing in LLM-Driven Detective Games*, 2026 预印本 ✔ [arXiv 2609.23043](https://arxiv.org/abs/2609.23043) | 检索-生成-校验三段，NPC 只透露叙事状态允许的信息；摘要称严重幻觉减少 64.78% | NPC 知情范围与信息揭示节奏 |

### 1.4 谄媚、同质化

| 工作 | 要点 | 对我们 |
|---|---|---|
| Chen et al., *Rule Adherence of LLM Adjudicators in Call of Cthulhu*, 2026 预印本 ✔ [arXiv 2607.02802](https://arxiv.org/abs/2607.02802) | 5,376 个对抗样本、22 个裁判模型：玩家用叙事包装的话术能绕过规则，更新的模型和显式推理都不能稳定防住 | **"世界没有阻力"的直接证据：裁定不能交给 LLM** |
| Shah et al., *Too Nice to Tell the Truth*, 2026 预印本 ✔ [arXiv 2604.10733](https://arxiv.org/abs/2604.10733) | 13 个开源小模型中 9 个：角色人设越随和越谄媚 | GM/NPC 不要用"友善助手"人设 |
| Li et al., *Narrative Flattening*, 2026 预印本 ✔ [arXiv 2605.27878](https://arxiv.org/abs/2605.27878) | 后训练（SFT/DPO/RL）压缩了小说的主题、情感与文体变化 | 雷同部分来自模型本身，不是提示词能完全解决的 |

### 1.5 研究空白（检索代理的结论，我认同）

- 没有工作把"意图规划 + 程序裁定事件 + 写手 + 程序账本"做全，也没人测过"LLM 只能提议"的硬边界。
- 谄媚被量化了，但**没有在游戏里修好它的研究**。
- **"LLM 替玩家做决定"没有对照研究**。
- **按每局意图调节节奏**没有 LLM 时代的研究。
- 叙事悖论没有评价标准：测一致性的有，测"玩家感到的自由"的没有。
- **没有中文、没有小说级文笔的 LLM GM 评估。**

## 2. 跑团 GM 的经验：现成的"算法"

| 做法 | 来源 | 解决 1.x 的什么 | 编码成什么（不是提示词规则） |
|---|---|---|---|
| **开局约定**（Session Zero）+ Lines & Veils / X 卡 | X 卡：John Stavropoulos 2013 ✔；Lines & Veils 常归于 Ron Edwards《Sex & Sorcery》◐（年份 2003/2004 未定） | 开局选了穿越却不发生；替玩家决定 | 开局配置：`premise_commitments`（带触发条件与期限）、`lines`、`veils`、节奏偏好；游戏中可随时"X"暂停重写 |
| **别准备剧情，准备局势** | Justin Alexander, The Alexandrian 2009 ✔ [链接](https://thealexandrian.net/wordpress/4147/roleplaying-games/dont-prep-plots) | 谄媚；主线丢失 | 每个势力一条记录：目标、资源、时间线；引擎每回合推进 |
| **三线索规则** | Alexander 2008 ✔ [链接](https://thealexandrian.net/wordpress/1118/roleplaying-games/three-clue-rule) | 铺垫不足、剧情空降 | `Revelation{clues≥3, delivered[]}`；不足 3 条线索的剧本数据直接拒收；N 回合未揭示则安排"主动线索"事件 |
| **节点式剧本** | Alexander ✔（只读了第 1 篇） | 主线丢失；铺垫 | 剧情图：节点 = 场景，边 = 线索；可达性检查 |
| **失败也推进**（fail forward） | Alexander ✔ [链接](https://thealexandrian.net/wordpress/46186/roleplaying-games/failure-for-the-beginning-gm) | 卡关；谄媚 | 检定失败必须返回"复杂化"或推进一格进度钟，不能返回纯成功 |
| **进度钟** | Blades in the Dark SRD ✔ [链接](https://bladesinthedark.com/progress-clocks) | 节奏；世界阻力；主线 | `Clock{name, size, filled, on_full}`；势力钟按回合推进，状态写进上下文 |
| **局势与效果**（Position & Effect） | Blades in the Dark SRD ✔ [链接](https://bladesinthedark.com/action-roll) | 谄媚（每次都"是"） | 每个行动先由程序定 `{position, effect}`，后果严重度受其约束 |
| **GM 行动清单**（moves），软/硬之分 | Dungeon World SRD ✔ [链接](https://www.dungeonworldsrd.com/gamemastering/)（源自 Apocalypse World，原书未读 ✗） | 替玩家决定；谄媚；节奏 | `GMMove` 事件类型：封闭清单、`soft/hard`、被忽视则升级；名称对玩家隐藏；每次以"你怎么做？"结束 |
| **威胁阵线与凶兆**（Fronts / Grim Portents） | Dungeon World SRD ✔ [链接](https://www.dungeonworldsrd.com/gamemastering/fronts/) | 主线丢失；节奏 | 战役级威胁 + 有序凶兆；凶兆久未推进则报警；开局前提可作第一个凶兆 |
| **懒人 DM 准备法**：强力开场、秘密与线索池 | Mike Shea《Return of the Lazy Dungeon Master》◐（模板页 ✔） | 铺垫；开局 | 每局约 10 条不绑定场景的秘密池，合适时投放；第一事件必须是强力开场 |

注意两处纠正：DnD 城主指南里**没有找到可引用的节奏章节**；"`players say what their characters do`"这句未找到出处，Dungeon World SRD 的说法是"对角色说话，不对玩家说话""从虚构开始、以虚构结束"。

## 3. 对 2.0 的直接回答

### 3.1 "开局选择算不算授权"——跑团的答案是"算"

Session Zero 的本意就是开局前把前提、基调、界限谈定，之后 GM 据此主动推进。玩家选了"穿越"，就是同意了"穿越会发生"；GM 只是不替玩家决定穿越**之后**怎么做。这一条仍需你拍板，但跑团实践和 1.x 的教训（d599044：规划器把玩家选定的前提当成了不该强推的钩子）指向同一个答案。

### 3.2 AI DM 版的回合链（草图）

```text
开局约定（Session Zero）
  → 前提承诺、界限、基调、节奏偏好、中篇的隐藏候选结局
  → 威胁阵线 / 势力局势 / 进度钟 / 秘密池 / 揭示与线索（= 故事意图，全是数据）

每回合
  玩家宣告行动
  → 程序：理解意图，定局势与效果，掷骰
  → GM（LLM）：从封闭行动清单中提议 GM 行动（软/硬），推进钟与凶兆
  → 程序：校验提议（不得含玩家角色的行动/感受；不得违反账本；失败必须带复杂化）
  → 写手（LLM）：把已确定的事件写成小说级正文，以"你怎么做？"收尾
  → 程序：记账
```

"有没有冲突"不再是全局规则，而是钟和凶兆的状态：日常故事的钟走得慢，玩家无视软行动时才升级为硬行动。

### 3.3 和 1.x 的对应

| 1.x 的问题（RETRO 分类） | 2.0 的承接 |
|---|---|
| C 谄媚 | 局势与效果 + 程序骰 + 失败必带复杂化；裁定不交给 LLM（CoC 研究） |
| C 替玩家决定 | 事件数据里根本没有"玩家角色行动/感受"的字段 |
| C 雷同 | 秘密池、势力、起名从程序侧抽样（已验证有效） |
| D 节奏 | 进度钟 + 凶兆 + 开局节奏偏好，偏差可测 |
| E 计划 vs 自由 | 开局约定的前提承诺 + 软/硬行动升级 |
| 主线丢失 | 战役级威胁阵线 + 凶兆停滞报警 + 程序账本 |

## 4. 需不需要新方法？

主体不需要：上面每一块都有出处。**真正可能需要自己想办法的只有四处**，也正是研究空白：

1. **小说级文笔与 GM 结构的结合。** 跑团经验只管"发生什么"，不管"写得好不好"；后训练本身会压平文风（Narrative Flattening）。写手怎样在"照事件写"的前提下仍有小说感、不变成念清单，是 2.0 最大的未知数，需要 A/B。
2. **按每局意图调节节奏、并从玩家反馈中学习。** 只有 2007 年的 PaSSAGE 一个前 LLM 先例。每章打分 + 进度钟参数，是一个可做的小实验。
3. **"LLM 只能提议"的硬边界效果如何。** 没人测过；它可能让世界更可靠，也可能让叙事变僵。
4. **评价：** 一致性有基准，"玩家感到的自由"和"中文小说质量"没有。2.0 需要自己定义一小套。

这四处既是风险，也是 2.0 作为作品集最有说服力的部分：前人做了零件，我们做整机并给出评价。
