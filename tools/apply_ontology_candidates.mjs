import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const dir = path.join(root, 'research');
const ontologyFile = path.join(dir, 'tag_ontology.json');
const reviewFile = path.join(dir, 'ontology_candidate_review_cn_jp.json');
const ontology = JSON.parse(fs.readFileSync(ontologyFile, 'utf8'));
const review = JSON.parse(fs.readFileSync(reviewFile, 'utf8'));
const categories = new Map(ontology.categories.map((category) => [category.id, category]));
const existing = new Map(ontology.categories.flatMap((category) => category.tags.map((tag) => [tag, category.id])));
const changes = [];

for (const item of review) {
  if (item.decision !== 'add') continue;
  const category = categories.get(item.proposed_category);
  if (!category) throw new Error(`Unknown category ${item.proposed_category} for ${item.canonical_tag}`);
  if (existing.has(item.canonical_tag)) {
    changes.push({ tag: item.canonical_tag, action: 'already_present', category: existing.get(item.canonical_tag) });
    continue;
  }
  category.tags.push(item.canonical_tag);
  existing.set(item.canonical_tag, category.id);
  changes.push({
    tag: item.canonical_tag,
    action: 'added',
    category: category.id,
    total_frequency: item.total_frequency,
    regions: item.regions,
    rationale: item.rationale
  });
}

ontology.version = '1.1.0';
ontology.updated_at = new Date().toISOString();
fs.writeFileSync(ontologyFile, `${JSON.stringify(ontology, null, 2)}\n`, 'utf8');
fs.writeFileSync(path.join(dir, 'ontology_change_log_cn_jp.json'), `${JSON.stringify(changes, null, 2)}\n`, 'utf8');
console.log(JSON.stringify({ added: changes.filter((item) => item.action === 'added').length, already_present: changes.filter((item) => item.action === 'already_present').length }, null, 2));
