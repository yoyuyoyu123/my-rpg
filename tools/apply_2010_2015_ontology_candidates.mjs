import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const dir = path.join(root, 'research');
const ontologyFile = path.join(dir, 'tag_ontology.json');
const crosswalkFile = path.join(dir, 'china_tag_crosswalk_2010_2015.json');
const ontology = JSON.parse(fs.readFileSync(ontologyFile, 'utf8'));
const crosswalk = JSON.parse(fs.readFileSync(crosswalkFile, 'utf8'));
const additions = [
  { raw: '史前幻想', canonical: '史前幻想', category: 'world_frame' },
  { raw: '部落', canonical: '部落社会', category: 'world_frame' },
  { raw: '图腾', canonical: '图腾信仰', category: 'story_engine' },
  { raw: '迁徙', canonical: '族群迁徙', category: 'story_engine' },
  { raw: '文明成长', canonical: '文明演进', category: 'story_engine' }
];

for (const item of additions) {
  const category = ontology.categories.find((entry) => entry.id === item.category);
  if (!category) throw new Error(`Unknown category: ${item.category}`);
  if (!ontology.categories.some((entry) => entry.tags.includes(item.canonical))) category.tags.push(item.canonical);
  const row = crosswalk.find((entry) => entry.raw_tag === item.raw);
  if (!row) throw new Error(`Missing crosswalk row: ${item.raw}`);
  row.canonical_tags = [item.canonical];
  row.action = item.raw === item.canonical ? 'existing' : 'alias';
  row.rationale = `${row.rationale} 本轮审查通过，正式纳入 ${item.category} 维度。`;
}

ontology.version = '1.3.0';
ontology.updated_at = new Date().toISOString();
fs.writeFileSync(ontologyFile, `${JSON.stringify(ontology, null, 2)}\n`, 'utf8');
fs.writeFileSync(crosswalkFile, `${JSON.stringify(crosswalk, null, 2)}\n`, 'utf8');
fs.writeFileSync(path.join(dir, 'ontology_change_log_2010_2015.json'), `${JSON.stringify(additions, null, 2)}\n`, 'utf8');
console.log(JSON.stringify({ added: additions.length, ontology_version: ontology.version }, null, 2));
