"""Read-only first-launch smoke test against a fresh CI Android emulator."""
import argparse
from pathlib import Path
import subprocess
import time


def adb(*args, timeout=20):
    return subprocess.run(["adb", "-e", *args], capture_output=True, text=True, timeout=timeout)


def main(apk):
    install = adb("install", "-r", str(apk), timeout=90)
    if install.returncode:
        raise RuntimeError(install.stderr or install.stdout)
    launch = adb("shell", "am", "start", "-n", "com.wuji.rpg/.MainActivity")
    if launch.returncode:
        raise RuntimeError(launch.stderr or launch.stdout)
    deadline = time.monotonic() + 120
    last = ""
    while time.monotonic() < deadline:
        try:
            adb("shell", "uiautomator", "dump", "/sdcard/wuji-smoke.xml")
            result = adb("shell", "cat", "/sdcard/wuji-smoke.xml")
            last = result.stdout
            if "游戏启动失败" in last or "游戏页面暂未连接" in last:
                break
            if any(text in last for text in ("继续已有进度", "本地后端配置")):
                print("Native Android: WebView, embedded Python, protected backend and game menu started")
                return
        except subprocess.TimeoutExpired:
            pass
        time.sleep(2)
    print(last[-8000:])
    logs = adb("logcat", "-d", "-t", "300")
    print(logs.stdout[-16000:])
    raise RuntimeError("Native game startup was not verified within 120 seconds")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("apk", type=Path)
    main(parser.parse_args().apk)
