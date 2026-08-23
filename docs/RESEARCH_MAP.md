# 学术对照地图

整理日期：2026-08-23

## 这份文档是什么

我们在 2026-08-20 到 08-23 这几天里，为了修「玩家选了穿越却永远不穿越」，
连改了六轮。每一轮都以为找到了根因，下一局又冒出新的变种。最后收敛到的
结论是：**「必须发生的事」不能交给模型判断，程序负责保证、模型负责表达。**

之后去检索文献，发现我们撞上的几乎每一个问题，学术界都有专门的名字，
有些还有成熟的解法。这份文档把**我们的工程发现**和**已有研究**对起来，
目的有三个：

1. 停止重新发明轮子——`migration_contract.py` 基本上是一个 drama manager；
2. 遇到下一个问题时知道该去哪个领域找答案，而不是继续试提示词；
3. 给还没做的功能（详略、命名、长程一致性）一个现成的理论骨架。

**这不是一份论文清单。**按「我们的问题」组织，不按学科组织；每条都写清楚
「可以直接抄什么」和「我们现在差在哪」。

## 证据分级

文献这东西，摘要和原文经常不是一回事。下面每条都标了我实际读到哪一层，
**级别只标不删**——低级别的线索仍然有价值，只是不能当结论用。

| 级别 | 含义 |
|---|---|
| **A** | 读过原文（或完整 HTML），文中数字与措辞可直接引用 |
| **B** | 只读到检索摘要／二手转述，方向可信，细节需回原文核对 |
| **C** | 只有标题和出处，未验证内容，仅作为检索线索 |

已知局限：本轮检索用的是英文关键词、以 arXiv 和 ACM/Springer 为主，
中文学界和游戏工业界的实践（尤其是国内文字游戏、AI Dungeon 之后的
一批产品）完全没有覆盖。

---

## 一、我们造的 migration_contract = Drama Manager

**我们的问题**：玩家开局点了穿越，但穿不穿越取决于规划器愿不愿意推进阶段。
实测四次规划里只有一次前进，而那一次是模型「违抗」了另一条指令。最后的
解法是程序拿回执行权：软提示（还剩几回合）+ 硬接管（预算用尽时程序自己
下发一张必须被写出来的场景卡）。

**学术名**：Drama Management / Experience Management。

标准定义（**B**）：

> a drama manager **monitors** an interactive experience and **intervenes**
> to shape the global experience so that it satisfies the **author's
> expressive goals** without decreasing a player's **interactive agency**

四个要素——监控、干预、作者意图、不削弱自主权——和我们那个模块的注释
几乎逐条对应。连我们在 commit 里写的「玩家选择的是**如何应对**穿越，
不是穿越**是否**发生」，也正是这个领域拆解 agency 的标准方式。

Experience Management (EM) 是更广的概念，drama management 是它的特例
（**B**）。这条线从 2006 年前后就有系统性工作，2008 年有综述。

### 可以直接抄的：DM 动作分类法（**B**）

搜索式 drama management 把「干预」拆成了一套动作类型，在 Anchorhead
这个交互小说上做过实验：

| 动作 | 作用 | 我们的对应 |
|---|---|---|
| **Causer** | 直接让某个 plot point 发生 | 就是我们的 `forced_scene`（唯一实现了的） |
| **Denier** | 阻止某个 plot point 发生 | 无 |
| **Temporer** | 临时阻止（必须配对 Re-enabler） | 无 |
| **Re-enabler** | 解除临时阻止 | 无 |
| **Hint** | 提示玩家往某个方向走 | 无（`budget_note` 是提示**模型**，不是提示玩家） |

**我们的差距很明显：五种动作我们只有一种，而且是最粗暴的那一种。**
「接管整幕」是 causer 里最重的形态。真正想要的效果——让穿越自然地早点
发生——用 hint（在正文里给玩家一个更明显的入口）配合 temporer（暂时
挡住无关的日常支线）会平滑得多，不需要程序夺走一整幕的作者权。

文献特别强调 **temporer 必须和 re-enabler 配对**，否则会永久卡死某条线。
这一条对我们有直接警示：如果以后加「暂时压制日常线」的机制，必须同时
实现解除条件。

### 两种主流实现路线（**B**）

- **SBDM（Search-Based）**：把剧情空间当搜索问题，用作者评价函数打分，
  前向采样找最优干预。
