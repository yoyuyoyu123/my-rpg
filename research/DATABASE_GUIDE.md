# 研究数据库使用指南

本指南说明 [research_db.json](./research_db.json) 的数据口径、字段语义、标签归一、查询方式和更新流程。它服务于 AI 文字游戏的题材检索与组合设计，不是销量数据库、首发年表或文学质量排行榜。

如果本指南、旧研究说明和数据库中的统计不一致，以重新运行 [build_research_db.mjs](../tools/build_research_db.mjs) 后的 `coverage` 与聚合字段为准。

## 1. 当前快照

2026-07-12 重新运行构建器后的结果：

| 项目 | 当前值 |
|---|---:|
| `schema_version` | `2.0.0` |
| 覆盖期 | `2016-2026YTD` |
| 原始作品记录 | 397 |
| 跨年去重后的作品 | 392 |
| 作品源文件 | 7 |
| 标签 crosswalk 文件 | 3 |
| 本体版本 | `1.2.0` |
| 本体维度 | 17 |
| 本体标签（去重） | 683 |
| 分类内标签条目 | 698 |
| crosswalk 记录 | 2,556 |
| 合并作品中的不同 raw tag | 2,390 |
| 来源 URL 引用次数 | 528 |

去重后按载体分布：

| `medium` | 作品数 |
|---|---:|
| `web_novel` | 120 |
| `light_or_web_novel` | 145 |
| `manga` | 127 |

原始记录实际由中国网文 125 条、日本 Web／轻小说 145 条、漫画 127 条组成。中国网文有 5 部作品跨年重复入选，合并后变成 120 部；日本侧合计 272 部。

证据记录按原始入选记录计数，而非按 392 部去重作品计数：

| `evidence_strength` | 记录数 |
|---|---:|
| A | 322 |
| B | 73 |
| C | 2 |

crosswalk 动作分布：

| `action` | 记录数 |
|---|---:|
| `existing` | 204 |
| `alias` | 1,421 |
| `new_candidate` | 0 |
| `keep_raw` | 931 |

这些计数描述研究库内部，不代表市场份额、读者偏好或题材真实流行率。

## 2. 数据文件与构建关系

原始作品文件：

- [china_works_2016_2020.json](./china_works_2016_2020.json)
- [china_works_2021_2024.json](./china_works_2021_2024.json)
- [china_works_2025_2026.json](./china_works_2025_2026.json)
- [japan_works_2016_2020.json](./japan_works_2016_2020.json)
- [japan_works_2021_2026.json](./japan_works_2021_2026.json)
- [manga_works_2016_2020.json](./manga_works_2016_2020.json)
- [manga_works_2021_2026.json](./manga_works_2021_2026.json)

标签与归一文件：

- [tag_ontology.json](./tag_ontology.json)：正式本体。
- [china_tag_crosswalk.json](./china_tag_crosswalk.json)
- [japan_tag_crosswalk.json](./japan_tag_crosswalk.json)
- [manga_tag_crosswalk.json](./manga_tag_crosswalk.json)

[build_research_db.mjs](../tools/build_research_db.mjs) 读取上述文件，完成标题归一、跨年合并、标签展开和聚合统计，最后覆盖生成 `research_db.json`。`research_db.json` 是衍生物，不应手工修补；需要改数据时应改原始文件、本体或 crosswalk，然后重建。

当前没有独立的 JSON Schema 文件。实际 schema 由构建脚本、`schema_version` 和本指南共同定义。[validate_research_db.mjs](../tools/validate_research_db.mjs) 只检查基础必填字段、数组类型和跨文件同名警告，不会检查全部证据语义、crosswalk 冲突或 canonical 标签是否真的存在于本体。

## 3. 覆盖范围与样本选择

本库采用“年度可见度 + 机制覆盖”的目的性分层抽样：

