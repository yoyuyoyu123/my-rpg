import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const htmlPath = path.join(root, 'wuji_v25_reviewed.html');
const dbPath = path.join(root, 'research', 'research_db.json');
const html = fs.readFileSync(htmlPath, 'utf8');
const db = JSON.parse(fs.readFileSync(dbPath, 'utf8'));

const compact = {
  schema_version: db.schema_version,
  built_at: db.built_at,
  coverage: db.coverage,
  ontology: db.ontology,
  works: db.works.map((w) => ({
    id: w.id,
    region: w.region,
    medium: w.medium,
    title: w.title,
    author: w.author,
    platform_or_publisher: w.platform_or_publisher,
    recognition_years: w.recognition_years,
    canonical_tags: w.canonical_tags,
    canonical_tags_by_category: w.canonical_tags_by_category,
    protagonist_role: w.protagonist_role,
    narrative_features: w.narrative_features,
    why_included: w.why_included,
    popularity_basis: (w.evidence || []).map((e) => e.popularity_basis).filter(Boolean).join('；'),
    evidence_strength: (w.evidence || []).map((e) => e.evidence_strength).filter(Boolean).sort()[0] || ''
  }))
};

const block = `// EMBEDDED_RESEARCH_DB_START\nvar EMBEDDED_RESEARCH_DB=${JSON.stringify(compact)};\n// EMBEDDED_RESEARCH_DB_END`;
const marker = '// ── RESEARCH TAG DB';
let next;
if (/\/\/ EMBEDDED_RESEARCH_DB_START[\s\S]*?\/\/ EMBEDDED_RESEARCH_DB_END/.test(html)) {
  next = html.replace(/\/\/ EMBEDDED_RESEARCH_DB_START[\s\S]*?\/\/ EMBEDDED_RESEARCH_DB_END/, block);
} else {
  const at = html.indexOf(marker);
  if (at < 0) throw new Error(`Marker not found: ${marker}`);
  next = html.slice(0, at) + block + '\n' + html.slice(at);
}
fs.writeFileSync(htmlPath, next, 'utf8');
console.log(JSON.stringify({ html_bytes: Buffer.byteLength(next), embedded_works: compact.works.length, categories: compact.ontology.categories.length }));