- **DODM（Declarative Optimization-Based）**：由 plot point 抽象、DM 动作、
  玩家转移模型、作者评价函数组成；后续工作把搜索换成解 MDP 得到策略，
  也有用强化学习和 TTD-MDP（targeted trajectory distribution MDP）的变体。

**对我们的启发**：这两条路线都要求把「作者想要什么」写成一个**可计算的
评价函数**。我们现在没有这个东西——`budget_total` 那张按篇幅取值的表
（short 3 / medium 5 / long 8）就是一个极简版的作者评价函数，而且是我拍
脑袋定的。要往前走，第一步是把「一局好的穿越故事长什么样」显式写下来。

---

## 二、场景卡 = Storylet

**我们的东西**：`SceneCard`——有 id、前置（`causal_bridge`）、内容
（`situation` / `purpose` / `affordances`）、禁止项、停止点、刷新视野。

**学术名**：storylet。这是可授权交互叙事的标准结构单元（**B**）。

Kreminski & Wardrip-Fruin 的综述把 storylet 系统按四个维度分类（**B**）：

1. 前置条件怎么定义；
2. **单个 storylet 能不能重复**；
3. storylet 内部装什么内容；
4. 内容选择架构（怎么挑出下一个可用的 storylet）。

**第 2 条正中我们的痛点。**我们花了一整轮修「同一个 purpose 连写四幕」
（回合 3 和回合 5 的 purpose 一字不差），最后加了字符二元组 Jaccard 检测。
而「storylet 可不可重复」在这套分类法里是**设计时就要回答的一维**，不是
事后打补丁的地方。我们现在的答案是「事后检测重复并施压」，属于最弱的一档。

相关概念还有 **Quality-Based Narrative (QBN)** 和 **Salience-Based
Narrative (SBN)**（**B**）——后者正是用 drama manager 来挑 storylet 的那类
系统，也就是我们的架构。

### LLM 时代的同类系统（**B/C**）

- **Drama Llama**（arXiv 2501.09099，作者含 Kreminski 本人）——LLM + storylets
  框架。关键设计：**作者用自然语言写触发条件，由 LLM 判断何时触发**，
  而不是写逻辑前置条件或 DSL（**B**）。我们的 `causal_bridge` +
  `activation_condition` 正是这个路子，等于独立走到了同一处；
  它做过 6 位作者参与的授权实验，值得看它踩过什么坑
- **Dramamancer**——作者用自然语言写设定和 storylet 前置条件，玩家用自然
  语言输入行动（**B**）
- **Orchid**——作者掌握主线，次要支线交给 LLM，玩家在作者定义的结构内
  创作（**B**）。这正是我们 planner/writer 分工的思路
- **StoryVerse**、**HAMLET**、**LLMR**——多智能体分工（planner / scene
  analyzer / inspector / director / actors）（**C**）

**HAMLET 那套分工和我们的 11 个 Agent 高度重合**，值得逐个对照看看它们
怎么切职责边界的——我们的 director/state/agency/utility 四个校验型 Agent
是自己长出来的，没参考过任何设计。

---

## 三、「程序保证 + 模型表达」= 神经符号

**这条最值得读，因为我们摸索了四轮才得出的结论，是这个领域的公认前提。**

核心主张（**B**）：

> LLMs positioned as **guided components within a neurosymbolic scaffold**
> rather than free-running narrators

### 代表工作：ASP 引导的故事生成（**A**，读过全文）

用 Answer Set Programming 定义「合法故事大纲」的生成器，LLM 只负责把
大纲展开成正文。具体做法：

- 定义一组**叙事功能**（`introduce_character`、`add_conflict` 等）；
- ASP 枚举出所有合法的七幕组合——实际生成了 **401,990 条**不同大纲；
- 约束排除不连贯的序列，例如「连续两幕是同一个叙事功能」「在介绍两个
  人物之前就加冲突」；
- LLM 把每个叙事功能翻译成写作指令并渲染成段落。

作者有一句话对我们特别重要：

> 因为大纲最终由 LLM 展开成完整故事，**ASP 约束并不需要防住每一个问题**

——符号层管结构，表达层的小毛病交给 LLM 兜。这正好解释了我们那条
`_has_declared_conflict` 为什么可以是两道很浅的闸：它不需要判断冲突是否
「真的成立」，只需要保证规划器**做了声明**，剩下的交给写手。

