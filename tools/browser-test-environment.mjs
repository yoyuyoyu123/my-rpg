import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { chromium } from 'playwright';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

export async function startTestServer() {
  if (process.env.RPG_URL) {
    throw new Error('浏览器回归只使用自动创建的隔离后端，请清除 RPG_URL；不能指向正式游戏地址。');
  }
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'wuji-browser-test-'));
  const python = process.env.RPG_TEST_PYTHON || path.join(root, 'backend', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const token = randomUUID();
  const child = spawn(python, [path.join(root, 'tools/browser_test_server.py'), '--data-dir', dataDir, '--token', token], {
    cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
  });
  let closed = false;
  const exited = new Promise(resolve => child.once('close', () => { closed = true; resolve(); }));
  const onExit = () => { if (!closed) child.kill(); };
  process.once('exit', onExit);
  let logs = '';
  child.stderr.on('data', chunk => { logs = (logs + chunk).slice(-4000); });
  const stop = async () => {
    if (!closed) child.kill();
    await exited;
    process.removeListener('exit', onExit);
    // Only remove the exact directory allocated by mkdtemp above, never a save slot.
    fs.rmSync(dataDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  };
  try {
    const port = await new Promise((resolve, reject) => {
      let output = '';
      const timer = setTimeout(() => reject(new Error('隔离后端启动超时：' + logs)), 30000);
      const fail = error => { clearTimeout(timer); reject(error); };
      child.once('error', fail);
      child.once('exit', code => fail(new Error(`隔离后端退出 ${code}: ${logs}`)));
      child.stdout.on('data', chunk => {
        output += chunk;
        const end = output.indexOf('\n');
        if (end < 0) return;
        try { const ready = JSON.parse(output.slice(0, end)); clearTimeout(timer); resolve(ready.port); }
        catch (error) { fail(error); }
      });
    });
    const url = `http://127.0.0.1:${port}/`;
    const deadline = Date.now() + 30000;
    let verified = false;
    while (Date.now() < deadline && !closed) {
      try {
        const response = await fetch(url + '__test__/identity', { signal: AbortSignal.timeout(1000) });
        const info = await response.json();
        verified = response.ok && info.isolated === true && info.token === token;
        if (verified) break;
      } catch { /* Wait for FastAPI startup. */ }
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    if (!verified) throw new Error('隔离后端身份验证失败：' + logs);
    return { url, dataDir, stop };
  } catch (error) {
    await stop();
    throw error;
  }
}

export async function startTestBrowser() {
  const server = await startTestServer();
  try {
    const browser = await chromium.launch({ headless: true });
    return { ...server, browser, stop: async () => {
      try { await browser.close(); } finally { await server.stop(); }
    } };
  } catch (error) {
    await server.stop();
    throw error;
  }
}
