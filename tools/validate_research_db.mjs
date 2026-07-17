import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const researchDir = path.join(root, 'research');
const files = fs.readdirSync(researchDir)
  .filter((name) => /(?:^|_)works(?:_|\.).*\.json$/i.test(name))
  .sort();

const required = ['year', 'title', 'author', 'tags', 'protagonist_role', 'narrative_features', 'why_included', 'sources', 'evidence_strength'];
const all = [];
const errors = [];
const warnings = [];

for (const name of files) {
  const filename = path.join(researchDir, name);
  let rows;
  try {
    rows = JSON.parse(fs.readFileSync(filename, 'utf8'));
  } catch (error) {
    errors.push(`${name}: JSON parse failed: ${error.message}`);
    continue;
  }
  if (!Array.isArray(rows) && Array.isArray(rows?.works)) rows = rows.works;
  if (!Array.isArray(rows)) {
    errors.push(`${name}: top-level value must be an array or contain a works array`);
    continue;
  }
  rows.forEach((row, index) => {
    for (const key of required) {
      if (row[key] == null || row[key] === '' || (Array.isArray(row[key]) && row[key].length === 0)) {
        errors.push(`${name}[${index}]: missing ${key}`);
      }
    }
    if (!Array.isArray(row.tags)) errors.push(`${name}[${index}]: tags must be an array`);
    if (!Array.isArray(row.sources)) errors.push(`${name}[${index}]: sources must be an array`);
    if (!['A', 'B', 'C'].includes(row.evidence_strength)) errors.push(`${name}[${index}]: evidence_strength must be A, B, or C`);
    const medium = name.startsWith('manga_') ? 'manga' : name.startsWith('japan_') ? 'novel_jp' : name.startsWith('china_') ? 'novel_cn' : 'unknown';
    all.push({ ...row, _source_file: name, _medium: medium });
  });
}

const seen = new Map();
for (const row of all) {
  const key = `${row._medium}\u0000${row.title}`.toLocaleLowerCase();
  if (seen.has(key)) warnings.push(`duplicate recognition record merged in master DB: ${row.title} (${seen.get(key)} / ${row._source_file})`);
  else seen.set(key, row._source_file);
}

const years = {};
const regions = {};
for (const row of all) {
  years[row.year] = (years[row.year] || 0) + 1;
  const region = row.region || 'unspecified';
  regions[region] = (regions[region] || 0) + 1;
}

const ontology = JSON.parse(fs.readFileSync(path.join(researchDir, 'tag_ontology.json'), 'utf8'));
const ontologyTags = new Set(ontology.categories.flatMap((category) => category.tags));
const crosswalkFiles = fs.readdirSync(researchDir).filter((name) => /_tag_crosswalk(?:_.*)?\.json$/i.test(name)).sort();
for (const name of crosswalkFiles) {
  const rows = JSON.parse(fs.readFileSync(path.join(researchDir, name), 'utf8'));
  const rawSeen = new Set();
  rows.forEach((row, index) => {
    if (!row.raw_tag || rawSeen.has(row.raw_tag)) errors.push(`${name}[${index}]: missing or duplicate raw_tag`);
    rawSeen.add(row.raw_tag);
    if (!Number.isInteger(row.frequency) || row.frequency < 1) errors.push(`${name}[${index}]: invalid frequency`);
    if (!['existing', 'alias', 'keep_raw'].includes(row.action)) errors.push(`${name}[${index}]: unresolved action ${row.action}`);
    if (!Array.isArray(row.canonical_tags)) errors.push(`${name}[${index}]: canonical_tags must be an array`);
    else for (const tag of row.canonical_tags) if (!ontologyTags.has(tag)) errors.push(`${name}[${index}]: unknown canonical tag ${tag}`);
    if (row.action === 'keep_raw' && row.canonical_tags?.length) errors.push(`${name}[${index}]: keep_raw must have no canonical tags`);
  });
}

console.log(JSON.stringify({ files, crosswalk_files: crosswalkFiles, works: all.length, years, regions, errors, warnings }, null, 2));
if (errors.length) process.exitCode = 1;
