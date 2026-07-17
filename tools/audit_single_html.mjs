import fs from 'node:fs';

const file = process.argv[2];
if (!file) throw new Error('Usage: node audit_single_html.mjs <html>');
const source = fs.readFileSync(file, 'utf8');
const scripts = [...source.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)].map((match) => match[1]).join('\n');
const duplicates = (values) => {
  const counts = new Map();
  for (const value of values) counts.set(value, (counts.get(value) || 0) + 1);
  return [...counts].filter(([, count]) => count > 1);
};

const ids = [...source.matchAll(/\bid=["']([^"']+)["']/g)].map((match) => match[1]);
const definitions = [...scripts.matchAll(/(?:async\s+)?function\s+([\w$]+)\s*\(/g)].map((match) => match[1]);
const variableFunctions = [...scripts.matchAll(/(?:var|let|const)\s+([\w$]+)\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[\w$]+\s*=>)/g)].map((match) => match[1]);
const knownFunctions = new Set([...definitions, ...variableFunctions]);
const inlineHandlers = [...source.matchAll(/\bon(?:click|change|input|keydown|submit)=["']([^"']+)["']/g)].map((match) => match[1]);
const inlineCalls = inlineHandlers.flatMap((handler) => [...handler.matchAll(/\b([A-Za-z_$][\w$]*)\s*\(/g)].map((match) => match[1]));
const globals = new Set(['if', 'for', 'while', 'confirm', 'alert', 'prompt', 'String', 'Number', 'Boolean', 'Math', 'JSON', 'Date', 'Object', 'Array', 'parseInt', 'parseFloat']);
const missingInlineFunctions = [...new Set(inlineCalls.filter((name) => !knownFunctions.has(name) && !globals.has(name)))];

const results = {
  bytes: Buffer.byteLength(source),
  lines: source.split(/\r?\n/).length,
  script_blocks: [...source.matchAll(/<script(?:\s[^>]*)?>/gi)].length,
  duplicate_ids: duplicates(ids),
  duplicate_function_declarations: duplicates(definitions),
  missing_inline_functions: missingInlineFunctions,
  definitions: definitions.length,
  inline_handlers: inlineHandlers.length,
  possibly_unused_functions: [...new Set(definitions)].filter((name) => {
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return (scripts.match(new RegExp(`\\b${escaped}\\b`, 'g')) || []).length === 1 && !inlineCalls.includes(name);
  })
};

console.log(JSON.stringify(results, null, 2));
