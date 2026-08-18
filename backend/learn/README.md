# FastAPI 练习 · Lesson 01

零基础起步。8 个小练习，每个只教一件事，改完自动检测对错。

## 怎么用

在 `backend` 目录下开两个终端。

**终端 1** — 让它一直开着，自动检测：

```bash
.venv/Scripts/python.exe learn/run.py watch
```

**终端 2**（可选）— 想看真实网页效果时用：

```bash
.venv/Scripts/python.exe -m uvicorn learn.exercises.ex01_hello:app --reload --port 8000
```

然后打开 http://127.0.0.1:8000/docs

> 换练习就把命令里的 `ex01_hello` 换成别的文件名。
> 端口被占就换个数字：`--port 8001`

## 流程

1. `run.py watch` 会告诉你当前卡在第几题、哪个文件、错在哪
2. 用编辑器打开那个文件，完成里面的 `TODO`
3. 保存 → 终端自动重新检测 → 变绿就自动进下一题

不用背，不用先读完文档。**卡住了就问**，问原理我讲透。

## 8 个练习

| # | 学什么 |
|---|---|
| 01 | 路由 = 一个网址对应一个函数 |
| 02 | 返回 dict 会自动变成 JSON |
| 03 | 一个服务可以有多个路由 |
| 04 | 网址里的变量（路径参数） |
| 05 | 问号后面的筛选条件（查询参数） |
| 06 | 用 Pydantic 规定数据长什么样 |
| 07 | 契约会在运行时真的拦住你 |
| 08 | 找不到要返回 404，不是 200 |

全绿之后进 Lesson 02：前后端边界划分。

## 遇到报错怎么办

**`WinError 10013`** — 端口被占了。换端口 `--port 8001`，或者查谁占了：

```powershell
Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
```

**`ModuleNotFoundError`** — 你不在 `backend` 目录下，或者没用 `.venv` 里的 python。

**中文乱码** — 已经处理过了，如果还有告诉我。
