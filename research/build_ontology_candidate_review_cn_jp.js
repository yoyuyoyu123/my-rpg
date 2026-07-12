const fs = require('fs');
const path = require('path');

const base = __dirname;
const ontology = JSON.parse(fs.readFileSync(path.join(base, 'tag_ontology.json'), 'utf8'));
const categoryIds = new Set(ontology.categories.map((category) => category.id));
const existingTags = new Set(ontology.categories.flatMap((category) => category.tags));
const sources = [
  { region: '中国', file: 'china_tag_crosswalk.json' },
  { region: '日本', file: 'japan_tag_crosswalk.json' }
];

const aggregated = new Map();
for (const source of sources) {
  const rows = JSON.parse(fs.readFileSync(path.join(base, source.file), 'utf8'));
  for (const row of rows) {
    if (row.action !== 'new_candidate') continue;
    for (const candidateTag of row.canonical_tags) {
      if (!aggregated.has(candidateTag)) {
        aggregated.set(candidateTag, {
          totalFrequency: 0,
          regions: new Set(),
          rawTags: new Map()
        });
      }
      const item = aggregated.get(candidateTag);
      item.totalFrequency += row.frequency;
      item.regions.add(source.region);
      if (!item.rawTags.has(row.raw_tag)) {
        item.rawTags.set(row.raw_tag, { frequency: 0, regions: new Set() });
      }
      const raw = item.rawTags.get(row.raw_tag);
      raw.frequency += row.frequency;
      raw.regions.add(source.region);
    }
  }
}

const decisions = new Map();
function decide(tags, proposedCategory, decision, mergeInto, rationale) {
  for (const tag of tags) {
    if (decisions.has(tag)) throw new Error(`Duplicate decision: ${tag}`);
    decisions.set(tag, {
      proposed_category: proposedCategory,
      decision,
      merge_into: mergeInto,
      rationale
    });
  }
}

