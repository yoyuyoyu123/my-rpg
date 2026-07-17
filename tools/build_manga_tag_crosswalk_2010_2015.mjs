import fs from 'node:fs';
const base=new URL('../research/',import.meta.url);
const works=JSON.parse(fs.readFileSync(new URL('manga_works_2010_2015.json',base),'utf8')).works;
const prior=JSON.parse(fs.readFileSync(new URL('manga_tag_crosswalk.json',base),'utf8'));
const ontology=JSON.parse(fs.readFileSync(new URL('tag_ontology.json',base),'utf8'));
const canonical=new Set(ontology.categories.flatMap(c=>c.tags));
const covered=new Set(prior.map(x=>x.raw_tag));
const frequency={}; for(const w of works) for(const t of w.tags) frequency[t]=(frequency[t]||0)+1;

// Only conservative semantic aliases. Unlisted fine-grained period, locale, motif and medium labels stay raw.
const aliases={
 '战争':['战争史诗'],'竞技':['体育竞技'],'日常':['日常占主导'],'不可靠叙事':['不可靠叙事者'],'登山':['体育竞技'],'第一人称':['第一人称叙事'],'非人':['亚人类'],'科幻短篇':['短篇闭环'],'丧尸':['末日求生'],'身体变形':['可变形生命'],'时间穿越':['历史穿越'],'团队':['团队协作'],'音乐':['音乐题材'],'自传':['第一人称叙事'],'都市':['现代都市'],'都市恋爱':['现代都市','恋爱主线'],'都市奇幻':['都市奇幻'],'创伤修复':['心理创伤','疗愈恢复'],'创作':['作家创作者'],'单恋':['单向暗恋'],'不死者':['不死族'],'超能力':['都市异能'],'成年人再出发':['完成冒险后的第二人生'],'出版业':['现实职业'],'传统音乐':['音乐题材'],'地方文化':['地方共同体'],'独居':['独居生活'],'法国革命':['历史正剧'],'复归':['疗愈恢复'],'古代史':['历史正剧'],'规则能力':['规则公开限制'],'航天':['硬科幻'],'航天学校':['科研学术','校园青春'],'伙伴':['团队协作'],'极限运动':['体育竞技'],'继承':['能力继承'],'寄居家庭':['拟制家庭'],'家族':['家族责任'],'剑客':['武侠江湖'],'教师':['教师'],'街机文化':['游戏世界'],'姐弟':['兄弟姐妹'],'姐妹':['兄弟姐妹'],'精神疾病':['心理疾病'],'救赎':['自我救赎'],'爵士':['音乐题材'],'科幻':['近未来科幻'],'恋爱':['恋爱主线'],'流行音乐':['音乐题材'],'漫画业界':['娱乐行业','作家创作者'],'魔法学徒':['学院奇幻'],'能力成长':['成长升级'],'农业学校':['校园青春','乡村田园'],'女性共同体':['女性群像'],'奇幻':['西式奇幻'],'骑士团':['佣兵军人'],'任务':['任务驱动'],'社会崩坏':['末日求生'],'社会排斥':['身份歧视'],'社交舞':['体育竞技'],'社区':['地方共同体'],'身份替代':['身份伪装'],'失忆':['失忆但不悬疑'],'师生':['师徒'],'时间停止':['时间静止'],'实验':['科研实验'],'食物伦理':['美食餐饮'],'视角反转':['身份反转'],'赎罪':['自我救赎'],'甜点职业':['美食餐饮','厨师调酒师'],'听障':['身体残障'],'王国':['西式奇幻'],'校园喜剧':['校园青春','轻喜剧'],'邪教':['宗教组织'],'悬疑':['谜题调查'],'压倒性力量':['开局无敌'],'医疗自传':['医疗行业','第一人称叙事'],'英雄学校':['超级英雄社会','校园青春'],'英雄组织':['超级英雄社会'],'幽灵':['幽灵'],'幽默':['轻喜剧'],'游戏制作':['现实职业','程序员黑客'],'御宅族':['御宅文化'],'战国':['历史正剧'],'职业':['现实职业'],'职业棒球':['体育竞技'],'职业竞技':['体育竞技'],'职业训练':['技能成长'],'职业主角':['职业技术人员'],'智谋':['智斗博弈'],'追捕':['逃亡追捕']
};
const forceKeep=new Set(['非人','科幻短篇','超能力','成年人再出发','航天','剑客','科幻','魔法学徒','骑士团','失忆','王国','游戏制作']);

Object.assign(aliases,{
 '职业训练':['职业专精','现实职业'],
 '秘密历史':['历史旧账'],
 '江户':['历史正剧'],
 '伪文献':['伪史料互文'],
 '中国战国':['历史正剧'],
 '失忆':['失忆叙事'],
 '生物改造':['生物朋克'],
 '校园喜剧':['校园青春','喜剧'],
 '医疗自传':['医疗行业']
});
forceKeep.delete('失忆');
// Explicit quality override: the legacy crosswalk kept 江户 raw, but this historical setting
// is safely represented by the existing broad world-frame tag and must override that row.
const overrideCovered=new Set(['江户']);

const rows=Object.entries(frequency).filter(([t])=>!covered.has(t)||overrideCovered.has(t)).map(([raw_tag,freq])=>{
 let tags,action,rationale;
 if(canonical.has(raw_tag)){tags=[raw_tag];action='existing';rationale='与当前 tag_ontology.json 中的规范标签完全一致。';}
 else if(!forceKeep.has(raw_tag)&&aliases[raw_tag]?.every(t=>canonical.has(t))){tags=aliases[raw_tag];action='alias';rationale='可在不引入额外情节假设的前提下归并到现有本体概念；原词仍保留更细粒度语义。';}
 else {tags=[];action='keep_raw';rationale='题材、地域、时代、媒介或表现手法过细，当前本体没有语义等价项；保留原词以避免过度推断。';}
 for(const t of tags) if(!canonical.has(t)) throw new Error(`canonical tag not in ontology: ${raw_tag} -> ${t}`);
 return {raw_tag,frequency:freq,canonical_tags:tags,action,rationale};
}).sort((a,b)=>b.frequency-a.frequency||a.raw_tag.localeCompare(b.raw_tag,'zh-CN'));

const out=new URL('manga_tag_crosswalk_2010_2015.json',base);
fs.writeFileSync(out,JSON.stringify(rows,null,2)+'\n','utf8');
console.log(JSON.stringify({rows:rows.length,existing:rows.filter(x=>x.action==='existing').length,alias:rows.filter(x=>x.action==='alias').length,keep_raw:rows.filter(x=>x.action==='keep_raw').length,total_frequency:rows.reduce((s,x)=>s+x.frequency,0)},null,2));