1. 用正式榜单、奖项、年度报告、平台大赛和出版社资料建立每年主干。
2. 保留能够代表商业可见度的作品，但不把热门榜首当作唯一入口。
3. 主动加入叙事位置、身体形态、职业流程、关系结构或文本形式特别的作品；创新样本可以不属于销量头部，但必须有可核实来源。
4. 对同一作品原则上避免逐年重复占位；若不同年度确有独立榜单或影响节点，则保留为多个 evidence 记录并在主库合并。
5. 标签是为互动叙事引擎制作的分析编码，不是平台或出版社标签的逐字复制。

各批次方法详见：

- [中国网文 2016—2020 说明](./china_works_2016_2020_notes.md)
- [中国网文 2025—2026 YTD 说明](./china_works_2025_2026_notes.md)
- [日本小说 2016—2020 说明](./japan_works_2016_2020_notes.md)
- [日本小说 2021—2026 YTD 说明](./japan_works_2021_2026_notes.md)
- [漫画 2016—2020 说明](./manga_2016_2020.md)
- [漫画 2021—2026 YTD 说明](./manga_2021_2026.md)
- [总体研究报告](./RESEARCH_REPORT.md)

主要证据域包括：

- 中国：`chinawriter.com.cn` 及其 `wyb`、`image` 子域，`cssn.cn`，以及 `jjwxc.net`、`qidian.com` 等原始作品或荣誉页。
- 日本小说：`tsugirano.jp`、`kakuyomu.jp`、`kadokawa.co.jp`、`ichijinsha.co.jp`，以及作为年度榜整理的 `shopping.bookoff.co.jp`、`books.rakuten.co.jp`。
- 漫画：`mangataisho.com`、`tsugimanga.jp`、`j-mediaarts.jp`，以及 `kodansha.co.jp`、`kadokawa.co.jp`、`shueisha.co.jp` 等出版社或连载平台。

平台、奖项和媒体各自覆盖不同人群，因此“来源权威”不等于“市场代表性完整”。

## 4. `year` 与 `recognition_years` 的语义

原始记录中的 `year` 是“研究观察锚点”，可能表示：

- 进入当年榜单或奖项；
- 当年出版、完结、漫画化或形成明显传播；
- 当年年度报告确认其类型影响；
- 2026 YTD 截止日前可核实的阶段性可见度。

它不保证等于 Web 首发年、第一卷出版年、首次连载年或动画播出年。因此禁止用本库直接统计“每年新作数量”。2026 仅是年中快照，不能和完整年度进行等权的年度冠军或增速比较。

主库中的 `recognition_years` 是同名作品所有原始 `year` 的去重、升序集合。年度聚合的作品数合计仍为 397，而 canonical 作品数是 392，因为 5 部作品保留了两个年度节点：

- 《开端》：2019、2022
- 《砸锅卖铁去上学》：2019、2021
- 《第一序列》：2020、2021
- 《故障乌托邦》：2024、2025
- 《天才俱乐部》：2024、2025

## 5. 证据等级 A／B／C

`evidence_strength` 衡量 `popularity_basis` 或纳入理由的可核验强度，不评价作品质量、销量规模、标签正确率或是否值得推荐。

| 等级 | 通用定义 | 典型来源 |
|---|---|---|
| A | 官方奖项、正式榜单、协会或年度报告、出版社／平台／作品官网的直接记录 | 中国作家网与蓝皮书、次にくるライトノベル大賞、Kakuyomu 比赛、漫画大赏、出版社书目 |
| B | 权威媒体、可靠零售年度榜、平台或行业材料的间接支持 | BOOKOFF 年度榜、Rakuten Books、媒体转述、早期平台数据 |
| C | 动态榜、聚合页或较弱二手材料，只能支持审计时点的阶段性可见度 | 小説家になろう动态年度榜、缺少正式详情页的聚合材料 |

同一原始记录有多个来源时，字段保存最强的一个等级。跨年合并后，同一作品的 `evidence` 数组可以同时出现不同等级；查询时应逐条保留，不能把低等级记录删除后假装它从未存在。

