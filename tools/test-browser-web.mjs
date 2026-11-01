import assert from 'node:assert/strict';
import { startTestBrowser } from './browser-test-environment.mjs';

process.env.RPG_TEST_WEB_AUTH = '1';
const { browser, url, stop } = await startTestBrowser();
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
await page.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.fulfill({ contentType: 'text/css', body: '' }));
const errors = [];
page.on('pageerror', error => errors.push(String(error)));
try {
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  assert.match(page.url(), /_site\/login/);
  assert.equal((await page.request.get(url + 'api/saves')).status(), 401);
  await page.locator('#password').fill('fixture-site-password-12345');
  await page.locator('button[type=submit]').click();
  await page.waitForURL(url);
  await page.waitForFunction(() => typeof WujiWeb !== 'undefined' && document.querySelectorAll('#startup-slots .svs').length === 4);
  const manifest = await (await page.request.get(url + 'web/manifest.webmanifest')).json();
  assert.equal(manifest.display, 'standalone');
  assert.equal(manifest.icons.length, 2);
  assert.equal((await page.request.get(url + 'api/saves')).status(), 200);
  const configured = await page.evaluate(async () => {
    document.getElementById('cfg-gemini').value = 'fixture-google-not-real';
    document.getElementById('cfg-openai').value = 'fixture-openai-not-real';
    const ok = await saveBackendConfig();
    return { ok, options: document.getElementById('bemod').textContent,
      googleCleared: !document.getElementById('cfg-gemini').value,
      openaiCleared: !document.getElementById('cfg-openai').value };
  });
  assert.equal(configured.ok, true);
  assert.match(configured.options, /gemini-3.8-flash/);
  assert.match(configured.options, /gpt-6-luna/);
  assert.equal(configured.googleCleared && configured.openaiCleared, true);
  assert.equal(await page.evaluate(async () => { await navigator.serviceWorker.ready; return !!(await caches.match('/api/saves')); }), false);
  await page.waitForFunction(() => document.getElementById('site-logout'));
  await page.route('**/api/site/status', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ auth_enabled: true, revision: 'test-next-version' }) }));
  await page.evaluate(async () => { window.__updateMarker = true; await WujiWeb.checkVersion(); LOADING = true; });
  await page.locator('#web-update button').first().click();
  assert.equal(await page.evaluate(() => window.__updateMarker), true);
  const protectedSave = await page.evaluate(async () => {
    LOADING = false;
    HIST = [{ role: 'user', content: '测试更新前的存档' }];
    const original = savePut;
    savePut = async () => { throw new Error('fixture network failure'); };
    try { return await WujiWeb.refreshGame(); } finally { savePut = original; }
  });
  assert.equal(protectedSave, false);
  assert.equal(await page.evaluate(() => window.__updateMarker), true);
  await Promise.all([page.waitForEvent('load'), page.locator('#web-update button').first().click()]);
  await page.waitForFunction(() => typeof WujiWeb !== 'undefined');
  const saved = await (await page.request.get(url + 'api/saves/auto')).json();
  assert.equal(saved.payload.history[0].content, '测试更新前的存档');
  await page.waitForFunction(() => document.getElementById('site-logout'));
  await page.evaluate(() => document.getElementById('site-logout').click());
  await page.waitForURL('**/_site/login');
  assert.equal((await page.request.get(url + 'api/saves')).status(), 401);
  assert.deepEqual(errors, []);
  console.log('Private mobile web: login, protected saves, PWA manifest, uncached API, safe update, save-before-reload and logout passed');
} finally { await stop(); }
