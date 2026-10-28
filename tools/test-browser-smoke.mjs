import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { startTestBrowser } from './browser-test-environment.mjs';

const { browser, url, stop } = await startTestBrowser();
const artifactDir = path.resolve('.playwright-artifacts', 'browser-smoke');
fs.mkdirSync(artifactDir, { recursive: true });

const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const pageErrors = [];
const consoleErrors = [];
const failedRequests = [];

page.on('pageerror', (error) => pageErrors.push(String(error)));
page.on('console', (message) => {
  if (message.type() === 'error') consoleErrors.push(message.text());
});
page.on('requestfailed', (request) => {
  failedRequests.push({
    url: request.url(),
    error: request.failure()?.errorText || 'unknown',
  });
});

try {
  const response = await page.goto(url, { waitUntil: 'domcontentloaded' });
  assert(response, `没有收到页面响应：${url}`);
  assert.equal(response.status(), 200, `首页 HTTP ${response.status()}`);

  await page.waitForFunction(() => typeof window.render_game_to_text === 'function');
  await page.waitForFunction(() => Array.isArray(window.WORLD_CATALOG) && window.WORLD_CATALOG.length === 10);
  await page.waitForFunction(() => {
    const status = document.body.innerText;
    return status.includes('后端在线') || status.includes('连接失败');
  });

  const state = JSON.parse(await page.evaluate(() => window.render_game_to_text()));
  assert.equal(state.screen, 'menu');
  assert.equal(state.loading, false);
  assert.equal(state.turn, 0);
  await page.locator('#ascreen').waitFor({ state: 'visible', timeout: 5000 });
  const resumeTitle = page.locator('.startup-load-title');
  await resumeTitle.waitFor({ state: 'visible', timeout: 5000 });
  assert.match(await resumeTitle.innerText(), /继续已有进度/);
  await page.waitForFunction(() => document.querySelectorAll('#startup-slots .svs').length === 4);
  assert.equal(await page.locator('#startup-slots .svs').count(), 4);

  await page.screenshot({
    path: path.join(artifactDir, 'home.png'),
    fullPage: true,
  });
  fs.writeFileSync(
    path.join(artifactDir, 'state.json'),
    JSON.stringify(state, null, 2),
  );

  await page.evaluate(() => {
    // 世界选择页正常由“连接后端”进入；测试只建立最小已连接状态，绝不调用模型。
    BK = 'be';
    MODEL = 'browser-catalog-test';
    goStep(2);
  });
  await page.locator('#wscreen').waitFor({ state: 'visible', timeout: 5000 });
  assert.equal(await page.locator('#world-grid .wcard').count(), 12);
  await page.locator('#wc-fantasy').click();
  assert.equal(await page.locator('#wc-fantasy').evaluate((node) => node.classList.contains('sel')), true);
  assert.equal(await page.locator('#preset-chips .chip').count(), 6);
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    document.getElementById('wscreen').scrollTop = 0;
  });
  await page.screenshot({
    path: path.join(artifactDir, 'world-catalog.png'),
    fullPage: true,
  });

  // 不调用模型，直接验证多设备存档冲突的玩家选择层。
  await page.evaluate(() => {
    showSaveConflict('auto', { turns: 3 }, {
      conflict: true,
      currentRevision: 8,
      currentTurns: 5,
    }, true);
  });
  assert.equal(await page.locator('#imodal').evaluate((node) => node.classList.contains('on')), true);
  const conflictText = await page.locator('#imod-actions').innerText();
  assert.match(conflictText, /保留本机版本并覆盖服务端/);
  assert.match(conflictText, /读取服务端版本/);
  assert.match(conflictText, /稍后处理/);
  await page.evaluate(() => closeModal());

  // 用真实会话验证监视器既能即时显示，也能写入/读取服务端。
  const browserSessionId = await page.evaluate(async () => {
    const response = await fetch('/api/sessions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: '浏览器监视器验收',
        world_id: 'fantasy',
        preset_id: '',
        pace: 'long',
      }),
    });
    if (!response.ok) throw new Error(`创建浏览器验收会话失败：HTTP ${response.status}`);
    const session = await response.json();
    LORE.on = true;
    LORE.sid = session.id;
    return session.id;
  });
  // 验证监视器能显示提交环节的具体输入、输出和深度思考内容。
  await page.evaluate((sessionId) => {
    const id = monitorStart('commit', '浏览器验收提交', {
      input: 'commit_id=browser-contract',
      thinking: true,
      sessionId,
      turnId: 1,
      parentId: 'browser-parent',
      meta: { source: 'browser-contract' },
    });
    monitorStage(id, '服务端事务', 'done', '账本与自动存档已提交');
    monitorFinish(id, {
      output: '第 1 回合提交完成',
      reasoning: '这是浏览器验收用的深度思考占位内容',
    });
    openAgentMonitor();
  }, browserSessionId);
  await page.locator('#agent-monitor').waitFor({ state: 'visible', timeout: 5000 });
  const monitorText = await page.locator('#agent-monitor').innerText();
  assert.match(monitorText, /提交与存档/);
  assert.match(monitorText, /浏览器验收提交/);
  assert.match(monitorText, /深度思考/);
  assert.match(monitorText, /第 1 回合提交完成/);
  assert.match(monitorText, new RegExp(browserSessionId));
  assert.match(monitorText, /browser-parent/);
  await page.waitForFunction(async (sessionId) => {
    const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/agent-runs?limit=10`);
    if (!response.ok) return false;
    const rows = await response.json();
    return rows.some((row) => row.title === '浏览器验收提交' && row.status === 'done');
  }, browserSessionId, { timeout: 5000 });
  await page.locator('#agent-monitor-status-filter').selectOption('done');
  assert.match(await page.locator('#agent-monitor-summary').innerText(), /显示1\/\d+/);
  await page.locator('#agent-monitor-status-filter').selectOption('');
  await page.evaluate(() => closeAgentMonitor());

  // 受限测试环境可能禁止访问 Google Fonts；它不影响本地 UI 与游戏逻辑。
  const onlyExternalFontsFailed = failedRequests.length > 0
    && failedRequests.every((item) => /^https:\/\/fonts\.(?:googleapis|gstatic)\.com\//.test(item.url));
  const relevantConsoleErrors = onlyExternalFontsFailed
    ? consoleErrors.filter((text) => !text.includes('ERR_NETWORK_ACCESS_DENIED'))
    : consoleErrors;

  assert.deepEqual(pageErrors, [], `页面脚本错误：${pageErrors.join(' | ')}`);
  assert.deepEqual(
    relevantConsoleErrors,
    [],
    `控制台错误：${relevantConsoleErrors.join(' | ')}`,
  );

  console.log(
    `browser smoke: menu loaded, backend status resolved, screenshot=${path.join(artifactDir, 'home.png')}`,
  );
  if (onlyExternalFontsFailed) {
    console.log('browser smoke: Google Fonts request blocked by test environment (ignored)');
  }
} finally {
  await stop();
}
