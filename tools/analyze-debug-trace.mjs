import fs from 'node:fs';
import path from 'node:path';

const target = process.argv[2];
if (!target) {
  console.error('Usage: node tools/analyze-debug-trace.mjs <myrpg_debug.json>');
  process.exit(2);
}

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');

function extractFunction(name) {
  const start = html.indexOf(`function ${name}(`);
  if (start < 0) throw new Error(`missing function: ${name}`);
  const next = html.indexOf('\nfunction ', start + 10);
  if (next < 0) throw new Error(`cannot find function boundary: ${name}`);
  return html.slice(start, next).trim();
}

const debugAnalyze = new Function(`${extractFunction('debugAnalyze')}\nreturn debugAnalyze;`)();
const parseActionOptions = new Function(
  `${extractFunction('cleanOptionMarkdown')}\n${extractFunction('parseActionOptions')}\nreturn parseActionOptions;`,
)();

const payload = JSON.parse(fs.readFileSync(path.resolve(target), 'utf8'));
if (payload.format !== 'wuji-debug-trace' || !Array.isArray(payload.logs)) {
  throw new Error('not a wuji-debug-trace export');
}

const codeCounts = {};
const rows = [];
for (const log of payload.logs) {
  const recomputed = debugAnalyze(log);
  for (const warning of recomputed) {
    codeCounts[warning.code] = (codeCounts[warning.code] || 0) + 1;
  }
  const reply = String(log.reply || '');
  const options = parseActionOptions(reply);
  rows.push({
    turn: Number(log.turn) || 0,
    status: String(log.status || ''),
    durationMs: Number(log.durationMs) || 0,
    replyChars: reply.length,
    optionCount: options.found ? options.opts.length : 0,
    critical: recomputed.filter((w) => w.severity === 'critical').map((w) => w.code),
    warnings: recomputed.filter((w) => w.severity === 'warning').map((w) => w.code),
    agencyViolations: Array.isArray(log.agencyViolations) ? log.agencyViolations.length : 0,
  });
}

function median(values) {
  const xs = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!xs.length) return 0;
  const m = Math.floor(xs.length / 2);
  return xs.length % 2 ? xs[m] : Math.round((xs[m - 1] + xs[m]) / 2);
}

const completed = rows.filter((row) => row.status === 'complete');
const summary = {
  source: path.basename(target),
  appVersion: payload.appVersion || '',
  turns: rows.length,
  completed: completed.length,
  errors: rows.filter((row) => row.status === 'error').length,
  criticalWarnings: rows.reduce((n, row) => n + row.critical.length, 0),
  warnings: rows.reduce((n, row) => n + row.warnings.length, 0),
  missingActionOptions: completed.filter((row) => row.replyChars > 0 && row.optionCount < 2).length,
  agencyViolations: rows.reduce((n, row) => n + row.agencyViolations, 0),
  medianDurationMs: median(completed.map((row) => row.durationMs)),
  medianReplyChars: median(completed.map((row) => row.replyChars)),
  warningCodes: codeCounts,
  rows,
  notYetMeasurableFromV2Trace: [
    'NPC knowledge provenance',
    'promise lifecycle and expiry',
    'causal difference between branch replays',
    'medium-term versus short-term character state',
  ],
};

console.log(JSON.stringify(summary, null, 2));
