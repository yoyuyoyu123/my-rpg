"""
练习 04 · 路径参数
==================
概念：网址里可以有【变量部分】，写成 {名字}，它会自动变成函数的参数。

     访问 /worlds/wuxia   →  world_id 的值是 "wuxia"
     访问 /worlds/cyber   →  world_id 的值是 "cyber"

任务：让 /worlds/{world_id} 返回 {"id": 传进来的id}
"""
from fastapi import FastAPI

app = FastAPI()


# 注意两个地方要对应：网址里的 {world_id}  ←→  函数参数 world_id
@app.get("/worlds/{world_id}")
def get_world(world_id: str):
    # TODO: 返回 {"id": world_id}
    #   注意不是 {"id": "world_id"} —— 加引号就变成死字符串了
    return {}


# ─────────────────────────────────────────────
def verify():
    from fastapi.testclient import TestClient
    c = TestClient(app)
    a = c.get("/worlds/wuxia").json()
    assert a == {"id": "wuxia"}, f'/worlds/wuxia 应该返回 {{"id": "wuxia"}}，实际返回 {a!r}'
    b = c.get("/worlds/cyber").json()
    assert b == {"id": "cyber"}, (
        f'/worlds/cyber 应该返回 {{"id": "cyber"}}，实际返回 {b!r}\n'
        "     （如果两次返回一样，说明你把变量写成固定字符串了）"
    )
