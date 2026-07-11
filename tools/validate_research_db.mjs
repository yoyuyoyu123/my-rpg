import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const researchDir = path.join(root, 'research');
const files = fs.readdirSync(researchDir)
  .filter((name) => /(?:^|_)works(?:_|\.).*\.json$/i.test(name))
  .sort();

const required = ['year', 'title', 'author', 'tags', 'protagonist_role', 'narrative_features', 'why_included', 'sources'];
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
    const medium = name.startsWith('manga_') ? 'manga' : name.startsWith('japan_') ? 'novel_jp' : name.startsWith('china_') ? 'novel_cn' : 'unknown';
    all.push({ ...row, _source_file: name, _medium: medium });
  });
}

const seen = new Map();
for (const row of all) {
  const key = `${row._medium}\u0000${row.title}`.toLocaleLowerCase();
  if (seen.has(key)) warnings.push(`cross-file duplicate merged in master DB: ${row.title} (${seen.get(key)} / ${row._source_file})`);
  else seen.set(key, row._source_file);
}

const years = {};
const regions = {};
for (const row of all) {
  years[row.year] = (years[row.year] || 0) + 1;
  const region = row.region || 'unspecified';
  regions[region] = (regions[region] || 0) + 1;
}

console.log(JSON.stringify({ files, works: all.length, years, regions, errors, warnings }, null, 2));
if (errors.length) process.exitCode = 1;
