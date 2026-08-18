"""
练习 03 · 两个路由
==================
概念：一个 app 可以挂很多个路由，各管各的网址。

任务：照着已有的 /health，自己写一个 /version，返回 {"version": "0.1.0"}
"""
from fastapi import FastAPI

app = FastAPI()


# 这个已经写好了，照着它的样子写下一个
@app.get("/health")
def health():
    return {"status": "ok"}


# TODO: 在这里写一个新路由
#   网址：/version
#   返回：{"version": "0.1.0"}
#
# 提示：需要三行——@app.get(...) 装饰器、def 函数名()、return {...}


# ─────────────────────────────────────────────
def verify():
    from fastapi.testclient import TestClient
    c = TestClient(app)
    assert c.get("/health").json() == {"status": "ok"}, "别把 /health 改坏了"
    r = c.get("/version")
    assert r.status_code != 404, "找不到 /version，你还没写这个路由"
    assert r.json() == {"version": "0.1.0"}, f'/version 应该返回 {{"version": "0.1.0"}}，实际返回 {r.json()!r}'
