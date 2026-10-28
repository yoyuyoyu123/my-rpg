import assert from 'node:assert/strict';
import fs from 'node:fs';

const html = fs.readFileSync(new URL('../index.html', import.meta.url), 'utf8');
const payload = JSON.parse(fs.readFileSync(new URL('../data/worlds/catalog.json', import.meta.url), 'utf8'));
const worlds = payload.worlds;

assert.equal(payload.schema_version, 1);
assert.equal(worlds.length, 10);
assert.equal(new Set(worlds.map((world) => world.id)).size, worlds.length);
assert.deepEqual(
  new Set(worlds.map((world) => world.family)),
  new Set(['东方', '幻想', '现代', '未来', '末日恐怖']),
);

for (const world of worlds) {
  assert(world.id && world.name && world.family && world.skill_label && world.color);
  assert.equal(world.daily.length > 0, true, `${world.id} 缺少快捷动作`);
  assert.equal(world.presets.length > 0, true, `${world.id} 缺少预设`);
  assert(world.card.icon && world.card.description && world.card.tag, `${world.id} 缺少卡片信息`);
  assert.equal(new Set(world.presets.map((preset) => preset.id)).size, world.presets.length);
}

assert.match(html, /var WORLDS = \{\};/);
assert.match(html, /data\/worlds\/catalog\.json/);
assert.doesNotMatch(html, /var worlds_data\s*=/);
assert.doesNotMatch(html, /wuxia:\s*\{\s*name:'武侠江湖'/);
console.log('world catalog contract: 10 worlds share one versioned metadata source');
