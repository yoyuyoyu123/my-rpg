const fs = require('fs');
const path = require('path');

const base = __dirname;
const files = [
  'japan_works_2016_2020.json',
  'japan_works_2021_2026.json'
];

const directOfficialHosts = new Set([
  'tsugirano.jp',
  'kakuyomu.jp',
  'www.kadokawa.co.jp',
  'www.ichijinsha.co.jp',
  'dengekibunko.jp'
]);

const dynamicHosts = new Set([
  'yomou.syosetu.com'
]);

function grade(record) {
  const hosts = (record.sources || []).map((source) => new URL(source).hostname);
  if (hosts.some((host) => directOfficialHosts.has(host))) return 'A';
  if (hosts.length > 0 && hosts.every((host) => dynamicHosts.has(host))) return 'C';
  return 'B';
}

const summary = {};
for (const file of files) {
  const fullPath = path.join(base, file);
  const rows = JSON.parse(fs.readFileSync(fullPath, 'utf8'));
  const counts = { A: 0, B: 0, C: 0 };
  for (const row of rows) {
    row.evidence_strength = grade(row);
    counts[row.evidence_strength] += 1;
  }
  fs.writeFileSync(fullPath, `${JSON.stringify(rows, null, 2)}\n`, 'utf8');
  summary[file] = { records: rows.length, ...counts };
}

console.log(JSON.stringify(summary, null, 2));