**结果**：跨六个前提测试，ASP 引导的生成一致地更多样（语义相似度算出的
同质化分数更低）。

**局限（作者自陈）**：没做人类评估；而且这个方法「以增加随机性的方式
降低了用户控制」，可能造成创作工具里的 "dearth of the author" 问题。

> 后一条对我们是个提醒：程序保证加得越多，作者（玩家）能感知到的
> 掌控感可能越少。我们的 `forced_scene` 已经在这条线上了——它夺走了
> 一整幕的规划权。文献建议的方向是把随机性/约束**开放给用户配置**，
> 而不是藏在系统里。我们的「迁移预算」如果做成开局可调的选项，就同时
> 解决了这个问题和「预算数字是我拍脑袋定的」那个问题。

### 其他路线（**C**）

- **LLM as narrative planning heuristics / search guides**——不让 LLM 直接
  写故事，而是用它给符号规划器的搜索提供启发式。这是另一种分工方式：
  符号层做决策，LLM 只提供直觉。
- **METATRON**——认知 + 符号 + 神经三者结合的框架综述。
- 用**时序逻辑合成自动机**来强制全局约束，保证长程生成中所有叙事要求
  始终成立。这比我们现在的「事后校验 + 警告」强一个量级。

### 领域公认的权衡（**B**）

| | 优势 | 代价 |
|---|---|---|
| 符号规划器 | 因果可靠、逻辑可保证 | 依赖手写 action schema，情节长度和多样性受限 |
| 纯 LLM | 能接受灵活的自然语言规格 | 黑箱，可控性差 |

**我们现在正好在中间**：程序管不变量（阶段推进、幕长、详略举证、
迁移预算），模型管表达（场景内容、正文）。这个位置是有文献支持的，
不是权宜之计。

---

## 四、详写/略写 = Genette 的「时距」

**我们的东西**：`narration: scene | summary` + `summary_target` + `conflict`。
从「小说的写作思路」推出来的。

**学术名**：热奈特（Gérard Genette）《叙事话语》(1972) 的**叙事时距**
(duration)，也叫 narrative speed——故事时长与叙述篇幅之比（**B**）。

《叙事话语》的四个维度（**B**）：

| 维度 | 含义 | 我们的对应 |
|---|---|---|
| **order** 顺序 | 故事时间 vs 叙述时间的次序（倒叙、预叙） | 无 |
| **duration** 时距 | 故事时长 vs 叙述篇幅 | **就是我们的详写/略写** |
| **frequency** 频率 | 同一事件被叙述几次 | **就是我们最早那个 bug** |
| **mood** 语式 | 距离与视角 | 部分对应「不替玩家想」那几条 |

**frequency 这一维值得特别记一笔。**我们最早的症状是「传送过程写了 11 个
回合约 4500 字，每回合换个感官细节重复同一件事」——这在热奈特的框架里
不是 duration 问题，是 **frequency 问题**（同一事件被重复叙述）。我当时
把它当成详略问题来修，方向偏了，所以才有后面那几轮。

计算叙事学有工作把每一维形式化成「把故事结构转成话语结构」的算子（**C**）。
LLM 时代的对应工作包括 outline-guided generation、suspense-aware iterative
planning、**pacing-aware planning**（**B**）。

**我们的差距**：我们只实现了 duration 的二值版本（详写/略写），而且
frequency 只有一个事后的字符重合度检测。order 和 mood 完全没碰。

**下一步该做什么**：把 `narration` 从二值扩成热奈特的五档
（省略 / 概述 / 场景 / 延缓 / 停顿），并把 frequency 提升成场景卡的显式
字段（「本幕是否在重述已经叙述过的事件」），而不是靠事后检测。

---

## 五、青石镇 = Mode Collapse + Typicality Bias

**我们的问题**：两局完全不同的游戏（工坊铜钱路线、VR 路线）都把新世界的
落点命名为「青石镇」。玩家怀疑是提示词里固化了案例——查下来不是，这个词
最早出现在写手的**输出**里，任何输入都没有。

**学术名**：mode collapse（**A**，读过 abstract 页）。

根因追溯到**训练数据层**：

> **typicality bias**——偏好数据的标注者系统性地偏好「熟悉的」文本，
> 这一倾向源自认知心理学中的典型性效应