更详细的审计口径见：

- [中国作品证据审计](./china_evidence_audit.md)
- [日本小说证据审计](./japan_evidence_audit.md)
- [漫画证据审计](./manga_evidence_audit.md)

推荐的检索策略是：正式趋势分析默认使用 A／B；C 只在“探索性样本”开关打开时使用，并明确显示 YTD 或动态来源。不要把 A、B、C 直接换算成销量权重。

## 6. 跨年去重与作品 ID

构建器使用以下键去重：

```text
medium + NUL + NFKC(title).trim().toLowerCase()
```

`id` 是该键的 SHA-1 前 12 位，并加上 `medium` 前缀。其后果是：

- 同一标题、同一载体的跨年记录会合并。
- 小说与漫画即使同名也不会合并，因为 `medium` 不同。
- 标题标点、正式副标题或译名改变可能产生新 ID；系统没有作者别名、日文原名或作品系列 ID 的模糊匹配。
- 同一标题的不同漫画版本若都属于 `manga`，可能被误并；当前键没有把作者、出版社或 `source_material` 纳入。

合并时，`recognition_years`、`raw_tags`、`canonical_tags` 取并集，`evidence` 逐条追加；作者、平台、主角位置、叙事特征和纳入理由等描述字段采用最先读取的记录。需要比较不同年份的描述变化时，应回到 `evidence.source_file` 指向的原始 JSON，不能只看合并后的首条描述。

## 7. raw tag、canonical tag 与 crosswalk 动作

### 7.1 `raw_tags`

`raw_tags` 保留作品记录中研究者写下的原始标签。它们可以是细粒度机制、复合短语、地域或年代细节，也可能是只对一部作品有意义的钩子。raw tag 的价值是可追溯和精准检索，不要求全部进入随机生成本体。

### 7.2 `canonical_tags`

canonical tag 的目标是把同义词与复合词映射到 17 个可组合轴。一个 raw tag 可以映射到多个 canonical tag，例如把一个“末日科幻”式复合词拆成世界、冲突或节奏轴。

当前快照中 392 部作品全部至少有一个 canonical tag，且所有 canonical tag 都能在当前本体中找到。生产使用时仍建议把 `works[].canonical_tags` 与 `ontology.categories[].tags` 取交集，防止未来导入未决 crosswalk 后污染运行时。

```js
const ontologyTags = new Set(
  db.ontology.categories.flatMap(category => category.tags)
);

const safeCanonicalTags = work =>
  work.canonical_tags.filter(tag => ontologyTags.has(tag));
```

### 7.3 四种 `action`

| 动作 | 含义 | 生产用法 |
|---|---|---|
| `existing` | 审计时 raw tag 与本体完全同名 | 可作为正式标签，但仍检查当前本体成员资格 |
| `alias` | 可安全映射到一个或多个审计时已有标签 | 可用于检索；多目标是跨轴拆分，不表示必须捆绑抽取 |
| `keep_raw` | 太宽、太细、作品专属、市场元数据、否定条件或语义不稳定 | 保留搜索与人工查看；默认不进入随机池和系统提示词 |
| `new_candidate` | 工作阶段发现本体缺口，给出候选名称 | 仅用于评审暂存；当前正式 crosswalk 数量为 0，验证器会拒绝未决候选 |

crosswalk 的 `frequency` 是该原始标签在对应研究样本中的出现次数，不是阅读量或市场频率。`rationale` 说明为何映射或保留，`source_file` 指出该判断来自中国、日本小说还是漫画 crosswalk。

### 7.4 当前候选状态

当前三份正式 crosswalk 已将候选全部裁定为 `existing`、`alias` 或 `keep_raw`，没有待决 `new_candidate`。[ontology_candidate_review_cn_jp.json](./ontology_candidate_review_cn_jp.json) 与 [ontology_candidate_review_manga.json](./ontology_candidate_review_manga.json) 保留的是评审过程和决策依据，不是运行时标签池。

## 8. 字段字典

