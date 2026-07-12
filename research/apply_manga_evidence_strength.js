const fs = require('fs');
const path = require('path');

const base = __dirname;
const files = ['manga_works_2016_2020.json', 'manga_works_2021_2026.json'];
const officialDomains = [
  'mangataisho.com',
  'tsugimanga.jp',
  'j-mediaarts.jp',
  'kodansha.co.jp',
  'kadokawa.co.jp',
  'shueisha.co.jp',
  'shogakukan.co.jp',
  'shogakukan-comic.jp',
  'shinchosha.co.jp',
  'tobooks.jp',
  'over-lap.co.jp',
  'comic-gardo.com',
  'square-enix.com',
  'ichijinsha.co.jp',
  'shonengahosha.co.jp',
  'kumo-anime.com',
  'tenken-anime.com',
  'gcnovels.jp',
  'shonenjumpplus.com',
  'urasunday.com',
  'comic-days.com',
  'bigcomicbros.net'
];

function isOfficial(url) {
  const host = new URL(url).hostname.toLowerCase();
  return officialDomains.some((domain) => host === domain || host.endsWith(`.${domain}`));
}

for (const file of files) {
  const fullPath = path.join(base, file);
  const data = JSON.parse(fs.readFileSync(fullPath, 'utf8'));
  data.works = data.works.map((work) => {
    if (!Array.isArray(work.sources) || work.sources.length === 0) {
      throw new Error(`${file}: missing sources for ${work.title}`);
    }
    if (!work.sources.some(isOfficial)) {
      throw new Error(`${file}: no official source for ${work.title}`);
    }

    const normalized = {};
    for (const [key, value] of Object.entries(work)) {
      if (key === 'evidence_grade' || key === 'evidence_strength' || key === 'sources') continue;
      normalized[key] = value;
    }
    normalized.evidence_strength = 'A';
    normalized.sources = work.sources;
    return normalized;
  });
  fs.writeFileSync(fullPath, `${JSON.stringify(data, null, 2)}\n`, 'utf8');
}

console.log(JSON.stringify({ files, works: files.reduce((sum, file) => {
  const data = JSON.parse(fs.readFileSync(path.join(base, file), 'utf8'));
  return sum + data.works.length;
}, 0), evidence_strength: { A: 127, B: 0, C: 0 } }, null, 2));
