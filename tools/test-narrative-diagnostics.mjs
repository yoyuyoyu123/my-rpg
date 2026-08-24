import fs from 'node:fs';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const fixture = JSON.parse(
  fs.readFileSync(new URL('../research/regression/fixtures/narrative_diagnostic_cases.json', import.meta.url), 'utf8'),
);

function extractFunction(name) {
  const start = html.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`missing function: ${name}`);
  const next = html.indexOf('\nfunction ', start + 10);
  if (next < 0) throw new Error(`cannot find function boundary: ${name}`);
  return html.slice(start, next).trim();
}

// Execute the production signal extractor and analyzer against sanitized fixtures.
const debugSignals = new Function(`${extractFunction('debugSignals')}\nreturn debugSignals;`)();
const debugAnalyze = new Function(`${extractFunction('debugAnalyze')}\nreturn debugAnalyze;`)();

for (const test of fixture.cases) {
  const storyDNA = '固定的脱敏测试设定';
  const entry = {
    input: test.input,
    signals: debugSignals(test.input),
    before: {
      premise: { kind: 'transmigration' },
      premiseStage: { stage: 1 },
      storyDNA,
      storyDNAHash: 'stable',
      lockedWorldTags: [],
      selectedResearchTags: [],
      tone: { name: test.tone, description: test.tone, informationMode: '信息直接' },
    },
    after: { premise: { kind: 'transmigration' }, storyDNAHash: 'stable' },
    systemPrompt: `${storyDNA}\n【迁移进度事实】当前=入口逼近`,
    reply: test.reply,
  };
  const actual = debugAnalyze(entry).map((warning) => warning.code);
  for (const code of test.expectedCodes) {
    if (!actual.includes(code)) throw new Error(`${test.id}: expected ${code}, got ${actual.join(',') || 'none'}`);
  }
  for (const code of test.forbiddenCodes) {
    if (actual.includes(code)) throw new Error(`${test.id}: unexpected ${code}`);
  }
}

console.log(`narrative diagnostics: ${fixture.cases.length} sanitized cases passed`);
