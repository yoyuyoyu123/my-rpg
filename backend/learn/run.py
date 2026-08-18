"""
FastAPI 练习跑分器
==================

用法（在 backend 目录下）：

    .venv/Scripts/python.exe learn/run.py          # 检查当前进度
    .venv/Scripts/python.exe learn/run.py watch    # 自动监视，改完文件立刻验证

它会找到你第一个没做完的练习，告诉你要做什么。
做完一个自动进下一个。
"""
import importlib
import os
import sys
import time
from pathlib import Path

LEARN_DIR = Path(__file__).parent
sys.path.insert(0, str(LEARN_DIR.parent))

# 关掉 starlette 的过时警告，避免干扰初学者
import warnings
warnings.filterwarnings("ignore")

# Windows 终端默认是 GBK 编码，打印中文和符号会崩。
# 强制把输出流切成 UTF-8，并在不支持的终端上退回纯 ASCII 符号。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    _UNICODE_OK = True
except Exception:
    _UNICODE_OK = False

if os.name == "nt":
    os.system("")  # 让 Windows 终端认识 ANSI 颜色码

MARK_OK = "✓" if _UNICODE_OK else "[OK]"
MARK_CUR = "▶" if _UNICODE_OK else ">>"
MARK_TODO = "·" if _UNICODE_OK else " -"

# 练习清单：(模块名, 标题, 验证函数名)
EXERCISES = [
    ("ex01_hello", "第一个路由"),
    ("ex02_json", "返回 JSON"),
    ("ex03_two_routes", "两个路由"),
    ("ex04_path_param", "路径参数"),
    ("ex05_query_param", "查询参数"),
    ("ex06_model", "第一个数据模型"),
    ("ex07_validation", "契约会拦住你"),
    ("ex08_status", "HTTP 状态码"),
]

GREEN, RED, YELLOW, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m"


def check_one(mod_name: str):
    """跑一个练习的验证。返回 (是否通过, 提示信息)。"""
    full = f"learn.exercises.{mod_name}"
    try:
        # 每次都重新导入，这样改完文件不用重启
        if full in sys.modules:
            del sys.modules[full]
        mod = importlib.import_module(full)
    except Exception as e:
        return False, f"文件有语法错误，Python 读不下去：\n     {type(e).__name__}: {e}"

    verify = getattr(mod, "verify", None)
    if verify is None:
        return False, "这个练习文件缺少 verify 函数（不该发生，去问 Claude）"

    try:
        verify()
        return True, ""
    except AssertionError as e:
        return False, str(e) or "验证没通过"
    except Exception as e:
        return False, f"运行时出错：{type(e).__name__}: {e}"


def render(verbose_current=True):
    """打印所有练习状态，返回第一个未通过的索引。"""
    first_todo = None
    lines = []
    for i, (mod, title) in enumerate(EXERCISES):
        ok, msg = check_one(mod)
        if ok:
            lines.append(f"  {GREEN}{MARK_OK}{RESET} {DIM}{i+1:02d} {title}{RESET}")
        else:
            if first_todo is None:
                first_todo = (i, mod, title, msg)
                lines.append(f"  {YELLOW}{MARK_CUR}{RESET} {BOLD}{i+1:02d} {title}{RESET}  {DIM}<- 你在这里{RESET}")
            else:
                lines.append(f"  {DIM}{MARK_TODO}  {i+1:02d} {title}{RESET}")
    print("\n".join(lines))
    print()

    if first_todo is None:
        print(f"{GREEN}{BOLD}全部完成。{RESET}Lesson 01 通关，可以进下一课了。\n")
        return None

    i, mod, title, msg = first_todo
    if verbose_current:
        print(f"{BOLD}当前任务：{i+1:02d} {title}{RESET}")
        print(f"{DIM}文件：learn/exercises/{mod}.py{RESET}\n")
        print(f"{RED}没通过：{RESET}{msg}\n")
    return i


def main():
    watch = len(sys.argv) > 1 and sys.argv[1] == "watch"
    print(f"\n{BOLD}FastAPI 练习{RESET} {DIM}· 打开对应文件，完成里面的 TODO{RESET}\n")

    if not watch:
        render()
        print(f"{DIM}提示：用 `python learn/run.py watch` 可以边改边自动检测{RESET}\n")
        return

    # watch 模式：轮询文件修改时间
    print(f"{DIM}监视中… 改完文件保存即可，Ctrl+C 退出{RESET}\n")
    last_sig = None
    last_idx = -1
    try:
        while True:
            ex_dir = LEARN_DIR / "exercises"
            sig = tuple(sorted((p.name, p.stat().st_mtime) for p in ex_dir.glob("*.py")))
            if sig != last_sig:
                last_sig = sig
                print("\033[2J\033[H", end="")  # 清屏
                print(f"\n{BOLD}FastAPI 练习{RESET} {DIM}· 监视中{RESET}\n")
                idx = render()
                if idx is None:
                    return
                if idx != last_idx:
                    last_idx = idx
            time.sleep(0.6)
    except KeyboardInterrupt:
        print("\n退出监视。\n")


if __name__ == "__main__":
    main()
