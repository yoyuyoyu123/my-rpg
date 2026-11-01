import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { startTestBrowser } from './browser-test-environment.mjs';

process.env.RPG_TEST_NOVEL_FIXTURE = '1';
const { browser, url, stop } = await startTestBrowser();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
const errors = [];
page.on('pageerror', e => errors.push(String(e)));
const artifacts = path.resolve('.playwright-artifacts/browser-novel-game');
fs.mkdirSync(artifacts, { recursive: true });
try {
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof send === 'function' && Array.isArray(WORLD_CATALOG));
  const played = await page.evaluate(async () => {
    BK = 'be'; BACKEND_PROVIDER = 'ollama'; MODEL = 'isolated-fixture'; WORLD = 'wuxia'; PACE = 'long';
    SETTINGS.narrativeMode = 'quality'; SETTINGS.stream = false; SETTINGS.autoMem = false;
    SETTINGS.storyAgents = false; SETTINGS.stateSync = true; SETTINGS.agencyGuard = true;
    SETTINGS.dice = true; SETTINGS.director = true;
    HIST = [{ role: 'user', content: '我走进茶馆。' }, { role: 'assistant', content: '掌柜正在擦桌。柜台旁摆着干粮。' }];
    TURNS = 0; TURN_BACKUPS = []; NOVEL_RUNTIME = {}; STORY_RUNTIME = {}; PREMISE_STATE = { kind: 'none' };
    PREFS = {}; GAME_STATE = revealedGameState({}); QUESTS = { main: [{ title: '明日送信', done: false }], side: [] };
    GAME_STATE.loc = '茶馆'; GAME_STATE.npcs = { '掌柜': { att: 0, rel: '熟人', knows: [] } };
    // Mock model-only adjudication/audit; program dice, state apply, ledger and save stay real.
    directorPass = async () => ({ risky: true, attr: Object.keys(GAME_STATE.attrs)[0], dc: 40, action: '练习', focus: '交易、练习与确认委托' });
    reconcileTurnState = async () => ({ inv_add: [{ name: '干粮', qty: 1 }], skill_upsert: [{ name: '基础剑法', proficiency: 5 }] });
    maybeCompress = () => {}; maybeAutoMemory = () => {}; loreQueue = () => {};
    const sr = await fetch('/api/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: '沉浸游戏回归', world_id: WORLD, pace: PACE }) });
    const session = await sr.json();
    LORE.on = true; LORE.sid = session.id; LORE.conflicts = [];
    SAVE_BACKEND = null; SAVE_REVISIONS = {}; await saveSummaries();
    document.getElementById('ascreen').classList.add('hidden'); document.getElementById('gscreen').style.display = 'flex';
    rebuildLog();
    const before = runtimeBackup();
    const ok = await send('我购买干粮，练习基础剑法，并与掌柜确认明日送信的委托。', false);
    const saved = await (await fetch('/api/saves/auto')).json();
    return { ok, turn: TURNS, inv: GAME_STATE.inv, skills: GAME_STATE.skills, check: GAME_STATE.lastCheck,
      quests: QUESTS, npc: GAME_STATE.npcs, last: NOVEL_RUNTIME.last, saved: saved.payload,
      options: document.querySelectorAll('#slog .sb.nar:last-child .opts .ob').length, before };
  });
  assert.equal(played.ok, true);
  assert.equal(played.turn, 1);
  assert(played.inv.some(x => x.name === '干粮' && x.quantity === 1));
  assert(played.skills.some(x => x.name === '基础剑法'));
  assert(played.check.die >= 1 && played.check.die <= 100);
  assert.equal(played.quests.main[0].title, '明日送信');
  assert(played.npc['掌柜']);
  assert.equal(played.last.candidate_count, 2);
  assert.equal(played.saved.novelRuntime.last.turn, 1);
  assert.equal(played.saved.gstate.inv[0].name, '干粮');
  assert(played.options >= 2);
  // A second turn is sent by the real action button, preserving free input alongside it.
  await page.locator('#slog .sb.nar').last().locator('.opts .ob').first().click();
  await page.waitForFunction(() => !LOADING && TURNS === 2, { timeout: 15000 });
  const second = await page.evaluate(() => ({ turn: TURNS, last: HIST.at(-2).content, runtime: NOVEL_RUNTIME, state: GAME_STATE }));
  assert.match(second.last, /询问送信地点/);
  assert.equal(second.runtime.last.turn, 2);
  // Undo must roll back the new memory together with existing game items and skills.
  const undo = await page.evaluate(async () => { await undoTurn(); return { turn: TURNS, runtime: NOVEL_RUNTIME, state: GAME_STATE }; });
  assert.equal(undo.turn, 1);
  assert.equal(undo.runtime.last.turn, 1);
  assert.equal(undo.runtime.excerpts.length, 1);
  assert.equal(undo.state.inv.find(x => x.name === '干粮').quantity, 1);
  // Save/load the whole game, including optional narration state and explicit feedback.
  const reload = await page.evaluate(async () => {
    await recordNovelFeedback(true); await recordNovelFeedback(false);
    await savePut('sv_0', snapshot());
    const expected = JSON.stringify(NOVEL_RUNTIME);
    NOVEL_RUNTIME = {}; GAME_STATE = freshGameState();
    applySnapshot(await saveGet('sv_0'));
    return { same: JSON.stringify(NOVEL_RUNTIME) === expected, preferences: NOVEL_RUNTIME.preferences,
      style: NOVEL_RUNTIME.last.style, inv: GAME_STATE.inv, turn: TURNS };
  });
  assert.equal(reload.same, true);
  assert.equal(reload.preferences[reload.style].likes, 0);
  assert.equal(reload.preferences[reload.style].dislikes, 1);
  assert(reload.inv.some(x => x.name === '干粮'));
  // Failed final commit must not leave speculative memory/state in the running game.
  await page.route('**/api/sessions/*/turn/commit', route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"detail":{"message":"fixture commit failed"}}' }));
  const failure = await page.evaluate(async () => {
    const before = JSON.stringify(runtimeBackup()), hist = JSON.stringify(HIST);
    const ok = await send('我继续询问送信的地点。', false);
    return { ok, unchanged: before === JSON.stringify(runtimeBackup()), history: hist === JSON.stringify(HIST) };
  });
  assert.deepEqual(failure, { ok: false, unchanged: true, history: true });
  assert.deepEqual(errors, []);
  await page.screenshot({ path: path.join(artifacts, 'game.png'), fullPage: true });
  console.log('novel game: free input, action buttons, NPC, dice, inventory, skills, quest, atomic save, feedback, reload, undo and failed commit passed');
} finally { await stop(); }
