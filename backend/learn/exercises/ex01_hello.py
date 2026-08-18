"""
练习 01 · 第一个路由
====================
概念：一个"路由"就是【一个网址】对应【一个函数】。

任务：把下面 TODO 那行改对，让访问 /hello 时返回字符串 "hello"。
"""
from fastapi import FastAPI

app = FastAPI()


# @app.get("/hello") 的意思是：
#   有人用浏览器访问 /hello 时，就调用下面这个函数。
@app.get("/hello")
def say_hello():
    # TODO: 把 None 改成 "hello"
    return None


# ─────────────────────────────────────────────
# 下面是自动验证，不用改
def verify():
    from fastapi.testclient import TestClient
    r = TestClient(app).get("/hello")
    assert r.status_code == 200, f"访问 /hello 应该成功(200)，实际是 {r.status_code}"
    assert r.json() == "hello", f'应该返回 "hello"，实际返回 {r.json()!r}'
