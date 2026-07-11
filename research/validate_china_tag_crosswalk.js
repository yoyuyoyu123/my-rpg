const fs = require('fs');
const path = require('path');

const researchDir = __dirname;
const sourceFiles = [
  'china_works_2016_2020.json',
  'china_works_2021_2024.json',
  'china_works_2025_2026.json'
];

function readJson(name) {
  return JSON.parse(fs.readFileSync(path.join(researchDir, name), 'utf8'));
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const works = sourceFiles.flatMap(readJson);
const ontology = readJson('tag_ontology.json');
const crosswalk = readJson('china_tag_crosswalk.json');
const trends = fs.readFileSync(path.join(researchDir, 'china_tag_trends_2016_2026.md'), 'utf8');

const rawFrequency = new Map();
for (const work of works) {
  assert(Array.isArray(work.tags), `Missing tags array on work: ${work.title || work.id || 'unknown'}`);
  for (const tag of work.tags) rawFrequency.set(tag, (rawFrequency.get(tag) || 0) + 1);
}

const canonical = new Set(
  ontology.categories.flatMap((category) => category.tags)
);
const expectedKeys = ['raw_tag', 'frequency', 'canonical_tags', 'action', 'rationale'];
const allowedActions = new Set(['existing', 'alias', 'new_candidate', 'keep_raw']);
const seen = new Set();
const actionCounts = Object.fromEntries([...allowedActions].map((action) => [action, 0]));
const proposedCanonical = new Set();

assert(Array.isArray(crosswalk), 'Crosswalk must be an array.');
assert(crosswalk.length === rawFrequency.size, 'Crosswalk/raw-tag cardinality mismatch.');

for (const entry of crosswalk) {
  assert(JSON.stringify(Object.keys(entry)) === JSON.stringify(expectedKeys),
    `Unexpected entry keys/order: ${entry.raw_tag}`);
  assert(!seen.has(entry.raw_tag), `Duplicate raw tag: ${entry.raw_tag}`);
  seen.add(entry.raw_tag);
  assert(rawFrequency.has(entry.raw_tag), `Unknown raw tag: ${entry.raw_tag}`);
  assert(entry.frequency === rawFrequency.get(entry.raw_tag), `Frequency mismatch: ${entry.raw_tag}`);
  assert(Number.isInteger(entry.frequency) && entry.frequency > 0, `Invalid frequency: ${entry.raw_tag}`);
  assert(Array.isArray(entry.canonical_tags), `canonical_tags must be an array: ${entry.raw_tag}`);
  assert(allowedActions.has(entry.action), `Invalid action: ${entry.raw_tag}`);
  assert(typeof entry.rationale === 'string' && entry.rationale.trim().length > 0,
    `Missing rationale: ${entry.raw_tag}`);
  assert(new Set(entry.canonical_tags).size === entry.canonical_tags.length,
    `Duplicate canonical target: ${entry.raw_tag}`);
  actionCounts[entry.action] += 1;

  if (entry.action === 'existing') {
    assert(entry.canonical_tags.length === 1 && entry.canonical_tags[0] === entry.raw_tag,
      `Existing tag is not an identity map: ${entry.raw_tag}`);
    assert(canonical.has(entry.raw_tag), `Existing tag absent from ontology: ${entry.raw_tag}`);
  } else if (entry.action === 'alias') {
    assert(entry.canonical_tags.length > 0, `Alias has no target: ${entry.raw_tag}`);
    assert(entry.canonical_tags.every((tag) => canonical.has(tag)),
      `Alias points outside ontology: ${entry.raw_tag}`);
  } else if (entry.action === 'new_candidate') {
    assert(entry.canonical_tags.length > 0, `Candidate has no proposed target: ${entry.raw_tag}`);
    assert(entry.canonical_tags.some((tag) => !canonical.has(tag)),
      `Candidate contains no genuinely new target: ${entry.raw_tag}`);
    for (const tag of entry.canonical_tags) {
      if (!canonical.has(tag)) proposedCanonical.add(tag);
    }
  } else {
    assert(entry.canonical_tags.length === 0, `keep_raw unexpectedly maps a target: ${entry.raw_tag}`);
  }
}

for (const rawTag of rawFrequency.keys()) {
  assert(seen.has(rawTag), `Missing raw tag: ${rawTag}`);
}

const assignments = [...rawFrequency.values()].reduce((sum, value) => sum + value, 0);
assert(works.length === 125, `Unexpected work count: ${works.length}`);
assert(assignments === 747, `Unexpected assignment count: ${assignments}`);
assert(rawFrequency.size === 566, `Unexpected unique raw-tag count: ${rawFrequency.size}`);
assert(JSON.stringify(actionCounts) === JSON.stringify({
  existing: 114,
  alias: 304,
  new_candidate: 62,
  keep_raw: 86
}), `Unexpected action distribution: ${JSON.stringify(actionCounts)}`);
assert(proposedCanonical.size === 27,
  `Unexpected unique candidate count: ${proposedCanonical.size}`);
assert(trends.includes('对应 27 个候选概念'), 'Trend report does not state the exact candidate count.');
for (const tag of proposedCanonical) {
  assert(trends.includes(tag), `Candidate absent from trend report: ${tag}`);
}

console.log(JSON.stringify({
  ok: true,
  source_files: sourceFiles.length,
  works: works.length,
  assignments,
  unique_raw_tags: rawFrequency.size,
  ontology_tags: canonical.size,
  crosswalk_entries: crosswalk.length,
  action_counts: actionCounts,
  unique_new_candidates: proposedCanonical.size,
  report_bytes: Buffer.byteLength(trends, 'utf8')
}, null, 2));
