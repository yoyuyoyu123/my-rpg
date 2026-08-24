import fs from 'node:fs';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');

function extractFunction(name) {
  const start = html.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`missing function: ${name}`);
  const next = html.indexOf('\nfunction ', start + 10);
  if (next < 0) throw new Error(`cannot find function boundary: ${name}`);
  return html.slice(start, next).trim();
}

// Evaluate the production parser itself instead of maintaining a duplicate.
const parseActionOptions = new Function(
  `${extractFunction('cleanOptionMarkdown')}\n${extractFunction('parseActionOptions')}\nreturn parseActionOptions;`,
)();

const cases = [
  {
    name: 'legacy plain format',
    text: '正文。\n\n选项：\n1 询问店主\n2 离开店铺\n3 原地观察\n或输入任何你想做的事',
    expected: ['询问店主', '离开店铺', '原地观察'],
  },
  {
    name: 'markdown bracket heading and parenthesized numbers',
    text: '正文。\n\n**【行动选项】**\n1) 敲门\n2) 绕到屋后\n3) 暂时离开\n自由输入',
    expected: ['敲门', '绕到屋后', '暂时离开'],
  },
  {
    name: 'heading-free final circled list',
    text: '正文最后一句。\n① 向左走\n② 向右走\n③ 留在原地',
    expected: ['向左走', '向右走', '留在原地'],
  },
  {
    name: 'full-width numbers and markdown heading',
    text: '正文。\n### 行动参考\n１、和她谈谈\n２、查看地图',
    expected: ['和她谈谈', '查看地图'],
  },
];

for (const test of cases) {
  const parsed = parseActionOptions(test.text);
  const actual = parsed.opts.map((option) => option.t);
  if (!parsed.found || JSON.stringify(actual) !== JSON.stringify(test.expected)) {
    throw new Error(`${test.name}: expected ${JSON.stringify(test.expected)}, got ${JSON.stringify(actual)}`);
  }
}

const bodyList = parseActionOptions('正文：\n1 第一条说明\n2 第二条说明\n\n这里还有后续正文，不是选项。');
if (bodyList.found) throw new Error('ordinary numbered body list was misclassified as action options');

console.log(`option parser: ${cases.length + 1} cases passed`);
