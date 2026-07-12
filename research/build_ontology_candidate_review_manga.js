const fs = require('fs');
const path = require('path');

const base = __dirname;
const ontology = JSON.parse(fs.readFileSync(path.join(base, 'tag_ontology.json'), 'utf8'));
const crosswalk = JSON.parse(fs.readFileSync(path.join(base, 'manga_tag_crosswalk.json'), 'utf8'));
const categoryIds = new Set(ontology.categories.map((category) => category.id));
const existingTags = new Set(ontology.categories.flatMap((category) => category.tags));

const aggregated = new Map();
for (const row of crosswalk) {
  if (row.action !== 'new_candidate') continue;
  for (const candidateTag of row.canonical_tags) {
    if (!aggregated.has(candidateTag)) aggregated.set(candidateTag, { frequency: 0, rawTags: new Map() });
    const item = aggregated.get(candidateTag);
    item.frequency += row.frequency;
    item.rawTags.set(row.raw_tag, (item.rawTags.get(row.raw_tag) || 0) + row.frequency);
  }
}

const decisions = new Map();
function decide(tags, proposedCategory, decision, mergeInto, rationale) {
  for (const tag of tags) decisions.set(tag, {
    proposed_category: proposedCategory,
    decision,
    merge_into: mergeInto,
    rationale
  });
}

// Add:漫画媒介中无法由现有标签无损表达、且能直接改变生成结构的形式。
decide(['内心独白'], 'manga_form', 'add', [], '内在语言可与画面形成反差并承担主要信息，是漫画中可独立控制的叙述形式。');
decide(['短篇结构'], 'manga_form', 'add', [], '表示有限篇幅的结构约束，不自动推断单元剧、闭环结局或连作关系。');
decide(['短篇连作'], 'manga_form', 'add', [], '多个短篇由人物、地点、物品或母题拼成整体，与单篇闭环和普通章节单元剧不同。');
decide(['非虚构漫画'], 'manga_form', 'add', [], '事实承诺、取材责任和叙述者立场会改变内容校验，不能用伪纪录片代替。');

// Merge:现有17类已经能用一个或多个正交标签表达。
decide(['固定地点发动机'], 'story_engine', 'merge', ['日常单元剧', '地点作为主角'], '固定地点是篇章发动机与漫画空间形式的组合，无需新增平行标签。');
decide(['女性关系中心'], 'relationship', 'merge', ['女性关系中心'], '正式本体已经存在完全相同标签。');
decide(['心理创伤'], 'conflict_source', 'merge', ['心理创伤'], '正式本体已经存在完全相同标签。');
decide(['第二人生'], 'provenance', 'merge', ['完成冒险后的第二人生'], '现有来历标签已覆盖主线结束后的第二人生；具体丧偶、离职或退役保留原始标签。');
decide(['服务业职业'], 'profession', 'merge', ['现实职业'], '服务业范围过宽，具体店员、餐饮、护理等职业继续保留原始标签。');
decide(['漫画创作题材'], 'story_engine', 'merge', ['创作活动'], '漫画制作是创作活动的具体媒介；投稿、分镜和编辑流程保留原始标签。');
decide(['现实职业'], 'world_frame', 'merge', ['现实职业'], '正式本体已经存在完全相同标签。');
decide(['关系边界协商'], 'relationship', 'merge', ['关系边界协商'], '正式本体已经存在完全相同标签。');
decide(['搭档关系'], 'relationship', 'merge', ['搭档关系'], '正式本体已经存在完全相同标签。');
decide(['现代怪谈'], 'world_frame', 'merge', ['现代怪谈'], '正式本体已经存在完全相同标签。');
decide(['反英雄身份'], 'narrative_position', 'merge', ['反英雄身份'], '正式本体已经存在完全相同标签。');
decide(['孤独处境'], 'conflict_source', 'merge', ['孤独处境'], '正式本体已经存在完全相同标签。');
decide(['潜伏谍报'], 'story_engine', 'merge', ['潜伏谍报'], '正式本体已经存在完全相同标签。');
decide(['轮换主角'], 'information_structure', 'merge', ['群像轮换视角'], '现有标签已经覆盖叙事中心在角色间轮换；接力式跨代差异保留原始标签。');
decide(['元叙事'], 'information_structure', 'merge', ['元叙事'], '正式本体已经存在完全相同标签。');
decide(['青春成长'], 'growth_mode', 'merge', ['人格成长', '青春酸甜'], '青春成长可由成长方向与青春基调两个正交标签表达。');
decide(['人宠双视角'], 'information_structure', 'merge', ['多视角POV', '动物视角'], '它是视角数量与漫画动物视角的组合，不需新增组合型标签。');
decide(['共同生活'], 'relationship', 'merge', ['共同生活'], '正式本体已经存在完全相同标签。');
decide(['后日谈'], 'pacing', 'merge', ['后日谈'], '正式本体已经存在完全相同标签。');
decide(['器物主角'], 'manga_form', 'merge', ['物品作为主角'], '漫画形式标签已能表达器物承担叙事中心；具体器灵、武器或载具由embodiment补充。');
decide(['佣兵军人'], 'profession', 'merge', ['佣兵军人'], '混合候选中的旧职业部分已存在；退役状态另行审核。');

