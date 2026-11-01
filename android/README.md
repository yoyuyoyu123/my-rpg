# 无界 RPG · 安卓独立版

APK 内包含游戏页面、Python 后端、10 个世界、规则、记忆与 SQLite 存档。安装后在手机上配置自己的模型 API；联网调用 AI 时不需要电脑保持开机。不会预装开发者的 API Key 或存档。

## 安装试玩

使用构建产物 `app-debug.apk`（arm64-v8a，Android 7.0+，需要较新的 Android System WebView）。允许文件管理器安装该 APK 后，打开“无界 RPG”。启动完成后进入原有连接页面，在“本地后端配置”填模型 API Key，再选择模型、世界、开局开始玩。

仍支持自由输入、行动按钮、NPC、检定、背包、技能、任务、沉浸叙事模式、存档和撤销。API Key 与存档位于应用私有目录。电脑存档可先导出 JSON，再通过手机的系统文件选择器导入；手机也可导出 JSON 回电脑。首版不自动同步电脑存档。

生成回合时保持应用在前台。后台或锁屏时 Android 可能暂停/终止进程；重开后恢复最后已提交的进度。退出、安装更新或卸载前，建议导出存档。试玩 APK 使用调试签名；正式长期更新应配置固定私有签名，避免不同构建的签名不一致导致无法覆盖安装。

## 构建

安装 Android Studio（包含 Android SDK）、JDK 17 和 Python 3.12。打开本目录，同步 Gradle 后选择 Build APK。也可运行：

```bash
cd android
./gradlew :app:assembleDebug
```

Windows：`gradlew.bat :app:assembleDebug`。构建 Python 不在 PATH 时，设置 `WUJI_BUILD_PYTHON` 为 Python 3.12 的可执行文件路径。SDK 路径由 Android Studio 的 `local.properties` 或 `ANDROID_HOME` 提供，不要提交该文件。

默认产物：`app/build/outputs/apk/debug/app-debug.apk`。模拟器测试可用 `./gradlew clean :app:assembleDebug -PwujiAbis=x86_64`；切换 ABI 时先 clean。APK 不依赖局域网服务器，不需要给安卓页面填写电脑 IP。

代码使用 Chaquopy 17.2、AGP 8.9.2、Gradle 8.11.1、CPython 3.12。Android 依赖单独锁定在 `requirements-android.txt`，Pydantic core 从 Flet 官方 Android wheel 源取得；桌面端依赖不变。原生代码/标准库和依赖的许可随上游包保留，构建工具 SDK 许可证由开发者环境接受。

## 验证

```bash
python tools/prepare_android.py
python tools/test_android_runtime.py
python -m pytest backend/tests -q
```

`test_android_runtime.py` 启动真实手机引导模块，但在主机 Python 上执行，使用临时数据库，验证一次性引导、Cookie、配置和 SQLite 存档。不代表安卓真机执行结果。当前证据与限制见 `docs/ANDROID_WORK_ITEM.md`。
