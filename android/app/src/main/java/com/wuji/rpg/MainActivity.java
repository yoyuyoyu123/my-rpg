package com.wuji.rpg;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.TextView;
import android.widget.Toast;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

public class MainActivity extends Activity {
    private static final int IMPORT = 101, EXPORT = 102;
    private static final ExecutorService WORKER = Executors.newSingleThreadExecutor();
    private static final Object SERVER_LOCK = new Object();
    private final Handler main = new Handler(Looper.getMainLooper());
    private WebView web;
    private TextView status;
    private String origin = "", pendingExport;
    private ValueCallback<Uri[]> fileCallback;
    private boolean destroyed;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.rgb(10, 25, 25));
        if (Build.VERSION.SDK_INT >= 30) getWindow().setDecorFitsSystemWindows(false);
        root.setOnApplyWindowInsetsListener((view, insets) -> {
            if (Build.VERSION.SDK_INT >= 30) {
                android.graphics.Insets bars = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout());
                android.graphics.Insets ime = insets.getInsets(WindowInsets.Type.ime());
                view.setPadding(bars.left, bars.top, bars.right, Math.max(bars.bottom, ime.bottom));
                return WindowInsets.CONSUMED;
            }
            view.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                    insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets.consumeSystemWindowInsets();
        });
        web = new WebView(this);
        root.addView(web, new FrameLayout.LayoutParams(-1, -1));
        status = new TextView(this);
        status.setTextColor(Color.rgb(220, 198, 155));
        status.setBackgroundColor(Color.rgb(10, 25, 25));
        status.setGravity(android.view.Gravity.CENTER);
        status.setText("正在启动无界 RPG…\n游戏和存档在这台手机上运行");
        root.addView(status, new FrameLayout.LayoutParams(-1, -1));
        setContentView(root);
        configureWebView();
        WORKER.execute(() -> {
            try {
                JSONObject info;
                synchronized (SERVER_LOCK) {
                    File resources = unpackResources();
                    if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
                    SharedPreferences prefs = getSharedPreferences("wuji-native", MODE_PRIVATE);
                    String result = Python.getInstance().getModule("mobile_runtime").callAttr("start",
                            new File(getFilesDir(), "game-data").getAbsolutePath(), resources.getAbsolutePath(), prefs.getInt("port", 0)).toString();
                    info = new JSONObject(result);
                    prefs.edit().putInt("port", info.getInt("port")).apply();
                }
                String launch = info.getString("url");
                origin = "http://127.0.0.1:" + info.getInt("port");
                awaitReady(launch);
                main.post(() -> { if (!destroyed) web.loadUrl(launch); });
            } catch (Exception error) {
                main.post(() -> { if (!destroyed) status.setText("游戏启动失败，已有存档保留。\n\n" + error.getMessage() + "\n\n请关闭应用后重试。"); });
            }
        });
    }

    @SuppressWarnings("SetJavaScriptEnabled")
    private void configureWebView() {
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true); // Explicit system file chooser grants only.
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSupportMultipleWindows(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, false);
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);
        web.addJavascriptInterface(new ExportBridge(), "WujiAndroid");
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest req) {
                Uri uri = req.getUrl();
                if (isLocal(uri.toString())) return false;
                if ("https".equals(uri.getScheme())) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); }
                    catch (Exception ignored) { toast("无法打开外部链接"); }
                }
                return true;
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (!isLocal(url)) return;
                try {
                    String js = new String(readAsset("mobile-shell.js"), StandardCharsets.UTF_8);
                    view.evaluateJavascript(js, null);
                    status.setVisibility(View.GONE);
                } catch (Exception error) { toast("手机文件功能初始化失败"); }
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError error) {
                if (req.isForMainFrame()) {
                    status.setVisibility(View.VISIBLE);
                    status.setText("游戏页面暂未连接，已有存档保留。\n请关闭应用后重试。");
                }
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("*/*").addCategory(Intent.CATEGORY_OPENABLE);
                intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"application/json", "image/png", "text/plain"});
                try { startActivityForResult(intent, IMPORT); }
                catch (Exception e) { fileCallback.onReceiveValue(null); fileCallback = null; toast("无法打开文件选择器"); }
                return true;
            }
        });
    }

    private boolean isLocal(String url) { return !origin.isEmpty() && (url.equals(origin + "/") || url.startsWith(origin + "/")); }
    private void toast(String text) { Toast.makeText(this, text, Toast.LENGTH_LONG).show(); }

    public final class ExportBridge {
        @JavascriptInterface public void saveJson(String name, String text) {
            if (text == null || text.length() > 16 * 1024 * 1024) return;
            main.post(() -> {
                if (destroyed || !isLocal(web.getUrl())) return;
                if (pendingExport != null) { toast("请先完成上一次导出"); return; }
                pendingExport = text;
                String filename = name == null ? "wuji-save.json" : name.replaceAll("[^A-Za-z0-9._-]", "_");
                if (!filename.endsWith(".json")) filename = "wuji-save.json";
                Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT).setType("application/json").addCategory(Intent.CATEGORY_OPENABLE);
                intent.putExtra(Intent.EXTRA_TITLE, filename);
                try { startActivityForResult(intent, EXPORT); }
                catch (Exception e) { pendingExport = null; toast("无法导出，请检查系统文件管理器"); }
            });
        }
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == IMPORT && fileCallback != null) {
            fileCallback.onReceiveValue(result == RESULT_OK && data != null && data.getData() != null ? new Uri[]{data.getData()} : null);
            fileCallback = null;
        } else if (request == EXPORT) {
            String text = pendingExport;
            pendingExport = null;
            if (result == RESULT_OK && data != null && data.getData() != null && text != null) {
                Uri uri = data.getData();
                WORKER.execute(() -> {
                    try (OutputStream out = getContentResolver().openOutputStream(uri)) {
                        if (out == null) throw new java.io.IOException("无法写入文件");
                        out.write(text.getBytes(StandardCharsets.UTF_8));
                        main.post(() -> toast("已导出游戏记录"));
                    } catch (Exception e) { main.post(() -> toast("导出失败，请重试")); }
                });
            }
        }
    }

    @Override public void onBackPressed() {
        if (web == null || origin.isEmpty()) { super.onBackPressed(); return; }
        web.evaluateJavascript("typeof wujiAndroidBack==='function' && wujiAndroidBack()", value -> {
            if (destroyed) return;
            if (!"true".equals(value)) new AlertDialog.Builder(this).setTitle("暂时离开游戏？")
                .setMessage("已提交的进度会保留；生成中的回合请等待完成。")
                .setPositiveButton("离开", (d, which) -> finish()).setNegativeButton("继续玩", null).show();
        });
    }

    private byte[] readAsset(String name) throws Exception {
        try (InputStream in = getAssets().open(name); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192]; int read;
            while ((read = in.read(buffer)) != -1) out.write(buffer, 0, read);
            return out.toByteArray();
        }
    }

    private File unpackResources() throws Exception {
        File root = new File(getFilesDir(), "game-web-" + BuildConfig.VERSION_CODE);
        String manifest = new String(readAsset("game-manifest.json"), StandardCharsets.UTF_8);
        File stamp = new File(root, ".ready");
        if (stamp.isFile()) {
            try (InputStream in = new FileInputStream(stamp); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
                byte[] buffer = new byte[8192]; int size;
                while ((size = in.read(buffer)) != -1) out.write(buffer, 0, size);
                if (out.toString("UTF-8").equals(manifest)) return root;
            }
        }
        if (!root.exists() && !root.mkdirs()) throw new java.io.IOException("无法准备游戏资源目录");
        String prefix = root.getCanonicalPath() + File.separator;
        try (ZipInputStream zip = new ZipInputStream(getAssets().open("game-web.zip"))) {
            ZipEntry entry; byte[] buffer = new byte[8192];
            while ((entry = zip.getNextEntry()) != null) {
                File target = new File(root, entry.getName());
                if (!target.getCanonicalPath().startsWith(prefix)) throw new SecurityException("非法资源路径");
                if (entry.isDirectory()) { target.mkdirs(); continue; }
                File parent = target.getParentFile();
                if (parent != null && !parent.exists() && !parent.mkdirs()) throw new java.io.IOException("无法创建资源目录");
                try (FileOutputStream out = new FileOutputStream(target)) {
                    int size; while ((size = zip.read(buffer)) != -1) out.write(buffer, 0, size);
                }
            }
        }
        try (FileOutputStream out = new FileOutputStream(stamp)) { out.write(manifest.getBytes(StandardCharsets.UTF_8)); }
        return root;
    }

    private void awaitReady(String launch) throws Exception {
        long deadline = System.currentTimeMillis() + 60000;
        // An unauthenticated health request must return 403: it proves the gate is serving.
        String health = new URL(new URL(launch), "/health").toString();
        while (System.currentTimeMillis() < deadline) {
            try {
                HttpURLConnection conn = (HttpURLConnection) new URL(health).openConnection();
                conn.setConnectTimeout(1000); conn.setReadTimeout(1000);
                try { if (conn.getResponseCode() == 403) return; } finally { conn.disconnect(); }
            } catch (java.io.IOException ignored) { }
            Thread.sleep(100);
        }
        throw new java.io.IOException("本地游戏服务启动超时");
    }

    @Override protected void onDestroy() {
        destroyed = true;
        if (fileCallback != null) fileCallback.onReceiveValue(null);
        if (web != null) { web.removeJavascriptInterface("WujiAndroid"); web.destroy(); }
        super.onDestroy();
    }
}
