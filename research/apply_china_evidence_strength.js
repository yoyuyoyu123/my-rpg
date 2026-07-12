const fs = require('fs');
const path = require('path');

const researchDir = __dirname;
const sourceFiles = [
  'china_works_2016_2020.json',
  'china_works_2021_2024.json',
  'china_works_2025_2026.json'
];

// B records rely on a platform/authoritative-media discussion or an early dynamic
// signal, rather than a formal annual list, blue book, or directly documented
// official work-page milestone. The sole C record relies on a platform keyword
// aggregation page plus a weak secondary adaptation listing.
const gradeB = new Set([
  '2016|一念永恒',
  '2016|修真聊天群',
  '2025|非赢游戏',
  '2026|临圣',
  '2026|爸妈来自外星球'
]);
const gradeC = new Set([
  '2020|开局地摊卖大力'
]);

function keyOf(work) {
  return `${work.year}|${work.title}`;
}

function expectedGrade(work) {
  const key = keyOf(work);
  if (gradeC.has(key)) return 'C';
  if (gradeB.has(key)) return 'B';
  return 'A';
}

function withoutEvidence(works) {
  return works.map((work) => {
    const clone = JSON.parse(JSON.stringify(work));
    delete clone.evidence_strength;
    return clone;
  });
}

const totals = { A: 0, B: 0, C: 0, inserted: 0, preserved: 0 };

for (const fileName of sourceFiles) {
  const filePath = path.join(researchDir, fileName);
  const originalText = fs.readFileSync(filePath, 'utf8');
  const newline = originalText.includes('\r\n') ? '\r\n' : '\n';
  const originalWorks = JSON.parse(originalText);
  const semanticBaseline = JSON.stringify(withoutEvidence(originalWorks));
  let editedText = originalText;
  let cursor = 0;

  for (const work of originalWorks) {
    const grade = expectedGrade(work);
    totals[grade] += 1;

    const titleAt = editedText.indexOf('"title"', cursor);
    if (titleAt < 0) throw new Error(`Cannot locate title key: ${keyOf(work)}`);
    const titleValueAt = editedText.indexOf(JSON.stringify(work.title), titleAt + 7);
    if (titleValueAt < 0) throw new Error(`Cannot locate title value: ${keyOf(work)}`);

    let sourcesAt = editedText.indexOf('"sources"', titleValueAt + work.title.length);
    if (sourcesAt < 0) throw new Error(`Cannot locate sources key: ${keyOf(work)}`);

    const beforeSources = editedText.slice(titleAt, sourcesAt);
    const evidenceMatch = beforeSources.match(/"evidence_strength"\s*:\s*"([ABC])"\s*,?\s*$/);
    if (evidenceMatch) {
      if (evidenceMatch[1] !== grade) {
        throw new Error(`Existing grade mismatch for ${keyOf(work)}: ${evidenceMatch[1]} != ${grade}`);
      }
      totals.preserved += 1;
    } else {
      const lineStart = editedText.lastIndexOf('\n', sourcesAt - 1) + 1;
      const prefix = editedText.slice(lineStart, sourcesAt);
      if (/^\s*$/.test(prefix)) {
        const insertion = `${prefix}"evidence_strength": "${grade}",${newline}`;
        editedText = editedText.slice(0, lineStart) + insertion + editedText.slice(lineStart);
        sourcesAt += insertion.length;
      } else {
        const insertion = `"evidence_strength":"${grade}",`;
        editedText = editedText.slice(0, sourcesAt) + insertion + editedText.slice(sourcesAt);
        sourcesAt += insertion.length;
      }
      totals.inserted += 1;
    }
    cursor = sourcesAt + 1;
  }

  const editedWorks = JSON.parse(editedText);
  if (JSON.stringify(withoutEvidence(editedWorks)) !== semanticBaseline) {
    throw new Error(`Non-evidence content changed in ${fileName}`);
  }
  if (editedWorks.some((work) => work.evidence_strength !== expectedGrade(work))) {
    throw new Error(`Evidence grade validation failed in ${fileName}`);
  }

  fs.writeFileSync(filePath, editedText, 'utf8');
}

if (totals.A !== 119 || totals.B !== 5 || totals.C !== 1 ||
    totals.inserted + totals.preserved !== 125) {
  throw new Error(`Unexpected totals: ${JSON.stringify(totals)}`);
}

console.log(JSON.stringify({ ok: true, ...totals }, null, 2));