// Add: broad, orthogonal mechanisms that materially change generation.
decide(['生活流'], 'pacing', 'add', [], '中日两区合计支持最高；它是篇章组织方式，不等同群像、慢生活或完全无冲突。');
decide(['喜剧'], 'tone', 'add', [], '现有本体只有若干喜剧子型；上位标签可在子型未知时避免强行推断吐槽、误解或荒诞。');
decide(['地域生活书写'], 'tone', 'add', [], '强调方言、城市记忆、地方文化与乡土经验，能显著改变场景细节和NPC生活方式。');
decide(['音乐题材'], 'world_frame', 'add', [], '覆盖乐队、校园音乐、职业音乐与音乐世界机制；比单一演员职业更广且可复用。');
decide(['搭档关系'], 'relationship', 'add', [], '搭档不必是职业同事、恋人或挚友，独立关系标签可与这些轴自由组合。');
decide(['创作活动'], 'story_engine', 'add', [], '创作可以是写作、绘画、音乐或节目制作，适合作为可重复的故事循环。');
decide(['恋爱要素'], 'relationship', 'add', [], '作为恋爱开关而不预设单一恋爱、后宫、百合或BL，能提升关系自由度。');
decide(['魔女'], 'profession', 'add', [], '作为魔法实践者与社会身份处理，比误并入魔族更安全；可与人类、长生种等身体轴组合。');
decide(['内政治理'], 'story_engine', 'add', [], '财政、官僚、公共服务与制度改革不等同领地建设或战争经营。');
decide(['女性关系中心'], 'relationship', 'add', [], '允许女性双人或多人的关系成为中心，但不自动判定百合或女性群像。');
decide(['病态依恋'], 'relationship', 'add', [], '高依赖、控制欲与执着会直接改变NPC决策，且不能无损归入普通恋爱或多角关系。');
decide(['心理创伤'], 'conflict_source', 'add', [], '创伤是持续冲突来源，不等同一般疾病，也不表示角色已经进入疗愈阶段。');
decide(['多种族社会'], 'world_frame', 'add', [], '表达族群制度、政治与共居方式；单独的身体物种标签无法生成社会结构。');
decide(['双主角'], 'information_structure', 'add', [], '双主角不必双视角，但会改变信息分配与篇章重心，适合作为小说结构标签。');
decide(['分支世界线'], 'information_structure', 'add', [], '多条可变世界线与普通时间回归不同，会改变因果展示和玩家选择后果。');
decide(['技艺传承'], 'growth_mode', 'add', [], '强调跨代学习、守成与再创造，区别单人职业专精和知识优势。');
decide(['现代怪谈'], 'world_frame', 'add', [], '比都市奇幻更聚焦口耳传播、社区与网络怪谈，又不必默认规则怪谈或幕后组织。');
decide(['后日谈'], 'pacing', 'add', [], '原主线结束后的生活、调查和关系变化是一种稳定篇章位置，不等同退休或第二人生。');
decide(['关系边界协商'], 'relationship', 'add', [], '以同意、边界与规则谈判推进关系，能抑制靠误会和强制情节推动的默认模式。');
decide(['非婚关系契约'], 'relationship', 'add', [], '覆盖友情、雇佣、金钱和试用恋人契约；现有婚姻契约过窄。');
decide(['情报人员'], 'profession', 'add', [], '暗桩、情报掮客与卧底共享收集、验证、交易和保密循环，是可复用职业。');
decide(['基层劳动者'], 'profession', 'add', [], '决定社会位置、资源与日常动作，能补足职业库偏精英化的问题。');
decide(['民俗职业'], 'profession', 'add', [], '作为捞尸、扎纸、仪式服务等地方行当的上位生成入口，避免把每种行当写死为独立本体。');
decide(['成人关系'], 'relationship', 'add', [], '经济、工作、同居和长期责任使成年关系与校园恋爱拥有不同约束。');
decide(['反英雄身份'], 'narrative_position', 'add', [], '反勇者与反英雄位置会改写任务正当性和社会评价，不等同勇者队中的非勇者。');
decide(['孤独处境'], 'conflict_source', 'add', [], '长期孤独会影响信息、支持网络和关系需求，是稳定冲突而非单次情绪。');
decide(['广播叙事'], 'information_structure', 'add', [], '广播、听众来信和录音节目具有不同于直播弹幕的延迟互动与声音结构。');
decide(['认知规范错位'], 'conflict_source', 'add', [], '善恶或社会常识错位可以驱动制度冲突与喜剧，不应一律化为普通误会。');
decide(['共同生活'], 'relationship', 'add', [], '同居与合租不必自动形成家庭或恋爱，独立标签能保持关系开放。');
decide(['性别身份错位'], 'conflict_source', 'add', [], '社会呈现、角色身份与他人认知错位不等于身体性转，需单独表示。');
decide(['元叙事'], 'information_structure', 'add', [], '角色或叙述意识到类型、媒介和故事规则，会直接改变信息层。');
decide(['关系伦理灰度'], 'relationship', 'add', [], '允许不理想但非单纯敌对的关系伦理，避免所有亲密关系自动理想化。');
decide(['低压力叙事'], 'tone', 'add', [], '压力等级与是否生活流、是否有目标相互独立，是抑制强行危机的重要控制项。');
decide(['护卫安保'], 'profession', 'add', [], '警戒、路线规划、风险评估与保护目标构成清晰且跨世界可复用的职业循环。');
decide(['心理关系剧'], 'tone', 'add', [], '以人物内在与近距离关系为主要戏剧张力，区别悬疑、纯恋爱喜剧和哲学思辨。');
decide(['拒绝原作路线'], 'story_engine', 'add', [], '关键NPC主动拒绝攻略或退出路线，不等同玩家单方面改变原作结局。');
decide(['性别秩序反转'], 'world_frame', 'add', [], '它改变婚姻、继承、劳动与名誉制度，是社会世界变量而非主角性转。');
decide(['死亡游戏'], 'story_engine', 'add', [], '死亡游戏可一次性、职业化或直播化，不能完整并入无限流或迷宫副本。');
decide(['伪史料互文'], 'information_structure', 'add', [], '伪史料与不可靠史笔通过文献互证生成真相，明显区别一般档案文书。');
decide(['反系统叙事'], 'constraint_policy', 'add', [], '不仅是没有系统，而是主动质疑、拒绝或反转系统奖励逻辑。');
decide(['返乡再开始'], 'provenance', 'add', [], '返乡者带着外部经验重新进入熟人社会，区别普通移居和故事结尾的归隐。');
decide(['梦境穿行'], 'story_engine', 'add', [], '梦境可作为访问其他时间、世界和心理空间的重复入口。');
decide(['多时空并置'], 'information_structure', 'add', [], '同时呈现多个时间层不同于单纯倒叙或一次时间跳跃。');
decide(['传统文化能力体系'], 'story_engine', 'add', [], '把戏曲、曲艺等技艺转换为规则化能力，能产生训练、表演与战斗的复合循环。');
decide(['现实主义'], 'tone', 'add', [], '强调因果、制度和生活成本，可约束幻想世界也保持现实质感，不等同职业写实。');
decide(['离婚后生活'], 'provenance', 'add', [], '婚姻结束后的资源、身份与关系重建是稳定开局，不能用婚约破弃替代。');
decide(['敌对关系'], 'relationship', 'add', [], '敌对不必发展为恋爱或长期宿敌，需保留中性上位关系。');
decide(['潜伏谍报'], 'story_engine', 'add', [], '身份维持、情报交换与暴露风险构成跨题材可复用的行动循环。');
decide(['反乌托邦'], 'world_frame', 'add', [], '制度压迫与社会控制是稳定世界框架，不能只由监控或公司压迫标签拼凑。');
decide(['原作开局前'], 'story_engine', 'add', [], '在教程或主剧情开始前行动会改变资源与关系，是独立于原作知识的时间窗口。');
decide(['故障文本'], 'information_structure', 'add', [], '乱码、损坏UI和信息污染是数字原生叙事手段，能直接用于HTML表现。');
decide(['传记体'], 'information_structure', 'add', [], '按人物一生重建事件不同于普通长时间跳跃，可容纳证词、史料和阶段回顾。');
decide(['桌游社交'], 'story_engine', 'add', [], '桌游规则、胜负和谈判可重复驱动关系，不等同电子游戏世界。');
decide(['封闭空间'], 'world_frame', 'add', [], '空间封闭会限制资源、移动与社交，虽支持量低但机制高度通用且可执行。');
decide(['受害者行动主体'], 'narrative_position', 'add', [], '把受害者设为决策者而非线索或奖励，能显著改变叙事伦理和任务设计。');
decide(['异世界幻想'], 'world_frame', 'add', [], '现有本体缺少不预设魔法强度、文化原型和主角来历的通用异世界框架。');
decide(['中式怪诞'], 'tone', 'add', [], '结合本土现实、民俗与荒诞感，不应强制归入喜剧或克苏鲁。');
decide(['NPC视角'], 'narrative_position', 'add', [], 'NPC作为主角不必觉醒自我，也不必是原作配角；该位置能改变信息边界。');
decide(['和风幻想'], 'world_frame', 'add', [], '和风幻想不必是民俗志怪，作为文化审美框架可与高魔、日常等轴组合。');
decide(['妖精族'], 'embodiment', 'add', [], '妖精既不总是元素生命也不等同亚人，是高复用的独立存在形态。');
decide(['增强现实'], 'world_frame', 'add', [], '增强现实叠加现实空间，与完全沉浸式虚拟现实有不同移动和社会机制。');