### 8.1 顶层

| 字段 | 类型 | 语义 |
|---|---|---|
| `schema_version` | string | 衍生数据库结构版本，当前 `2.0.0` |
| `built_at` | ISO datetime | 构建器运行时间，不是资料冻结日 |
| `coverage` | object | 覆盖期、原始／canonical 数量、输入文件清单 |
| `ontology` | object | 正式标签本体及版本 |
| `tag_crosswalk` | array | 三份 crosswalk 的并集，并添加 `source_file` |
| `raw_tag_frequency` | object | 每个 raw tag 出现在多少部去重作品中；作品内只计一次 |
| `yearly_raw_tag_frequency` | object | 按 `recognition_years` 展开的 raw tag 计数 |
| `medium_raw_tag_frequency` | object | 每个载体内拥有某 raw tag 的去重作品数 |
| `evidence_strength_frequency` | object | 原始 evidence 记录的等级计数，当前合计 397 |
| `source_domain_frequency` | object | 来源 URL 引用次数，去掉域名前缀 `www.`；不是不同作品数或不同 URL 数 |
| `works` | array | 392 条去重作品 |

### 8.2 `coverage`

| 字段 | 类型 | 语义 |
|---|---|---|
| `period` | string | 研究覆盖期，当前 `2016-2026YTD` |
| `raw_records` | integer | 所有输入作品记录数，含跨年重复 |
| `canonical_works` | integer | 按 medium 与规范化标题合并后的作品数 |
| `work_files` | string[] | 实际纳入构建的作品文件 |
| `crosswalk_files` | string[] | 实际纳入构建的 crosswalk 文件 |

### 8.3 `ontology`

| 字段 | 类型 | 语义 |
|---|---|---|
| `version` | string | 本体版本，当前 `1.2.0` |
| `scope` | string | 本体研究范围 |
| `principles` | string[] | 正交组合、禁止自动推导等总原则 |
| `categories` | array | 17 个标签轴 |
| `updated_at` | ISO datetime | 本体最后更新时点 |

每个 category 包含 `id / label / selection / tags`。当前 `selection` 值有 `multi`、`single_or_custom`、`multi_optional`、`multi_default`；它只是 UI／抽样建议，构建器不会执行数量限制或互斥校验。

### 8.4 `tag_crosswalk[]`

| 字段 | 类型 | 语义 |
|---|---|---|
| `raw_tag` | string | 原始标签 |
| `frequency` | integer | 对应源样本中的出现次数 |
| `canonical_tags` | string[] | 映射目标或候选名称；`keep_raw` 应为空 |
| `action` | enum | `existing / alias / new_candidate / keep_raw` |
| `rationale` | string | 人工归一理由 |
| `source_file` | string | 此判断来自哪份 crosswalk |

### 8.5 `works[]`

| 字段 | 类型 | 语义 |
|---|---|---|
| `id` | string | medium + 规范化标题的稳定散列；标题变化会改变 ID |
| `region` | string | `CN` 或 `日本`；合并时采用首条记录 |
| `medium` | enum | `web_novel / light_or_web_novel / manga` |
| `title` | string | 首条记录的展示标题 |
| `author` | string | 作者或创作署名 |
| `platform_or_publisher` | string | 平台、出版社或榜单载体 |
| `source_type` | enum-like string | 当前观察到 `original / adaptation / original_nonfiction` |
| `source_material` | string/null | 漫画原作或来源说明；小说通常为 null |
| `recognition_years` | integer[] | 所有年度观察锚点 |
| `raw_tags` | string[] | 跨记录去重后的原始标签并集 |
| `canonical_tags` | string[] | crosswalk 展开结果；生产前必须与本体取交集 |
| `canonical_tags_by_category` | object | canonical tag 按 17 个 category id 分组；便于按轴查询，不表示已执行互斥或数量限制 |
| `protagonist_role` | string | 主角身份和叙事位置的研究归纳 |
| `narrative_features` | string/string[] | 叙事机制；当前 339 条为字符串、53 条为数组 |
| `why_included` | string | 作品为何对趋势或生成机制有价值 |
| `evidence` | array | 每个原始入选记录的年度依据和来源 |

