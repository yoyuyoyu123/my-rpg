import fs from 'node:fs';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');

function extractFunction(name) {
  const start = html.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`missing function: ${name}`);
  const next = html.indexOf('\nfunction ', start + 10);
  if (next < 0) throw new Error(`cannot find function boundary: ${name}`);
  return html.slice(start, next).trim();
}

// Test the production analyzer instead of copying its warning rules.
const debugAnalyze = new Function(`${extractFunction('debugAnalyze')}\nreturn debugAnalyze;`)();

function entry(prompt) {
  return {
    before: {
      premise: { kind: 'transmigration' },
      premiseStage: { stage: 2 },
      storyDNA: '固定设定',
      storyDNAHash: 'same',
      lockedWorldTags: [],
      selectedResearchTags: [],
      tone: { name: '日常' },
    },
    after: {
      premise: { kind: 'transmigration' },
      storyDNAHash: 'same',
    },
    systemPrompt: `固定设定\n${prompt}`,
    reply: '普通场景。',
    signals: {},
  };
}

for (const marker of ['【穿越前提状态机】', '【跨世界迁移状态】', '【迁移进度事实】']) {
  const warnings = debugAnalyze(entry(marker));
  if (warnings.some((w) => w.code === 'PREMISE_DIRECTIVE_MISSING')) {
    throw new Error(`valid premise marker was rejected: ${marker}`);
  }
}

const missing = debugAnalyze(entry('没有迁移约束'));
if (!missing.some((w) => w.code === 'PREMISE_DIRECTIVE_MISSING' && w.severity === 'critical')) {
  throw new Error('missing premise directive was not reported as critical');
}

console.log('debug analyzer: premise directive compatibility passed');