// Defer:概念有用，但当前17类语义边界或样本支持不足。
decide(['漫画原创', '小说改编漫画', '游戏／媒体企划改编漫画'], 'provenance', 'defer', [], '这是作品生产来源，不是角色在世界内的provenance；应保留在source_material元数据，避免污染故事本体。');
decide(['成年主角', '女性主角', '中年主角'], 'narrative_position', 'defer', [], '年龄与性别很有用，但现有17类缺少正交主角档案轴；放入叙事位置会与职业和角色功能冲突。');
decide(['退役身份'], 'provenance', 'defer', [], '现有“退役后重新开始”“主动退休者”可覆盖多数样本；若未来需要区分自愿、强制与组织脱离再考虑新增。');
decide(['出版生产链'], 'story_engine', 'defer', [], '采访、排版、装订、发行具有玩法价值，但当前只有一条直接支持，先保留原始标签。');
decide(['微观生命主角'], 'embodiment', 'defer', [], '细胞尺度有独立价值，但只有一条作品支持；需更多菌群、细胞或器官社会样本确认边界。');
decide(['记忆主题'], 'information_structure', 'defer', [], '记忆是主题而非必然的信息结构；需要未来theme轴，不能误并入失忆、倒叙或未来记忆。');

// Reject:过宽或已有具体轴足以表达，加入不会提高生成可执行性。
decide(['成长叙事'], 'growth_mode', 'reject', [], '过于宽泛，无法判断人格、职业、团队或能力成长，加入本体不会产生可执行约束。');
decide(['非人主角'], 'embodiment', 'reject', [], '本体已有动物、魔物、器灵、AI等具体形态；上位总括词会抹平身体差异。');

const allowedDecisions = new Set(['add', 'merge', 'defer', 'reject']);
const records = [...aggregated.entries()].map(([canonicalTag, item]) => {
  const review = decisions.get(canonicalTag);
  if (!review) throw new Error(`Missing decision: ${canonicalTag}`);
  if (!categoryIds.has(review.proposed_category)) throw new Error(`Invalid category: ${canonicalTag}`);
  if (!allowedDecisions.has(review.decision)) throw new Error(`Invalid decision: ${canonicalTag}`);
  if (review.decision === 'merge' && review.merge_into.some((tag) => !existingTags.has(tag))) {
    throw new Error(`Unknown merge target: ${canonicalTag} -> ${review.merge_into.join(', ')}`);
  }
  return {
    canonical_tag: canonicalTag,
    proposed_category: review.proposed_category,
    supporting_raw_tags: [...item.rawTags.entries()]
      .map(([rawTag, frequency]) => ({ raw_tag: rawTag, frequency, regions: ['日本'] }))
      .sort((a, b) => b.frequency - a.frequency || a.raw_tag.localeCompare(b.raw_tag, 'zh-Hans-CN')),
    frequency: item.frequency,
    total_frequency: item.frequency,
    regions: ['日本'],
    decision: review.decision,
    merge_into: review.merge_into,
    rationale: review.rationale
  };
}).sort((a, b) => b.frequency - a.frequency || a.canonical_tag.localeCompare(b.canonical_tag, 'zh-Hans-CN'));

if (records.length !== decisions.size) {
  const unused = [...decisions.keys()].filter((tag) => !aggregated.has(tag));
  if (unused.length) throw new Error(`Unused decisions: ${unused.join(', ')}`);
}

fs.writeFileSync(
  path.join(base, 'ontology_candidate_review_manga.json'),
  `${JSON.stringify(records, null, 2)}\n`,
  'utf8'
);

console.log(JSON.stringify({
  candidates: records.length,
  decisions: records.reduce((out, row) => {
    out[row.decision] = (out[row.decision] || 0) + 1;
    return out;
  }, {})
}, null, 2));