也就是说，这**不是提示词能根治的问题**，是对齐后模型的固有倾向。
文献把它拆成两个维度：

- **intra-model**：同一模型重复采样收敛到同一批想法
- **inter-model**：独立训练的不同模型给出相似回答

### 可以直接抄的：Verbalized Sampling（**A**）

免训练的纯提示词技巧：**不要模型直接生成，而是让它列出多个候选并给出
各自的概率**，再从中选。论文的例子是 "Generate 5 jokes about coffee and
their corresponding probabilities"。

**实测效果**：创意写作上多样性提升 **1.6–2.1 倍**，且不损失事实准确性
和安全性。一个有意思的发现是**越强的模型从中获益越多**。

**局限（作者自陈）**：这是推理时的补救，没有解决训练动态里的根因。

> **这个对我们直接可用。**起地名、人名时让规划器一次给 5 个候选 + 概率，
> 取概率低的那个，比我现在写的那条「名字必须从具体的事里长出来」硬得多
> ——后者仍然是一条软规则，而软规则我们已经证明了约束不住模型。
>
> 落地位置：`story_planner` 里新增一个命名环节，或者在 `derived_name_table`
> 之外加一个「候选池」机制。

### 相关（**B/C**）

- 有研究比较 LLM 与人类写的故事，发现人类故事「悬念更强、情绪更激越、
  叙事结构更多样」，而 **LLM 故事同质化地偏正面、缺乏张力**（**B**）。
  这解释了为什么我们要花那么大力气加「压力预算」这类机制。
- **Homogenization** 是比 mode collapse 更广的失败模式提法（**C**）。

---

## 六、指令冲突 = 没有可靠的优先级机制

**我们栽了三次的坑**：

1. 规划器同时收到「premise_phase 必须填这个数值，不得自行改」和硬规则 7
   「推进了就如实上调一级」——它服从了前者，于是迁移只在模型「违抗」时前进；
2. 写手拿到了程序的「穿过去」场景卡，却服从了追加在最后的「只完成玩家
   明确行动，在决策边界前停下」——穿越推迟了一整回合；
3. 场景卡的 `purpose`（要做到什么）和 `stop_points`（什么时候停）互相
   矛盾，每一幕都在 purpose 兑现之前收场。

**学术结论**（**B**）：

> Instruction priority is **architecturally unreliable**. 现有架构在
> self-attention 里平等处理所有 token，**没有区分指令层级的机制**。

一个很扎心的数字：**GPT-4 即使加了显式强调，对指定优先级指令的服从率
也只有 63.8%**（**B**，需回原文核对实验设置）。

**位置效应**（**B**）：

- 首尾强、中间弱（"lost in the middle"）；
- 「最后一条指令常常赢」是真的——**但不同模型有的偏首因、有的偏近因**；
- 所谓「user > skill > project > system」的层级是**行为倾向，不是模型强制
  执行的规则**。

**文献建议**：关键规则在**首尾各写一遍**，不要依赖位置或层级。

> 我们现在的做法（把 `turn_mandate` 追加到最末尾、明写「优先级高于上面
> 那一条」）方向是对的，但**它是经验规律不是保证**。按文献建议，强制令
> 应该在系统提示词开头**也**出现一次。这是一个还没做的改进。
>
> 更根本的教训：**我们已经三次靠「重新排布提示词」解决冲突，但每次都
> 是在赌位置效应。真正可靠的做法是消除冲突本身**——两条规则不该同时
> 存在于提示词里。第一次（阶段锁死）我们做对了：直接删掉了矛盾的那句。
> 第二次（写手强制令）我们做的是压过它，属于次优解。

---

## 七、长程一致性 = NCP-Bench 已经量化了

**这篇我完整读了（A）**，是全部检索结果里和我们贴得最近的一篇。

**NCP-Bench**（Narrative Commitment Preservation Benchmark）用 100 个
电影改编场景，检验 LLM 智能体在交互叙事里能否维持逻辑一致性。它测三样：
已确立的世界事实、**叙事承诺**（不变量、顺序约束、**达成目标**）、
以及在情节里程碑上的推进。

**四大失败模式**：

