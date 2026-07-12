import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const dir = path.join(root, 'research');
const ontologyFile = path.join(dir, 'tag_ontology.json');
const ontology = JSON.parse(fs.readFileSync(ontologyFile, 'utf8'));
const categoryMap = new Map(ontology.categories.map((category) => [category.id, category]));
const reviewFiles = ['ontology_candidate_review_cn_jp.json', 'ontology_candidate_review_manga.json'];
const decisions = new Map();
const changeLog = [];

for (const name of reviewFiles) {
  const rows = JSON.parse(fs.readFileSync(path.join(dir, name), 'utf8'));
  for (const row of rows) {
    const previous = decisions.get(row.canonical_tag);
    if (!previous || previous.decision !== 'add') decisions.set(row.canonical_tag, row);
    if (row.decision === 'add') {
      const category = categoryMap.get(row.proposed_category);
      if (!category) throw new Error(`Unknown category ${row.proposed_category}`);
      if (!ontology.categories.some((item) => item.tags.includes(row.canonical_tag))) {
        category.tags.push(row.canonical_tag);
        changeLog.push({ tag: row.canonical_tag, action: 'added', category: category.id, source_review: name });
      }
    }
  }
}

const ontologyTags = new Set(ontology.categories.flatMap((category) => category.tags));
const crosswalkFiles = ['china_tag_crosswalk.json', 'japan_tag_crosswalk.json', 'manga_tag_crosswalk.json'];
for (const name of crosswalkFiles) {
  const file = path.join(dir, name);
  const rows = JSON.parse(fs.readFileSync(file, 'utf8'));
  for (const row of rows) {
    const mapped = [];
    for (const tag of row.canonical_tags || []) {
      const review = decisions.get(tag);
      if (!review || review.decision === 'add') mapped.push(tag);
      else if (review.decision === 'merge') mapped.push(...(review.merge_into || []));
    }
    row.canonical_tags = [...new Set(mapped)].filter((tag) => ontologyTags.has(tag));
    if (!row.canonical_tags.length) row.action = 'keep_raw';
    else if (row.canonical_tags.length === 1 && row.canonical_tags[0] === row.raw_tag) row.action = 'existing';
    else row.action = 'alias';
  }
  fs.writeFileSync(file, `${JSON.stringify(rows, null, 2)}\n`, 'utf8');
}

ontology.version = '1.2.0';
ontology.updated_at = new Date().toISOString();
fs.writeFileSync(ontologyFile, `${JSON.stringify(ontology, null, 2)}\n`, 'utf8');
fs.writeFileSync(path.join(dir, 'ontology_change_log_final.json'), `${JSON.stringify(changeLog, null, 2)}\n`, 'utf8');
console.log(JSON.stringify({ newly_added: changeLog.length, ontology_tags: ontologyTags.size }, null, 2));
