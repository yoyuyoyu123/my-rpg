import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const root = path.resolve(import.meta.dirname, '..');
const dir = path.join(root, 'research');
const readJson = (file) => JSON.parse(fs.readFileSync(file, 'utf8'));
const workFiles = fs.readdirSync(dir).filter((name) => /^(china|japan|manga)_works_.*\.json$/i.test(name)).sort();
const crosswalkFiles = fs.readdirSync(dir).filter((name) => /_tag_crosswalk\.json$/i.test(name)).sort();
const ontology = readJson(path.join(dir, 'tag_ontology.json'));

const canonicalTags = new Set(ontology.categories.flatMap((category) => category.tags));
const tagCategories = new Map();
for (const category of ontology.categories) for (const tag of category.tags) {
  if (!tagCategories.has(tag)) tagCategories.set(tag, []);
  tagCategories.get(tag).push(category.id);
}
const facetTags = (tags) => {
  const facets = {};
  for (const tag of tags) for (const category of tagCategories.get(tag) || []) {
    facets[category] ||= [];
    if (!facets[category].includes(tag)) facets[category].push(tag);
  }
  return facets;
};
const crosswalk = new Map();
const crosswalkEntries = [];
for (const name of crosswalkFiles) {
  const data = readJson(path.join(dir, name));
  const rows = Array.isArray(data) ? data : data.entries || data.crosswalk || [];
  for (const row of rows) {
    if (!row.raw_tag) continue;
    crosswalkEntries.push({ ...row, source_file: name });
    crosswalk.set(row.raw_tag, Array.isArray(row.canonical_tags) ? row.canonical_tags : []);
  }
}

const cleanTitle = (value) => String(value || '').normalize('NFKC').trim().toLocaleLowerCase();
const normalizeEvidenceStrength = (value) => {
  const text = String(value || '').trim().toUpperCase();
  if (text.startsWith('A')) return 'A';
  if (text.startsWith('B')) return 'B';
  if (text.startsWith('C')) return 'C';
  return 'ungraded';
};
const idFor = (medium, title) => `${medium}_${crypto.createHash('sha1').update(`${medium}\0${cleanTitle(title)}`).digest('hex').slice(0, 12)}`;
const fileMedium = (name) => name.startsWith('manga_') ? 'manga' : name.startsWith('japan_') ? 'light_or_web_novel' : 'web_novel';
const byKey = new Map();

for (const name of workFiles) {
  const parsed = readJson(path.join(dir, name));
  const rows = Array.isArray(parsed) ? parsed : parsed.works || [];
  const medium = fileMedium(name);
  for (const row of rows) {
    const key = `${medium}\0${cleanTitle(row.title)}`;
    const rawTags = [...new Set(row.tags || [])];
    const normalized = [...new Set(rawTags.flatMap((tag) => canonicalTags.has(tag) ? [tag] : crosswalk.get(tag) || []))];
    const sourceRecord = {
      recognition_year: row.year,
      source_file: name,
      popularity_basis: row.popularity_basis || '',
      evidence_strength: normalizeEvidenceStrength(row.evidence_strength),
      sources: row.sources || []
    };
    if (!byKey.has(key)) {
      byKey.set(key, {
        id: idFor(medium, row.title),
        region: row.region || (medium === 'web_novel' ? 'CN' : '日本'),
        medium,
        title: row.title,
        author: row.author,
        platform_or_publisher: row.platform_or_publisher || row.platform || '',
        source_type: row.source_type || (medium === 'manga' ? 'unknown' : 'original'),
        source_material: row.source_material || null,
        recognition_years: [row.year],
        raw_tags: rawTags,
        canonical_tags: normalized,
        canonical_tags_by_category: facetTags(normalized),
        protagonist_role: row.protagonist_role,
        narrative_features: row.narrative_features,
        why_included: row.why_included,
        evidence: [sourceRecord]
      });
    } else {
      const item = byKey.get(key);
      item.recognition_years = [...new Set([...item.recognition_years, row.year])].sort();
      item.raw_tags = [...new Set([...item.raw_tags, ...rawTags])];
      item.canonical_tags = [...new Set([...item.canonical_tags, ...normalized])];
      item.canonical_tags_by_category = facetTags(item.canonical_tags);
      item.evidence.push(sourceRecord);
    }
  }
}

const works = [...byKey.values()].sort((a, b) => Math.min(...a.recognition_years) - Math.min(...b.recognition_years) || a.title.localeCompare(b.title, 'zh-CN'));
const observedYears = works.flatMap((work) => work.recognition_years).filter(Number.isFinite);
const minYear = Math.min(...observedYears);
const maxYear = Math.max(...observedYears);
const rawTagFrequency = {};
for (const work of works) for (const tag of work.raw_tags) rawTagFrequency[tag] = (rawTagFrequency[tag] || 0) + 1;
const yearlyTagFrequency = {};
const mediumTagFrequency = {};
const evidenceStrengthFrequency = {};
const sourceDomainFrequency = {};
for (const work of works) {
  for (const year of work.recognition_years) {
    yearlyTagFrequency[year] ||= {};
    for (const tag of work.raw_tags) yearlyTagFrequency[year][tag] = (yearlyTagFrequency[year][tag] || 0) + 1;
  }
  mediumTagFrequency[work.medium] ||= {};
  for (const tag of work.raw_tags) mediumTagFrequency[work.medium][tag] = (mediumTagFrequency[work.medium][tag] || 0) + 1;
  for (const evidence of work.evidence) {
    const strength = evidence.evidence_strength;
    evidenceStrengthFrequency[strength] = (evidenceStrengthFrequency[strength] || 0) + 1;
    for (const source of evidence.sources) {
      try {
        const domain = new URL(source).hostname.replace(/^www\./, '');
        sourceDomainFrequency[domain] = (sourceDomainFrequency[domain] || 0) + 1;
      } catch {
        sourceDomainFrequency.invalid = (sourceDomainFrequency.invalid || 0) + 1;
      }
    }
  }
}

const database = {
  schema_version: '2.0.0',
  built_at: new Date().toISOString(),
  coverage: {
    period: `${minYear}-${maxYear}${maxYear === new Date().getUTCFullYear() ? 'YTD' : ''}`,
    raw_records: workFiles.reduce((count, name) => {
      const parsed = readJson(path.join(dir, name));
      return count + (Array.isArray(parsed) ? parsed.length : (parsed.works || []).length);
    }, 0),
    canonical_works: works.length,
    work_files: workFiles,
    crosswalk_files: crosswalkFiles
  },
  ontology,
  tag_crosswalk: crosswalkEntries,
  raw_tag_frequency: rawTagFrequency,
  yearly_raw_tag_frequency: yearlyTagFrequency,
  medium_raw_tag_frequency: mediumTagFrequency,
  evidence_strength_frequency: evidenceStrengthFrequency,
  source_domain_frequency: sourceDomainFrequency,
  works
};

fs.writeFileSync(path.join(dir, 'research_db.json'), `${JSON.stringify(database, null, 2)}\n`, 'utf8');
console.log(JSON.stringify(database.coverage, null, 2));
