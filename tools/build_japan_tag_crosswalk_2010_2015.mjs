import fs from 'node:fs';

const works = JSON.parse(fs.readFileSync('research/japan_works_2010_2015.json','utf8'));
const prior = JSON.parse(fs.readFileSync('research/japan_tag_crosswalk.json','utf8'));
const ontology = JSON.parse(fs.readFileSync('research/tag_ontology.json','utf8'));
const canonical = new Set(ontology.categories.flatMap(c => c.tags));
const covered = new Set(prior.map(x => x.raw_tag));
const freq = new Map();
for (const work of works) for (const tag of work.tags) if (!covered.has(tag)) freq.set(tag,(freq.get(tag)||0)+1);

// Only lossless or near-lossless aliases. Narrow narrative details intentionally remain raw.
const aliases = {
  '校园喜剧':['校园青春','喜剧'], '程序员':['程序员黑客'], '地下城':['地下城社会'],
  '都市怪异':['现代怪谈'], '都市推理':['现代都市','推理解谜'], '都市灾害':['现代都市','灾难求生'],
  '公路旅行':['公路旅行'], '古典音乐':['音乐题材'], '历史幻想':['架空历史'],
  '后启示录':['灾后新文明'], '机器人主角':['机器人仿生人'], '机械兵器':['机甲战争'],
  '记忆丧失':['失忆但不悬疑'], '架空昭和':['架空历史'], '军师':['参谋军师'],
  '军事SF':['近未来科幻','机甲战争'], '历史穿越':['历史穿越'], '魔王主角':['反英雄身份'],
  '尼特侦探':['侦探调查员'], '农业':['乡村田园'], '农业职业':['农民灵农'],
  '女性侦探':['侦探调查员'], '奇幻推理':['西式奇幻','推理解谜'], '骑士训练':['佣兵军人'],
  '日常推理':['日常谜题'], '商业金融':['商业金融'], '失忆':['失忆但不悬疑'],
  '推理':['推理解谜'], '网络调查':['侦探调查员'], '性别转换':['性别转换'],
  '兄妹关系':['兄弟姐妹'], '兄妹':['兄弟姐妹'], '药师':['药师炼丹'],
  '乙女游戏世界':['乙女游戏世界'], '异世界':['异世界幻想'], '异世界滞留':['游戏玩家困入世界'],
  '职业女性':['职业技术人员'], '自卫队':['佣兵军人'], '蜘蛛主角':['昆虫'],
  '现实家庭':['家庭生活'], '职业经营':['店主经营者'], '餐馆经营':['美食餐饮','店主经营者'],
  '古书店':['现实职业','店主经营者'], '打工':['平台劳动者'], '公共卫生':['医疗行业'],
  '工程技术':['工业制造'], '工程师主角':['工程维修'], '技术职业':['职业技术人员'],
  '制造研发':['工业制造'], '现代军事':['佣兵军人'], '国家建设':['领地经营'],
  '共同体经营':['势力经营'], '经济制度':['商业金融'], '经济改革':['商业金融'],
  '贵族家族':['贵族家族'], '时间重置':['时间回归'], '人格交换':['身体交换'],
  '不死者主角':['不死族'], '本地奇幻':['西式奇幻','本地土著'], '反向异世界':['异世界转移'],
  '防御职业':['治疗辅助'], '非人角色':['非人观察者'], '封闭群体':['封闭空间'],
  '科学都市':['近未来科幻'], '学院政治':['学院奇幻'], '时间加速':['时间操控'],
  '论坛小说':['论坛体'], '第一人称':['第一人称限制视角'], '多时间线':['多线并行'],
  '多种族群像':['多种族社会','群像交叉线'], '班级群像':['群像交叉线'],
  '边缘人群像':['群像交叉线'], '创作者群像':['作家创作者','群像交叉线'],
  '公会群像':['群像交叉线'], '常客群像':['群像交叉线'], '照料群像':['群像交叉线'],
  '五人群像':['群像交叉线'], '艺术家群像':['群像交叉线'], '群像战争':['群像交叉线'],
  '心理战':['智斗博弈'], '信息战':['智斗博弈'], '政治谈判':['政治博弈'],
  '规则战':['规则解谜'], '游戏规则':['规则解谜'], '无暴力规则':['规则解谜'],
  '游戏决胜':['智斗博弈'], '能力组合':['能力组合构筑'], '网络社区':['网络社群'],
  '制作':['工匠铁匠'], '料理':['厨师调酒师'], '暗恋':['暗恋单向'],
};

const out = [...freq.entries()].sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0],'zh-CN')).map(([raw_tag,frequency]) => {
  if (canonical.has(raw_tag)) return {raw_tag,frequency,canonical_tags:[raw_tag],action:'existing',rationale:'与当前 tag_ontology.json 中的标准标签完全一致。'};
  const mapped = aliases[raw_tag];
  if (mapped && mapped.every(x=>canonical.has(x))) return {raw_tag,frequency,canonical_tags:mapped,action:'alias',rationale:raw_tag === '机器人主角' ? '“机器人”明确描述主角的存在形态，安全归入身体轴“机器人仿生人”；不额外推断其意识技术必然属于人工智能。' : '可由当前本体中的既有维度近无损表达；未附加原标签没有明示的属性。'};
  return {raw_tag,frequency,canonical_tags:[],action:'keep_raw',rationale:'该标签包含作品专名、细粒度情境、主角性别／体型、评价或复合叙事含义；当前本体没有足够精确且安全的对应项，保留原始标签。'};
});

for (const x of out) {
  if (covered.has(x.raw_tag)) throw new Error(`already covered: ${x.raw_tag}`);
  if (!['existing','alias','keep_raw'].includes(x.action)) throw new Error(`action: ${x.raw_tag}`);
  if (!x.canonical_tags.every(t=>canonical.has(t))) throw new Error(`noncanonical: ${x.raw_tag}`);
  if (x.action === 'keep_raw' && x.canonical_tags.length) throw new Error(`keep_raw mapped: ${x.raw_tag}`);
  if (x.action !== 'keep_raw' && !x.canonical_tags.length) throw new Error(`empty mapping: ${x.raw_tag}`);
}
fs.writeFileSync('research/japan_tag_crosswalk_2010_2015.json',JSON.stringify(out,null,2)+'\n');
console.log({raw_tags:[...freq.values()].reduce((a,b)=>a+b,0),unique_missing:out.length,actions:out.reduce((o,x)=>(o[x.action]=(o[x.action]||0)+1,o),{})});
