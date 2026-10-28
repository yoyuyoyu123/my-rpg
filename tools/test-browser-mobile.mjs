import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { startTestBrowser } from './browser-test-environment.mjs';

const { browser, url, stop } = await startTestBrowser();
const artifactDir = path.resolve('.playwright-artifacts', 'browser-mobile');
fs.mkdirSync(artifactDir, { recursive: true });

const page = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
const pageErrors = [];
const consoleErrors = [];
page.on('pageerror', (error) => pageErrors.push(String(error)));
page.on('console', (message) => {
  if (message.type() === 'error') consoleErrors.push(message.text());
});

try {
  const response = await page.goto(url, { waitUntil: 'domcontentloaded' });
  assert(response, `没有收到页面响应：${url}`);
  assert.equal(response.status(), 200);
  await page.waitForFunction(() => typeof window.render_game_to_text === 'function');
  await page.waitForFunction(() => Array.isArray(window.WORLD_CATALOG) && window.WORLD_CATALOG.length === 10);
  await page.locator('#ascreen').waitFor({ state: 'visible', timeout: 5000 });

  const menuState = JSON.parse(await page.evaluate(() => window.render_game_to_text()));
  assert.equal(menuState.screen, 'menu');
  assert.equal(await page.locator('#startup-slots .svs').count(), 4);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2));

  await page.evaluate(() => {
    BK = 'be';
    MODEL = 'browser-mobile-test';
    goStep(2);
  });
  await page.locator('#wscreen').waitFor({ state: 'visible', timeout: 5000 });
  assert.equal(await page.locator('#world-grid .wcard').count(), 12);
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2));
  await page.screenshot({ path: path.join(artifactDir, 'world-mobile.png'), fullPage: true });

  assert.deepEqual(pageErrors, [], `页面脚本错误：${pageErrors.join(' | ')}`);
  const relevantConsoleErrors = consoleErrors.filter((text) => !text.includes('ERR_NETWORK_ACCESS_DENIED'));
  assert.deepEqual(relevantConsoleErrors, [], `控制台错误：${relevantConsoleErrors.join(' | ')}`);
  console.log(`browser mobile: menu/world responsive checks passed, screenshot=${path.join(artifactDir, 'world-mobile.png')}`);
} finally {
  await stop();
}
