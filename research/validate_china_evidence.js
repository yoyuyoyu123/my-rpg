const fs = require('fs');
const path = require('path');

const researchDir = __dirname;
const sourceFiles = [
  'china_works_2016_2020.json',
  'china_works_2021_2024.json',
  'china_works_2025_2026.json'
];
const expectedFileCounts = [53, 44, 28];
const expectedB = new Set([
  '2016|一念永恒',
  '2016|修真聊天群',
  '2025|非赢游戏',
  '2026|临圣',
  '2026|爸妈来自外星球'
]);
const expectedC = new Set(['2020|开局地摊卖大力']);
const allowedHosts = new Set([
  'www.chinawriter.com.cn',
  'wyb.chinawriter.com.cn',
  'image.chinawriter.com.cn',
  'www.jjwxc.net',
  'm.jjwxc.net',
  'm.jjwxc.com',
  'static.jjwxc.net',
  'book.qidian.com',
  'www.qidian.com',
  'www.cssn.cn',
  'www.xinhuanet.com',
  'fanqienovel.com',
  'www.shuqi.com',
  'pdf.dfcfw.com',
  'www.sohu.com',
  'm.thepaper.cn',
  'bgm.tv'
]);

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function keyOf(work) {
  return `${work.year}|${work.title}`;
}

function expectedGrade(work) {
  const key = keyOf(work);
  if (expectedC.has(key)) return 'C';
  if (expectedB.has(key)) return 'B';
  return 'A';
}

function isStrongDirectHost(host) {
  return host.endsWith('.chinawriter.com.cn') ||
    host === 'www.jjwxc.net' || host === 'm.jjwxc.net' || host === 'm.jjwxc.com' ||
    host === 'book.qidian.com' || host === 'www.qidian.com' ||
    host === 'www.cssn.cn' || host === 'www.xinhuanet.com';
}

const totals = { A: 0, B: 0, C: 0 };
const seen = new Set();
let totalWorks = 0;
let totalSources = 0;

sourceFiles.forEach((fileName, fileIndex) => {
  const filePath = path.join(researchDir, fileName);
  const works = JSON.parse(fs.readFileSync(filePath, 'utf8'));
  assert(Array.isArray(works), `${fileName} must contain an array.`);
  assert(works.length === expectedFileCounts[fileIndex],
    `${fileName} work count changed: ${works.length}`);

  for (const work of works) {
    totalWorks += 1;
    const key = keyOf(work);
    assert(!seen.has(key), `Duplicate year/title key: ${key}`);
    seen.add(key);
    assert(['A', 'B', 'C'].includes(work.evidence_strength), `Invalid grade: ${key}`);
    assert(work.evidence_strength === expectedGrade(work), `Unexpected grade: ${key}`);
    totals[work.evidence_strength] += 1;

    const keys = Object.keys(work);
    assert(keys.indexOf('evidence_strength') === keys.indexOf('sources') - 1,
      `evidence_strength must immediately precede sources: ${key}`);
    assert(typeof work.popularity_basis === 'string' && work.popularity_basis.trim().length >= 4,
      `Insufficient popularity_basis: ${key}`);
    assert(Array.isArray(work.sources) && work.sources.length > 0, `Missing sources: ${key}`);
    assert(new Set(work.sources).size === work.sources.length, `Duplicate source URL: ${key}`);

    const hosts = [];
    for (const source of work.sources) {
      let url;
      try { url = new URL(source); } catch { throw new Error(`Invalid source URL: ${key}`); }
      assert(url.protocol === 'https:', `Non-HTTPS source URL: ${key}`);
      assert(allowedHosts.has(url.hostname), `Unreviewed source host ${url.hostname}: ${key}`);
      hosts.push(url.hostname);
      totalSources += 1;
    }
    if (work.evidence_strength === 'A') {
      assert(hosts.some(isStrongDirectHost), `A record lacks a strong direct/official source: ${key}`);
    }
  }
});

assert(totalWorks === 125, `Total work count changed: ${totalWorks}`);
assert(totals.A === 119 && totals.B === 5 && totals.C === 1,
  `Unexpected grade totals: ${JSON.stringify(totals)}`);
assert([...expectedB].every((key) => seen.has(key)), 'Expected B record is missing.');
assert([...expectedC].every((key) => seen.has(key)), 'Expected C record is missing.');

console.log(JSON.stringify({
  ok: true,
  files: sourceFiles.length,
  works: totalWorks,
  sources: totalSources,
  evidence_strength: totals,
  b_records: [...expectedB],
  c_records: [...expectedC]
}, null, 2));
