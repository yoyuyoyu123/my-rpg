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
  await page.evaluate(async () => {
    goStep(1); setTab('be');
    document.getElementById('cfg-gemini').value = 'fixture-android-google-not-real';
    if (!await saveBackendConfig()) throw new Error('Isolated fixture configuration failed');
  });
  const modelID = page.locator('#be-model-id');
  const model = 'gemini-3.1-flash-lite';
  await modelID.pressSequentially(model, { delay: 30 });
  assert.equal(await modelID.inputValue(), model);
  await modelID.fill('');
  await modelID.focus();
  // A keyboard replaces the current composing span on each update, then commits.
  const keyboard = await page.context().newCDPSession(page);
  for (let length = 1; length <= model.length; length++) {
    await keyboard.send('Input.imeSetComposition', { text: model.slice(0, length), selectionStart: length, selectionEnd: length });
  }
  await keyboard.send('Input.insertText', { text: model });
  assert.equal(await modelID.inputValue(), model);
  await modelID.blur();
  await page.locator('#be-gemini-lite').click();
  assert.equal(await modelID.inputValue(), model);
  assert.match(await page.locator('#bemod').inputValue(), /^gemini\|/);
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
  console.log('Android shell: model typing, IME composition, one-tap Gemini selection, original save export/import, narration memory and panel back handling passed');
} finally { await stop(); }
