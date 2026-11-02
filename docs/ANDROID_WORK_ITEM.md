# AND-01：手机独立运行的安卓 APK

目标：保留原 RPG 和 NE-01，手机安装后本地执行规则、记忆、SQLite 存档和叙事编排，只需联网调用 AI，无需电脑保持开机。Android 7.0+、arm64-v8a 首版；可附带 x86_64 供模拟器测试。

架构：原生 Activity/WebView + Chaquopy Python 3.12 + 原 FastAPI 后端。HTML、10 世界目录、类型研究数据随 APK 打包。仅修改三个资源/配置根目录的环境变量支持，桌面默认路径不变。APK 不带 .env、存档、虚拟环境或开发者密钥。

本地服务仅监听 127.0.0.1。每次进程启动产生随机令牌，通过一次性引导换取 HttpOnly/SameSite=Strict Cookie；其余端点先鉴权再进游戏。端口按安装记录保存，避免 WebView 的 IndexedDB/localStorage 因端口变化丢失；端口被占用时明确报错，不静默切换存储源。配置与 SQLite 在应用私有目录；关闭 Android 云备份。

WebView 保留 JavaScript/DOM 存储，禁止 file:// 访问、混合内容与任意原生接口。只允许导航到自己的本地 origin，外链用外部浏览器。原生桥仅提供用户主动触发的 JSON 导出（系统文件选择器）；导入通过文件选择器。适配系统栏、软键盘、返回键和旋转。

前后台边界：前台正常游戏；系统杀进程时保留最后提交存档，下次重开恢复。首版不承诺锁屏/后台长时间生成，避免引入常驻通知与耗电。网络断开不把候选写成已完成进度。

依赖：Android 单独锁定兼容版本，Pydantic core 使用 Flet 官方 Android wheel 源，greenlet 使用 Chaquopy 官方源；使用纯 Python Uvicorn，不带 uvloop。桌面依赖不降级。构建本身须实际完成才称为“已生成 APK”；无真机/模拟器运行证据时明确说明。

验收：资源打包无秘密、引导鉴权/异常路径、启动建库、API 配置、SSE、完整游戏回合与原子存档、导入导出、手机键盘/导航。APK 编译与签名检查；真机结果另记。

参考：Chaquopy Android 插件 https://chaquo.com/chaquopy/doc/current/android.html ；Flet 官方 wheel 源 https://pypi.flet.dev/pydantic-core/ ；AGP 8.9 https://developer.android.com/build/releases/agp-8-9-0-release-notes 。

## 本次验证

- arm64-v8a 安装包实际编译成功，APK v2 签名验证通过；Android lint：0 errors、2 warnings（旧系统忽略新版 manifest 属性、提示文案国际化）。
- x86_64 测试包编译成功。无 KVM 的本地软件模拟器未取得启动成功证据；随后 GitHub 的 KVM 模拟器实际运行成功，确认 WebView、内置 Python、受保护后端与游戏菜单启动。证据：https://github.com/yoyuyoyu123/my-rpg/actions/runs/41324464944 。仍未在物理安卓手机上运行。
- 桌面依赖下后端：473 passed、3 既有 xfailed；Android 锁定依赖的主机环境下同为 473 passed、3 xfailed。前端契约通过。
- 手机引导模块在隔离主机环境中启动真实服务：一次性引导/HttpOnly Cookie、未授权访问拒绝、API 配置写入私有目录、世界目录、SQLite 和叙事记忆存档往返通过。
- Android 依赖下的完整浏览器游戏回归通过；手机 JS 桥的原存档导出、JSON 导入、叙事记忆与返回关闭面板通过。安卓系统文件选择器、软键盘与真机后台行为尚待设备验证。
- 资源与 APK 检查确认含 Python、世界与研究数据，不含用户 .env、数据库或虚拟环境。Gradle 下载有 SHA-256 校验。CI 提供重复构建与 APK artifact。

交付：`wuji-rpg-android-preview-arm64.apk`，32,244,365 bytes，SHA-256 `80ebb68dc6f11a71279aa0a69a03e1ff85e303677184ce0e88ac7795c748b454`。调试签名、Android 7.0+、arm64-v8a，需较新的系统 WebView 和玩家自己的模型 API Key。

此为可安装测试构建；以上主机测试和编译结果不构成真机兼容性保证，也未验证实际付费模型的安卓端长回合体验。
