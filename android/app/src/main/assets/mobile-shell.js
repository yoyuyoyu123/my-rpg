(function () {
  'use strict';
  if (!window.WujiAndroid || window.__wujiMobileReady) return;
  window.__wujiMobileReady = true;
  var blobs = new Map(), create = URL.createObjectURL.bind(URL), revoke = URL.revokeObjectURL.bind(URL);
  URL.createObjectURL = function (blob) { var url = create(blob); blobs.set(url, blob); return url; };
  URL.revokeObjectURL = function (url) { blobs.delete(url); revoke(url); };
  var click = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    var blob = blobs.get(this.href), name = this.download;
    if (blob && name && /\.json$/i.test(name)) {
      if (blob.size > 16 * 1024 * 1024) { alert('导出文件超过 16 MB，请先缩减调试记录。'); return; }
      blob.text().then(function (text) { window.WujiAndroid.saveJson(name, text); })
        .catch(function () { alert('导出失败，请重试。'); });
      return;
    }
    return click.call(this);
  };
  window.wujiAndroidBack = function () {
    var input = document.getElementById('pinp');
    if (document.activeElement === input) { input.blur(); return true; }
    var modal = document.getElementById('imodal');
    if (modal && modal.classList.contains('on')) { closeModal(); return true; }
    var panel = document.getElementById('spnl');
    if (panel && panel.classList.contains('open')) { closePanel(); return true; }
    return false;
  };
})();
