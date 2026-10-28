import assert from 'node:assert/strict';
import { startTestBrowser } from './browser-test-environment.mjs';

const { browser, url, stop } = await startTestBrowser();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
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
  await page.waitForFunction(() => typeof window.doFetchStream === 'function');

  const result = await page.evaluate(async () => {
    BK = 'be';
    BACKEND_PROVIDER = 'deepseek';
    MODEL = 'browser-stream-test';
    SETTINGS.streamCps = 240;
    const encoder = new TextEncoder();
    const originalFetch = window.fetch;
    const frames = [
      'data: {"choices":[{"delta":{"content":"第一段"}}]}\n\n',
      'data: {"choices":[{"delta":{"content":"第二段"},"finish_reason":"stop"}]}\n\n',
      'data: [DONE]\n\n',
    ];
    let frameIndex = 0;
    window.fetch = async () => new Response(new ReadableStream({
      async pull(controller) {
        if (frameIndex >= frames.length) {
          controller.close();
          return;
        }
        controller.enqueue(encoder.encode(frames[frameIndex++]));
        await new Promise((resolve) => setTimeout(resolve, 5));
      },
    }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
    const seen = [];
    const complete = await doFetchStream(
      [{ role: 'user', content: '测试流式' }],
      200,
      (full) => { seen.push(full); return full.length; },
      null,
      { agent: 'narrative', title: '浏览器流式验收' },
    );

    const partialFrames = [
      'data: {"choices":[{"delta":{"content":"半截正文"}}]}\n\n',
    ];
    let partialIndex = 0;
    window.fetch = async () => new Response(new ReadableStream({
      pull(controller) {
        if (partialIndex >= partialFrames.length) {
          controller.close();
          return;
        }
        controller.enqueue(encoder.encode(partialFrames[partialIndex++]));
      },
    }), { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
    let partialError = null;
    try {
      await doFetchStream(
        [{ role: 'user', content: '测试断流' }],
        200,
        () => 1,
        null,
        { agent: 'narrative', title: '浏览器断流验收' },
      );
    } catch (error) {
      partialError = { message: String(error.message || error), partial: !!error.__partial, text: error.partialText || '' };
    }
    window.fetch = originalFetch;
    return { complete, seen, partialError };
  });

  assert.equal(result.complete.text, '第一段第二段');
  assert.ok(result.complete.frames >= 2);
  assert.ok(result.seen.length >= 2, '正文应分多次回调，而不是一次性出现');
  assert.equal(result.partialError.partial, true);
  assert.match(result.partialError.text, /半截正文/);
  assert.match(result.partialError.message, /完成标记|半截/);
  assert.deepEqual(pageErrors, [], `页面脚本错误：${pageErrors.join(' | ')}`);
  const relevantConsoleErrors = consoleErrors.filter((text) => !text.includes('ERR_NETWORK_ACCESS_DENIED'));
  assert.deepEqual(relevantConsoleErrors, [], `控制台错误：${relevantConsoleErrors.join(' | ')}`);
  console.log('browser stream: incremental SSE rendering and partial disconnect recovery passed');
} finally {
  await stop();
}