### 8.6 `works[].evidence[]`

| 字段 | 类型 | 语义 |
|---|---|---|
| `recognition_year` | integer | 对应原始记录的 `year` |
| `source_file` | string | 原始作品 JSON 文件 |
| `popularity_basis` | string | 年度可见度、奖项或纳入依据 |
| `evidence_strength` | `A/B/C` | 该 evidence 记录的来源强度 |
| `sources` | string[] | 直接来源 URL |

## 9. 查询建议

### 9.1 先确定研究问题，再选字段

- 查“哪类身份可用于仙侠”：用 `safeCanonicalTags(work)` 过滤 `world_frame` 与 `narrative_position`，再读 `protagonist_role`。
- 查“低悬疑职业循环”：筛选 `profession / story_engine / tone`，不要仅搜索作品标题或简介中的“日常”。
- 查“某年被看见的机制”：用 `recognition_years`，并回到对应 `evidence` 和原始文件确认该标签是否确实属于该年的记录。
- 查来源强度：按 `evidence` 数组逐条判断，不要给整部作品永久贴一个单一等级。

基础筛选示例：

```js
const gradeRank = { A: 3, B: 2, C: 1 };
const ontologyTags = new Set(
  db.ontology.categories.flatMap(category => category.tags)
);

function tagsOf(work) {
  return work.canonical_tags.filter(tag => ontologyTags.has(tag));
}

function bestEvidence(work) {
  return work.evidence.reduce(
    (best, item) => !best || gradeRank[item.evidence_strength] > gradeRank[best.evidence_strength]
      ? item : best,
    null
  );
}

function query(requiredTags, { medium, minGrade = 'B' } = {}) {
  return db.works.filter(work => {
    if (medium && work.medium !== medium) return false;
    const evidence = bestEvidence(work);
    if (!evidence || gradeRank[evidence.evidence_strength] < gradeRank[minGrade]) return false;
    const tags = new Set(tagsOf(work));
    return requiredTags.every(tag => tags.has(tag));
  });
}
```

### 9.2 不用 raw frequency 当热门权重

`raw_tag_frequency` 与 crosswalk 的 `frequency` 受样本选择、批次标注粒度和同义词拆分影响。推荐两阶段抽样：

1. 先按地区、载体、完整年度／YTD、证据等级分层，避免单一来源占满结果。
2. 再在目标标签轴内抽样，优先覆盖不同机制；频次只用于发现过稀或过宽标签，不直接作为概率。

每部 canonical 作品只应有一票；不要因为一部作品有两个 evidence 记录，就在随机池中出现两次。

### 9.3 作品是证据样例，不是仿写模板

一次游戏只检索 3—6 条相关作品的 `narrative_features` 与 `why_included`，转成无作品名、无角色名的抽象可供性，例如“固定地点接待不同社会群体；职业劳动推动关系累积”。不要向模型下达“模仿某作品”的指令。

## 10. 随机组合建议

推荐按轴独立抽取，而不是把“异世界”“仙侠”“赛博”当成预制剧情包：

```text
world_frame             1—2
provenance              0—1
embodiment              0—1
narrative_position      1
profession              0—2
story_engine            1 个主发动机 + 0—1 个辅助发动机
relationship            0—2
information_structure   0—2
tone                    1—2
conflict_source         0—2
pacing                  1
constraint_policy       保留默认自由度约束
```

组合流程建议：