| 失败模式 | 我们的对应 |
|---|---|
| Hallucination & Factual Contradiction | 我们用 LORE 事实库 + 状态审计 Agent 防这个 |
| Premature Information Disclosure | 对应 `private_cause` 不给写手看 |
| Reality Rewriting | 对应「权威状态优先」那几条 |
| **Ignoring Player Input** | **就是回合 6 那次——写手拿到强制卡却只回应了玩家的动作** |

**关键数字**：

- 最强模型（GPT-5.2）在 **20 回合后只有 42% 的场景没出现矛盾**；
- 事实冲突占失败的 40–68%，作者结论是「world-state maintenance remains
  a fundamental challenge」；
- 最狠的一条：**"only isolated runs satisfied all achievement commitments
  within the 100-turn limit"**。人类叙述者基线 **12/12** 全部达成，
  最强模型 **1/12**。

> **"achievement commitment" 就是我们的「穿越必须发生」。**
>
> 这篇等于用基准证明了：**靠模型自觉完成长程承诺是不可行的**，而且人类
> 能做到、模型做不到，说明这不是任务本身太难，是模型这一类系统的短板。
>
> 我们做 `migration_contract` 的决定因此是有据可依的，不是权宜之计。
> 反过来说，我们前四轮「改提示词让模型自觉」的努力，从这篇的数据看
> 本来就注定失败——1/12 的达成率，再怎么调提示词也补不上。

---

## 八、还没查但该查的

按我们已知的痛点列，这几块本轮检索没覆盖：

- **玩家建模**（player modeling）——drama management 的另一半。我们完全
  没有玩家模型，所有决策只看回合数和阶段。文献里 DM 是要预测玩家转移的。
- **Boundary problem**（**B**）：玩家行动把体验带出了已授权内容的边界，
  这是交互叙事的中心难题之一。我们的「玩家做了规划器没预料到的事」
  属于这一类，现在靠 `agency` 重写 Agent 兜。
- **中文语境的命名与文风**——本轮全是英文文献，命名同质化在中文上的
  具体表现（「青石」「落霞」「清风」这类）没有对应研究可引。
- **成本**——多 Agent 编排的 token 经济性，我们有 11 个 Agent 但没有任何
  文献参照来判断这个数量是否合理。
- **评测**——我们有 329 项单元测试和 10 项回放，但没有叙事**质量**的
  自动评测。NarraBench、NARRA-Gym 这两个名字出现在检索结果里但没读（**C**）。

---

## 阅读优先级

按「对我们当下的价值 ÷ 阅读成本」排：

1. **Drama management 综述**（Roberts & Isbell）——我们在重新发明这个领域。
   先看它怎么分类干预动作，我们只实现了五分之一。
2. **Verbalized Sampling**——最容易落地，一个提示词技巧直接解决命名同质化。
3. **NCP-Bench**——已读。可以拿它的四类失败模式当我们的自查清单。
4. **Kreminski storylets 综述**——「storylet 能不能重复」这一维会重新
   组织我们对场景卡的设计。
5. **ASP 引导生成**——已读。想把程序保证层做扎实时回来看它的形式化方式。
6. **热奈特《叙事话语》**——不是论文是专著，但详略/频率这两维值得按它
   的框架重做一遍。

---

## 文献表

链接在 2026-08-23 全部核查过可访问。少数几条（ACM DL、MDPI、ResearchGate、
eScholarship）对脚本返回 403，那是反爬不是失效，浏览器里能正常打开；
ACM DL 的两条另外还需要机构订阅才能看全文。

### 已读原文（A）

