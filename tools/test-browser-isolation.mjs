import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import { startTestServer } from './browser-test-environment.mjs';

// A legacy external address is rejected before any request can reach it.
let requests = 0;
const sentinel = http.createServer((_req, res) => { requests++; res.end('{}'); });
await new Promise(resolve => sentinel.listen(0, '127.0.0.1', resolve));
const oldUrl = process.env.RPG_URL;
try {
  process.env.RPG_URL = `http://127.0.0.1:${sentinel.address().port}/`;
  await assert.rejects(startTestServer, /RPG_URL/);
  assert.equal(requests, 0);
} finally {
  if (oldUrl === undefined) delete process.env.RPG_URL; else process.env.RPG_URL = oldUrl;
  await new Promise(resolve => sentinel.close(resolve));
}

const first = await startTestServer();
let second;
try {
  second = await startTestServer();
  assert.notEqual(first.url, second.url);
  assert.notEqual(first.dataDir, second.dataDir);
  const put = await fetch(first.url + 'api/saves/sv_2', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({payload: {history: [], world: 'fantasy', gstate: {}}, base_revision: 0}),
  });
  assert.equal(put.status, 200, await put.text());
  assert.equal((await fetch(first.url + 'api/saves/sv_2')).status, 200);
  assert.equal((await fetch(second.url + 'api/saves/sv_2')).status, 404);
  assert.equal((await fetch(first.url + 'api/chat', {method:'POST'})).status, 403);
  const config = await (await fetch(first.url + 'api/config')).json();
  for (const p of config.providers.filter(p => ['deepseek', 'openrouter', 'siliconflow', 'zhipu'].includes(p.id))) {
    assert.equal(p.configured, false);
  }
} finally {
  try { if (second) await second.stop(); } finally { await first.stop(); }
}
assert.equal(fs.existsSync(first.dataDir), false);
assert.equal(fs.existsSync(second.dataDir), false);
console.log('browser isolation: external URL rejected; independent stores; no paid models; cleanup passed');