1. 玩家明确选择优先，随机器只补空轴。
2. 只阻止逻辑矛盾，不阻止市场少见组合。
3. 世界框架不得自动推导物种、性别、职业、恋爱或主角位置。
4. `story_engine` 决定事件池，`tone` 和 `conflict_source` 决定压力；“民俗”“赛博”“梦境”本身不自动开启阴谋。
5. 选择非人或身体差异时，同时生成感知、行动、维护需求和社会位置。
6. 选择职业时，至少生成核心劳动、服务对象、资源和失败后果。
7. 选择关系时，记忆系统保存承诺、边界、共同项目和已公开事实，不只存好感度。
8. 2026 YTD 应单独分层或降权，不能因新近可见度压过完整年度。

未选择的高频套路不得自动激活。`keep_raw` 只能在用户明确输入或作品级检索时作为局部修饰；未决候选不得进入默认随机池。

## 11. 当前构建器的已知限制

### 11.1 crosswalk 还不是按来源作用域映射

构建器目前以 `raw_tag` 作为全局键，并按文件名顺序加载三份 crosswalk；后加载的同名 raw tag 会覆盖前一份映射。当前有 144 个 raw tag 出现在多份 crosswalk，其中 28 个的动作或映射目标不一致。

因此，要求精确地区语义时应查询原始作品文件及对应 crosswalk。后续构建器应改为 `source_file/medium + raw_tag` 复合键；在修复前，主库 `canonical_tags` 只适合经过本体交集后的宽检索。

### 11.2 `canonical_tags` 未过滤未决候选

构建器会直接接收 crosswalk 的 `canonical_tags`，不会在构建作品时再次按 action 求交。当前快照经过新版验证器检查后，本体外目标为 0，且 392 部作品全部有 canonical tag；生产端继续使用 `safeCanonicalTags`，可防止未来未审数据绕过流程。

### 11.3 年度 raw tag 聚合会传播合并标签

`yearly_raw_tag_frequency` 先合并作品的全部 raw tag，再把这个并集计入每个 `recognition_year`。对 5 部跨年作品，这可能把后一年补充的标签回填到前一年。需要严谨年度标签分析时，直接统计原始 `*_works_*.json`，不要使用该聚合作为唯一证据。

### 11.4 历史 action 可能滞后于本体

`new_candidate` 只属于评审阶段。候选晋升或拒绝后，必须同步把 crosswalk 改成 `existing`、`alias` 或 `keep_raw`；当前验证器会拒绝任何未裁定 action，避免候选直接进入主库。

## 12. 偏差与禁止用途

主要偏差：

- 中国正式榜单偏重精品化、现实题材、文化价值与官方可见度，可能低估免费阅读、女性向站内爆款和已下架作品。
- 日本小说样本对 KADOKAWA、主流文库、BOOKOFF 与年度榜可检索作品覆盖较好，但 BL、百合、成人女性向和小平台不足。
- 漫画大赏偏向书店员推荐，下一部漫画大赏偏向网络动员与年轻连载；女性向条漫、同人、成人向和小型平台不足。
- 出版社简介能确认设定与出版关系，但带有营销选择；奖项入围也不是文学质量的绝对判断。
- 中文标签是跨语言研究归纳，译名、粒度和文化语义可能损失。
- 不同批次的标签粒度不同，单例 raw tag 很多；频次横向比较会受编码风格影响。
- 2026 是 YTD；预约、首日榜和动态年度榜都可能变化。
- 漫画改编与小说原作是不同 medium，但同一 IP 的相关性未建专门系列 ID。

禁止用途：

1. 不得把样本计数解释为中国或日本市场份额、销量、收入或读者人口比例。
2. 不得用 `year` 统计年度新作量、平均出版周期或首发趋势。
3. 不得把 A／B／C 当作作品质量、文学价值或商业成绩分数。
4. 不得从世界标签推断主角性别、性取向、物种、职业、恋爱结构或道德立场。
5. 不得从 `女性向`、BL、百合等市场／关系标签推断真实作者或读者身份。
6. 不得把 raw tag 频次当成随机生成的默认概率。
7. 不得把作品名和具体角色送入提示词要求近似仿写；数据库用于机制抽象，不用于复制受版权保护的表达。
8. 不得把来源 URL 的存在解释为页面永久可访问、作品版权清晰或资料已获再分发许可。
9. 不得用当前聚合字段进行统计显著性、因果关系或“近十年全市场必然趋势”断言。