// Merge: existing ontology or another accepted candidate already covers the concept.
decide(['轻喜剧'], 'tone', 'merge', ['喜剧'], '轻喜剧是喜剧的低压力子型；保留原始词控制强度，无需再建平行上位标签。');
decide(['传统表演艺人'], 'profession', 'merge', ['演员偶像'], '曲艺、戏曲与相声可作为演员表演职业的文化变体，具体门类留在原始标签。');
decide(['青春成长'], 'growth_mode', 'merge', ['人格成长', '青春酸甜'], '“青春”信息不足以形成独立机制，可由成长方向与青春基调共同表达。');
decide(['规则生存'], 'conflict_source', 'merge', ['规则公开限制', '生存追逃'], '该候选是规则限制与生存压力的组合，不应再建立组合型本体词。');
decide(['身体残障'], 'embodiment', 'merge', ['身体残障'], '正式本体已经存在完全相同标签。');
decide(['游戏现实主义'], 'tone', 'merge', ['游戏世界', '职业写实'], '这是游戏框架与写实处理方式的组合，可由两个正交标签表达。');
decide(['服务业职业'], 'profession', 'merge', ['现实职业'], '词义过宽且只受一条记录支持；具体服务循环应保留在原始职业标签。');
decide(['异世界生活'], 'world_frame', 'merge', ['异世界幻想', '日常占主导'], '它是异世界框架与日常节奏的组合，不需单独本体标签。');

