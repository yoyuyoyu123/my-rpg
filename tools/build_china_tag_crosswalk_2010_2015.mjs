import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const read = name => JSON.parse(fs.readFileSync(path.join(root, 'research', name), 'utf8'));
const works = read('china_works_2010_2015.json');
const old = read('china_tag_crosswalk.json');
const ontology = read('tag_ontology.json');
const canonical = new Set(ontology.categories.flatMap(c => c.tags));
const covered = new Set(old.map(x => x.raw_tag));
const freq = new Map();
for (const work of works) for (const tag of work.tags) freq.set(tag, (freq.get(tag) || 0) + 1);

// Only high-confidence aliases are declared. Composite mappings are used only when
// every component is directly expressed by the raw tag; everything else stays raw.
const aliases = {
  '官场':['朝堂官场'], '升级':['境界升级'], '单元故事':['单元剧'],
  '电竞':['体育竞技'], '都市仙侠':['现代修仙'], '都市现实':['现代都市'],
  '都市异术':['都市异能'],
  '江湖':['武侠江湖'], '领地经营':['领主经营'], '西方奇幻':['西式奇幻'],
  '仙侠喜剧':['古典仙侠','喜剧'],
  '搭档':['搭档关系'], '都市幻想':['都市奇幻'], '都市日常':['现代都市','日常占主导'],
  '都市职业':['现实职业'], '多时空':['多时空并置'], '多世界':['多元宇宙'],
  '反职业配置':['反套路流'], '工业建设':['工业建设'],
  '关系修复':['关系成长'],
  '家书':['书信日记'],
  '家宅经营':['内政治理'], '军旅':['佣兵军人'],
  '科学史':['科研学术'], '炼药':['药师炼丹'], '轮回任务':['无限流'],
  '猫':['动物'], '梦境':['梦境穿行'], '末日':['末日求生'],
  '谋士':['参谋军师'], '女性事业':['女性事业线'],
  '女性户主':['女性事业线'],
  '日常喜剧':['日常占主导','喜剧'], '商业':['商业金融'],
  '社区群像':['社区居民','群像交叉线'], '身份扮演':['马甲身份'],
  '失忆':['失忆叙事'],
  '探险悬疑':['谜题调查','冒险占主导'],
  '穿越':['历史穿越'],
  '退役重返':['退役后重新开始'], '网游':['游戏世界'], '位面战争':['跨世界诸天','战争局势'],
  '文明冲突':['价值观冲突'], '误入社群':['聊天群'],
  '仙侠言情':['古典仙侠','恋爱要素'], '乡土':['乡村田园'],
  '虚拟网游':['MMO世界'],
  '悬疑调查':['谜题调查'],
  '战争伦理':['战争局势','关系伦理灰度'],
  '职业搭档':['职业搭档'], '职业战队':['竞技联赛','团队成长'],
  '制度治理':['内政治理']
};

const newCandidates = {
  '史前幻想':'建议新增“史前幻想”世界框架标签；当前本体中的历史、异世界、末日或公路旅行均会改变原义。',
  '部落':'建议新增“部落社会”社会结构标签；“多种族社会”不能等价表达部落组织。',
  '图腾':'建议新增“图腾信仰”能力或文化体系标签；现有香火神道与传统文化能力体系均不完全等价。',
  '迁徙':'建议新增“族群迁徙”剧情机制标签；公路旅行偏向旅行体验，无法安全替代生存性迁徙。',
  '文明成长':'建议新增“文明演进”成长机制标签；城市建设、工业建设或灾后新文明都比原义更窄。'
};

const output = [...freq]
  .filter(([tag]) => !covered.has(tag))
  .sort((a,b) => b[1]-a[1] || a[0].localeCompare(b[0], 'zh-CN'))
  .map(([raw_tag, frequency]) => {
    if (canonical.has(raw_tag)) return {raw_tag, frequency, canonical_tags:[raw_tag], action:'existing', rationale:'与当前标签本体中的规范标签完全一致。'};
    const mapped = aliases[raw_tag];
    if (mapped && mapped.every(x => canonical.has(x))) return {raw_tag, frequency, canonical_tags:mapped, action:'alias', rationale:'原标签语义可由现有本体标签直接、无额外推断地表达。'};
    if (newCandidates[raw_tag]) return {raw_tag, frequency, canonical_tags:[], action:'new_candidate', rationale:newCandidates[raw_tag]};
    return {raw_tag, frequency, canonical_tags:[], action:'keep_raw', rationale:'当前本体没有足够精确的等价标签；为避免扩大、缩窄或误改原义，保留原标签。'};
  });

fs.writeFileSync(path.join(root,'research','china_tag_crosswalk_2010_2015.json'), JSON.stringify(output,null,2)+'\n','utf8');
console.log(`wrote ${output.length} uncovered raw tags`);