## 13. 更新流程

### 13.1 增加作品记录

1. 编辑对应的 `*_works_*.json`，不要直接编辑 `research_db.json`。
2. 至少填写 `year / title / author / platform` 或 `platform_or_publisher / popularity_basis / evidence_strength / tags / protagonist_role / narrative_features / why_included / sources`。
3. `evidence_strength` 必须为单字符 `A / B / C`；`sources` 必须是非空 URL 数组。
4. 同步更新相应 notes 的选择口径、冻结日期和局限。
5. 若作品跨年再次入选，保留新的原始记录；构建器会合并 evidence。若只是修正旧记录，不要复制一条新记录。

### 13.2 更新 crosswalk

按区域生成候选 crosswalk，并人工复核 diff：

```powershell
node research/build_china_tag_crosswalk.js
node research/build_japan_tag_crosswalk.js
node research/build_manga_tag_crosswalk.js
```

这些生成器可能重新产生 `new_candidate`，因此其输出是评审中间态，不能直接交给正式 builder。必须先裁定候选并更新生成规则；不要为追求较低的 `keep_raw` 比例而强行映射语义不稳定标签。

### 13.3 评审和应用候选

1. 中日小说候选由 [build_ontology_candidate_review_cn_jp.js](./build_ontology_candidate_review_cn_jp.js) 汇总，人工决定 `add / merge / defer / reject`。
2. 漫画候选单独查看 [ontology_candidate_review_manga.json](./ontology_candidate_review_manga.json)；当前应用工具不会处理它。
3. 当前 `apply_ontology_candidates.mjs` 仍只读取中日小说评审，并把版本硬编码为 `1.1.0`；正式本体已是 `1.2.0`，因此在修正脚本的版本更新逻辑与漫画评审入口前，不得直接运行它。

历史命令如下，仅供维护者定位工具，不是当前可安全重复执行的更新命令：

```powershell
node tools/apply_ontology_candidates.mjs
```

4. 修正并执行升级工具后，检查 [ontology_change_log_cn_jp.json](./ontology_change_log_cn_jp.json)，并按语义版本规则更新本体版本。升级工具会改写 `updated_at`，不要把它当无副作用的只读检查重复运行。
5. 同步更新 crosswalk action，避免历史 `new_candidate` 与新本体脱节。

### 13.4 构建与验证

```powershell
node tools/validate_research_db.mjs
node tools/build_research_db.mjs
node tools/validate_research_db.mjs
```

地区证据审计还可运行：

```powershell
node research/validate_china_evidence.js
node research/audit_japan_evidence.js
node research/apply_manga_evidence_strength.js
```

后两个脚本会写回作品 JSON，运行前应先确认分类规则和 diff；不能只把它们当只读 validator。

最后人工检查：

- builder 输出的 `raw_records / canonical_works / work_files / crosswalk_files`；
- `evidence_strength_frequency` 是否只含 A／B／C；
- canonical 标签与本体的差集；
- 跨 crosswalk 同名 raw tag 的冲突；
- 跨文件重复是否为真实跨年节点，而不是误重复；
- 2026 YTD 的截止日期和措辞；
- `research_db.json` 与本指南中的快照统计是否需要更新。

## 14. 最小生产读取规则

如果暂时不修改构建器，接入应用时至少遵守以下四条：

1. 只读取生成后的 `research_db.json`，但保留回溯到 `evidence.source_file` 的能力。
2. `works[].canonical_tags` 必须和 ontology 取交集。
3. 默认只用 A／B evidence；C 进入单独探索池。
4. 按轴抽取机制并去除作品名，不按 raw frequency 直接加权，不让未选标签自动出现。

这样数据库可以扩大题材和身份自由度，同时避免把研究样本误用成市场排名、仿写语料或固定套路菜单。
