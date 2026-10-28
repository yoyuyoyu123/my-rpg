import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { startTestBrowser } from './browser-test-environment.mjs';

const { browser, url, stop } = await startTestBrowser();
const artifactDir = path.resolve('.playwright-artifacts', 'browser-turn-transaction');
fs.mkdirSync(artifactDir, { recursive: true });

const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const pageErrors = [];
page.on('pageerror', (error) => pageErrors.push(String(error)));

try {
  const response = await page.goto(url, { waitUntil: 'domcontentloaded' });
  assert(response, `没有收到页面响应：${url}`);
  assert.equal(response.status(), 200, `首页 HTTP ${response.status()}`);
  await page.waitForFunction(() => typeof window.send === 'function');

  const failedTurn = await page.evaluate(async () => {
    const originalRunTurn = window._runTurn;
    const originalAddBlk = window.addBlk;
    const before = {
      history: JSON.parse(JSON.stringify(HIST)),
      turns: TURNS,
      clock: WORLD_CLOCK,
      backups: JSON.parse(JSON.stringify(TURN_BACKUPS)),
    };
    window.addBlk = () => {};
    window._runTurn = async () => { throw new Error('browser simulated failure'); };
    try {
      const result = await send('浏览器失败回滚测试', false);
      return {
        result,
        loading: LOADING,
        historyEqual: JSON.stringify(HIST) === JSON.stringify(before.history),
        turnsEqual: TURNS === before.turns,
        clockEqual: WORLD_CLOCK === before.clock,
        backupsEqual: JSON.stringify(TURN_BACKUPS) === JSON.stringify(before.backups),
      };
    } finally {
      window._runTurn = originalRunTurn;
      window.addBlk = originalAddBlk;
    }
  });
  assert.equal(failedTurn.result, false);
  assert.equal(failedTurn.loading, false);
  assert.equal(failedTurn.historyEqual, true);
  assert.equal(failedTurn.turnsEqual, true);
  assert.equal(failedTurn.clockEqual, true);
  assert.equal(failedTurn.backupsEqual, true);

  const undoResult = await page.evaluate(async () => {
    const originalRollback = window.loreRollback;
    const originalAutoSave = window.autoSave;
    const originalAddBlk = window.addBlk;
    const before = runtimeBackup();
    const beforeHistory = JSON.parse(JSON.stringify(HIST));
    const beforeBackups = JSON.parse(JSON.stringify(TURN_BACKUPS));
    let release;
    let saved = false;

    HIST = [
      { role: 'user', content: '撤回等待测试' },
      { role: 'assistant', content: '这一回合稍后才允许撤回。' },
    ];
    TURNS = 1;
    TURN_BACKUPS = [runtimeBackup()];
    LORE.on = true;
    window.addBlk = () => {};
    window.autoSave = () => { saved = true; };
    window.loreRollback = () => new Promise((resolve) => { release = resolve; });
    try {
      const pending = undoTurn();
      await Promise.resolve();
      const during = {
        loading: LOADING,
        historyLength: HIST.length,
        backupsLength: TURN_BACKUPS.length,
        saved,
      };
      release({ facts: 1 });
      await pending;
      return {
        during,
        after: {
          loading: LOADING,
          historyLength: HIST.length,
          backupsLength: TURN_BACKUPS.length,
          saved,
        },
      };
    } finally {
      HIST = beforeHistory;
      TURN_BACKUPS = beforeBackups;
      restoreRuntime(before);
      window.loreRollback = originalRollback;
      window.autoSave = originalAutoSave;
      window.addBlk = originalAddBlk;
    }
  });
  assert.deepEqual(undoResult.during, {
    loading: true,
    historyLength: 2,
    backupsLength: 1,
    saved: false,
  });
  assert.deepEqual(undoResult.after, {
    loading: false,
    historyLength: 0,
    backupsLength: 0,
    saved: true,
  });

  const saveRestore = await page.evaluate(async () => {
    const originalAddBlk = window.addBlk;
    window.addBlk = () => {};
    SAVE_BACKEND = null;
    SAVE_REVISIONS = {};
    BK = 'be';
    LORE = { on: false, sid: '', ctx: '', names: [], conflicts: [], busy: false, trace: [], counts: {} };
    WORLD = 'wuxia';
    PACE = 'long';
    TURNS = 3;
    HIST = [
      { role: 'user', content: '去江南渡口' },
      { role: 'assistant', content: '你在江南渡口看见了雨后的船灯。' },
    ];
    GAME_STATE = Object.assign(freshGameState(), { loc: '江南渡口' });
    syncStateCollections();
    const expected = snapshot();
    try {
      await savePut('sv_2', expected, { force: true });
      HIST = [];
      TURNS = 0;
      WORLD = 'fantasy';
      GAME_STATE = freshGameState();
      PENDING_STARTUP_LOAD = 'sv_2';
      await resumeStartupSave('sv_2');
      return {
        restored: HIST.length === 2
          && TURNS === 3
          && WORLD === 'wuxia'
          && GAME_STATE.loc === '江南渡口'
          && document.getElementById('slog').innerText.includes('江南渡口')
          && document.getElementById('gscreen').style.display === 'flex'
          && document.getElementById('ascreen').classList.contains('hidden'),
        revision: SAVE_REVISIONS.sv_2,
      };
    } finally {
      await saveDel('sv_2');
      window.addBlk = originalAddBlk;
    }
  });
  assert.equal(saveRestore.restored, true);
  assert.equal(typeof saveRestore.revision, 'number');

  const detached = await page.evaluate(() => {
    const saved = snapshot();
    const oldHistory = saved.history;
    const oldState = saved.gstate;
    HIST.push({ role: 'user', content: '快照之后的新消息' });
    GAME_STATE.__snapshotProbe = true;
    const result = !oldHistory.some((item) => item.content === '快照之后的新消息')
      && oldState.__snapshotProbe !== true;
    HIST.pop();
    delete GAME_STATE.__snapshotProbe;
    return result;
  });
  assert.equal(detached, true);
  assert.deepEqual(pageErrors, [], `页面脚本错误：${pageErrors.join(' | ')}`);

  await page.screenshot({
    path: path.join(artifactDir, 'transaction-complete.png'),
    fullPage: true,
  });
  fs.writeFileSync(
    path.join(artifactDir, 'result.json'),
    JSON.stringify({ failedTurn, undoResult, detached }, null, 2),
  );
  console.log(`browser turn transaction: 4 cases passed, artifacts=${artifactDir}`);
} finally {
  await stop();
}
