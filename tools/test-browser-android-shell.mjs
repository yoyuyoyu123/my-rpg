import assert from 'node:assert/strict';
import fs from 'node:fs';
import { startTestBrowser } from './browser-test-environment.mjs';

const { browser, url, stop } = await startTestBrowser();
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.fulfill({ contentType: 'text/css', body: '' }));
const errors = [];
page.on('pageerror', e => errors.push(String(e)));
try {
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => document.querySelectorAll('#startup-slots .svs').length === 4);
  await page.evaluate(() => {
    window.phoneExports = [];
    window.WujiAndroid = { saveJson: (name, text) => phoneExports.push({ name, text }) };
  });
  await page.addScriptTag({ content: fs.readFileSync(new URL('../android/app/src/main/assets/mobile-shell.js', import.meta.url), 'utf8') });
  await page.evaluate(() => {
    WORLD = 'wuxia'; TURNS = 2;
    HIST = [{ role: 'user', content: '我把干粮收进行囊。' }, { role: 'assistant', content: '干粮还温着。' }];
    GAME_STATE = freshGameState(); GAME_STATE.inv = [{ name: '干粮', quantity: 1 }];
    NOVEL_RUNTIME = { excerpts: [{ turn: 2, text: '干粮还温着。' }] };
    exportSave();
  });
  await page.waitForFunction(() => phoneExports.length === 1);
  const exported = await page.evaluate(() => phoneExports[0]);
  assert.match(exported.name, /^wuji_save_.*\.json$/);
  assert.equal(JSON.parse(exported.text).novelRuntime.excerpts[0].text, '干粮还温着。');
  await page.evaluate(() => { HIST = []; NOVEL_RUNTIME = {}; });
  const chooserPromise = page.waitForEvent('filechooser');
  await page.evaluate(() => importSave());
  const chooser = await chooserPromise;
  await chooser.setFiles({ name: 'phone-save.json', mimeType: 'application/json', buffer: Buffer.from(exported.text) });
  await page.waitForFunction(() => TURNS === 2 && HIST.length === 2);
  assert.equal(await page.evaluate(() => NOVEL_RUNTIME.excerpts[0].text), '干粮还温着。');
  const back = await page.evaluate(() => {
    const panel = document.getElementById('spnl'); panel.classList.add('open');
    const handled = wujiAndroidBack();
    return { handled, closed: !panel.classList.contains('open'), idle: wujiAndroidBack() };
  });
  assert.deepEqual(back, { handled: true, closed: true, idle: false });
  assert.deepEqual(errors, []);
  console.log('Android shell: original save export to native bridge, JSON import, narration memory and panel back handling passed');
} finally { await stop(); }