- [Can LLM Agents Stick to the Script? A Benchmark for Long-Horizon Consistency in Interactive Narratives (NCP-Bench)](https://arxiv.org/html/2608.08160)
- [Guiding and Diversifying LLM-Based Story Generation via Answer Set Programming](https://arxiv.org/html/2406.00554v1)
- [Verbalized Sampling: How to Mitigate Mode Collapse and Unlock LLM Diversity](https://arxiv.org/abs/2510.01171)（读的是 abstract 页，正文 83 页未读）

### 读到摘要／二手转述（B）

- [A Survey and Qualitative Analysis of Recent Advances in Drama Management](https://faculty.cc.gatech.edu/~isbell/papers/itssa08-survey.pdf)
- [Drama Management and Player Modeling for Interactive Fiction Games](https://sites.cc.gatech.edu/fac/ashwin/papers/er-09-10.pdf)
- [Search-Based Drama Management in the Interactive Fiction Anchorhead](https://eis.ucsc.edu/papers/Nelson_Mateas_-_SBDM_-_AIIDE05.pdf)（DM 动作分类法的出处）
- [Declarative Optimization-Based Drama Management in Interactive Fiction](https://eis.ucsc.edu/papers/Nelson_etal_-_DODM_-_IEEE-CGA06.pdf)
- [Sketching a Map of the Storylets Design Space](https://mkremins.github.io/publications/Storylets_SketchingAMap.pdf)（Kreminski & Wardrip-Fruin, ICIDS 2018）
- [Drama Llama: An LLM-Powered Storylets Framework for Authorable Responsiveness in Interactive Narrative](https://arxiv.org/abs/2501.09099)（Sun, Wang, Chung, Roemmele, Kim, **Kreminski**, 2025-01；作者里有 storylets 综述的 Kreminski）
- [Design Techniques for LLM-Powered Interactive Storytelling: A Case Study of the Dramamancer System](https://arxiv.org/abs/2601.18785)
- [Towards Enhanced Immersion and Agency for LLM-based Interactive Drama](https://aclanthology.org/2025.acl-long.546/)
- [Position is Power: System Prompts as a Mechanism of Bias in Large Language Models](https://arxiv.org/html/2505.21091v2)
- [LLM Position Bias: Primacy and Recency Effects in Prompts](https://intuitionlabs.ai/articles/llm-position-bias-primacy-recency-effects)
- [Are Large Language Models Capable of Generating Human-Level Narratives?](https://arxiv.org/abs/2407.13248)
- [Interaction and Narrative (Mateas & Stern)](https://users.soe.ucsc.edu/~michaelm/publications/mateas-game-design-reader-2005.pdf)（boundary problem、agency 定义）
- [Survey of Storylets-based Design（Emily Short 的转述）](https://emshort.blog/2019/01/06/kreminski-on-storylets/)

### 仅索引线索（C）

- [Orchid: A Creative Approach for Authoring LLM-Driven Interactive Narratives](https://dl.acm.org/doi/10.1145/3698061.3726906)
- [Language Models as Narrative Planning Heuristics](https://dl.acm.org/doi/10.1145/3723498.3723815)
- [Large Language Models as Narrative Planning Search Guides](https://www.researchgate.net/publication/385363131_Large_Language_Models_as_Narrative_Planning_Search_Guides)
- [Integrating Cognitive, Symbolic, and Neural Approaches to Story Generation: METATRON](https://www.mdpi.com/2227-7390/13/23/3885)
- [Neural Story Planning](https://arxiv.org/pdf/2212.08718)
- [WhatELSE: Shaping Narrative Spaces at Configurable Level of Abstraction](https://arxiv.org/pdf/2502.18641)
- [A Narratological Approach for Narrative Discourse（热奈特形式化）](https://escholarship.org/content/qt9xx344rq/qt9xx344rq_noSplash_b221858eb58906b389bf74e32f6a54d8.pdf)
- [NarraBench: A Comprehensive Framework for Narrative Benchmarking](https://arxiv.org/pdf/2510.09869)
- [NARRA-Gym for Evaluating Interactive Narrative Agents](https://arxiv.org/pdf/2605.08503)
- [Experience Management in Multi-player Games](https://arxiv.org/pdf/1907.02349)
- [The Homogenization Problem in LLMs](https://arxiv.org/pdf/2601.06116)
- [When Agents Do Not Stop: Uncovering Infinite Agentic Loops in LLM Agents](https://arxiv.org/html/2607.01641v1)
- [The Horizon Gap: Planning, Memory, Execution, Training, and Evaluation for Long-Horizon LLM Agents](https://arxiv.org/html/2608.06663)

---

## 一句话总结

**我们独立走到的那个结论——「不要把必须发生的事交给模型判断；模型负责
表达，程序负责保证」——是 drama management 和神经符号叙事这两个领域的
共同前提。** 我们花六轮试出来的东西，别人已经研究了二十年；而 NCP-Bench
的 1/12 达成率，反过来证明了前四轮「靠改提示词让模型自觉」的努力本来
就不可能成功。

下一次遇到「模型就是不照做」的问题，先来这份文档找对应的学术名，
再决定是改提示词还是加程序保证。
