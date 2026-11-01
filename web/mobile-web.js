(function () {
  'use strict';
  if (window.WujiAndroid) return;
  var initialRevision = '', offered = '', registration = null, accepted = false, installPrompt = null;
  function notice(text) {
    if (typeof addBlk === 'function') addBlk('sys', '▸ ' + text);
  }
  async function refreshGame() {
    if (window.LOADING) { notice('当前回合完成后才能更新，进度不会被强制刷新。'); return false; }
    try {
      if (typeof pendingTurnRead === 'function' && await pendingTurnRead()) {
        notice('上一回合的提交仍待确认，请先恢复进度再更新。'); return false;
      }
      if (window.HIST && HIST.length && typeof savePut === 'function') await savePut('auto', snapshot());
    } catch (e) { notice('进度尚未保存，暂不更新。'); return false; }
    accepted = true;
    if (registration && registration.waiting) registration.waiting.postMessage({ type: 'SKIP_WAITING' });
    else location.reload();
    return true;
  }
  function offer(revision) {
    if (revision === offered) return;
    offered = revision;
    var previous = document.getElementById('web-update'); if (previous) previous.remove();
    var bar = document.createElement('div'); bar.id = 'web-update';
    bar.style.cssText = 'position:fixed;top:12px;left:12px;right:12px;z-index:3000;background:#173334;color:#eadcc1;border:1px solid #d8bc7f;border-radius:12px;padding:12px;display:flex;gap:10px;align-items:center;justify-content:center;flex-wrap:wrap;font:14px system-ui';
    var label = document.createElement('span'); label.textContent = '新版本已就绪'; bar.appendChild(label);
    var update = document.createElement('button'); update.textContent = '保存并更新'; update.onclick = refreshGame; bar.appendChild(update);
    var later = document.createElement('button'); later.textContent = '稍后'; later.onclick = function () { bar.remove(); }; bar.appendChild(later);
    document.body.appendChild(bar);
  }
  async function checkVersion() {
    try {
      var response = await fetch('/api/site/status', { cache: 'no-store' }); if (!response.ok) return;
      var status = await response.json();
      if (initialRevision && status.revision !== initialRevision) offer(status.revision);
      if (!initialRevision) initialRevision = status.revision;
      if (status.auth_enabled && !document.getElementById('site-logout')) {
        var button = document.createElement('button'); button.id = 'site-logout'; button.className = 'ob'; button.textContent = '退出网站登录';
        button.onclick = async function () {
          if (window.LOADING) { notice('请先完成当前回合。'); return; }
          try { if (window.HIST && HIST.length) await savePut('auto', snapshot()); }
          catch (e) { notice('进度尚未保存，暂不退出。'); return; }
          await fetch('/_site/logout', { method: 'POST' }); location.assign('/_site/login');
        };
        var settings = document.getElementById('set-narrative-mode');
        if (settings && settings.parentNode) settings.parentNode.parentNode.appendChild(button);
      }
    } catch (e) { /* Existing game handles connection errors. */ }
  }
  window.WujiWeb = { checkVersion: checkVersion, refreshGame: refreshGame };
  window.addEventListener('beforeinstallprompt', function (event) {
    event.preventDefault(); installPrompt = event;
    var settings = document.getElementById('set-narrative-mode');
    if (!settings || document.getElementById('site-install')) return;
    var button = document.createElement('button'); button.id = 'site-install'; button.className = 'ob'; button.textContent = '添加到手机主屏幕';
    button.onclick = async function () { if (installPrompt) { await installPrompt.prompt(); installPrompt = null; button.remove(); } };
    settings.parentNode.parentNode.appendChild(button);
  });
  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
    navigator.serviceWorker.register('/service-worker.js', { updateViaCache: 'none' }).then(function (reg) {
      registration = reg;
      if (reg.waiting && navigator.serviceWorker.controller) offer('worker');
      reg.addEventListener('updatefound', function () {
        var worker = reg.installing;
        worker.addEventListener('statechange', function () { if (worker.state === 'installed' && navigator.serviceWorker.controller) offer('worker'); });
      });
    }).catch(function () {});
    navigator.serviceWorker.addEventListener('controllerchange', function () { if (accepted) location.reload(); });
  }
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) { checkVersion(); if (registration) registration.update().catch(function () {}); }
  });
  checkVersion();
})();