// Defer: valuable concept but current 17-category schema or evidence is insufficient.
decide(['女性主角', '男性主角', '成年主角', '中年主角', '儿童主角'], 'reject', 'defer', [], '性别与年龄非常有用，但现有17类没有正交的主角档案轴；放入单选的narrative_position或embodiment会与职业、角色位置和物种冲突。');
decide(['记忆主题'], 'reject', 'defer', [], '这是主题而不是既有信息结构；需要未来新增theme轴，不能误并入失忆、未来记忆或倒叙。');
decide(['伴侣辅助位'], 'narrative_position', 'defer', [], '能表达伴侣不占主线的设计，但目前只有一条且原始词带强烈评论色彩。');
decide(['集体行动'], 'story_engine', 'defer', [], '集体争取不同于一般团队成长，但仅一条支持，需更多群体行动样本确认边界。');
decide(['搬迁物流'], 'profession', 'defer', [], '搬家与物流有清晰玩法，但目前仅两条且部分可由快递信使表达，先观察是否持续出现。');
decide(['清洁维护'], 'profession', 'defer', [], '清扫与维护值得保留，但两条样本分别偏清洁和杂务，职业边界尚未稳定。');

// Reject: metadata, redundant umbrella, or too generic to improve generation.
decide(['女性向'], 'reject', 'reject', [], '这是受众／市场元数据，不是故事内容；应进入未来audience字段，不能由它推断主角性别或恋爱结构。');
decide(['成长叙事'], 'reject', 'reject', [], '过于宽泛，无法判断是人格、职业、团队还是战力成长，加入后不会提供可执行约束。');
decide(['非人主角'], 'reject', 'reject', [], '本体已用动物、魔物、不死族、AI等具体embodiment描述主角；再加总括词会重复并降低物种差异。');
decide(['科幻（未指定子类）'], 'reject', 'reject', [], '泛科幻不提供技术、时代或社会机制；应保留原始检索词并由用户选择具体科幻框架。');

const allowedDecisions = new Set(['add', 'merge', 'defer', 'reject']);
const candidateNames = new Set(aggregated.keys());
for (const candidateName of candidateNames) {
  if (!decisions.has(candidateName)) throw new Error(`Missing decision: ${candidateName}`);
}
for (const decisionName of decisions.keys()) {
  if (!candidateNames.has(decisionName)) throw new Error(`Decision without candidate: ${decisionName}`);
}

const output = [...aggregated.entries()].map(([canonicalTag, data]) => {
  const review = decisions.get(canonicalTag);
  return {
    canonical_tag: canonicalTag,
    proposed_category: review.proposed_category,
    supporting_raw_tags: [...data.rawTags.entries()]
      .map(([rawTag, rawData]) => ({
        raw_tag: rawTag,
        frequency: rawData.frequency,
        regions: [...rawData.regions].sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'))
      }))
      .sort((a, b) => b.frequency - a.frequency || a.raw_tag.localeCompare(b.raw_tag, 'zh-Hans-CN')),
    frequency: data.totalFrequency,
    total_frequency: data.totalFrequency,
    regions: [...data.regions].sort((a, b) => a.localeCompare(b, 'zh-Hans-CN')),
    decision: review.decision,
    merge_into: review.merge_into,
    rationale: review.rationale
  };
});

const decisionOrder = { add: 0, merge: 1, defer: 2, reject: 3 };
output.sort((a, b) =>
  decisionOrder[a.decision] - decisionOrder[b.decision] ||
  b.total_frequency - a.total_frequency ||
  a.canonical_tag.localeCompare(b.canonical_tag, 'zh-Hans-CN')
);

for (const row of output) {
  if (row.proposed_category !== 'reject' && !categoryIds.has(row.proposed_category)) {
    throw new Error(`Invalid proposed category for ${row.canonical_tag}: ${row.proposed_category}`);
  }
  if (!allowedDecisions.has(row.decision)) throw new Error(`Invalid decision: ${row.decision}`);
  if (row.decision === 'merge' && row.merge_into.length === 0) {
    throw new Error(`Merge without target: ${row.canonical_tag}`);
  }
  if (row.decision !== 'merge' && row.merge_into.length !== 0) {
    throw new Error(`Non-merge with target: ${row.canonical_tag}`);
  }
  for (const target of row.merge_into) {
    const acceptedCandidate = decisions.get(target)?.decision === 'add';
    if (!existingTags.has(target) && !acceptedCandidate) {
      throw new Error(`Unknown merge target ${target} for ${row.canonical_tag}`);
    }
  }
}

fs.writeFileSync(
  path.join(base, 'ontology_candidate_review_cn_jp.json'),
  `${JSON.stringify(output, null, 2)}\n`,
  'utf8'
);

const summary = output.reduce((result, row) => {
  result[row.decision] = (result[row.decision] || 0) + 1;
  return result;
}, {});
console.log(JSON.stringify({ candidates: output.length, decisions: summary }, null, 2));
