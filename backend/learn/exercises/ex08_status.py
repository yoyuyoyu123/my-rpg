"""
练习 08 · HTTP 状态码
=====================
概念：找不到东西的时候，不能返回 200 + {"error": "没找到"}。
     必须返回 404 —— 状态码是给机器看的，前端靠它判断成功失败。

     常见的：200 成功 / 404 找不到 / 400 你传的参数不对 / 500 服务器炸了

任务：world_id 不存在时，抛出 404。
"""
from fastapi import FastAPI, HTTPException

app = FastAPI()

WORLDS = {"wuxia": "武侠江湖", "cyber": "赛博近未来"}


@app.get("/worlds/{world_id}")
def get_world(world_id: str):
    name = WORLDS.get(world_id)

    if name is None:
        # TODO: 这里要抛出 404
        #   写法：raise HTTPException(status_code=404, detail="世界观不存在")
        pass

    return {"id": world_id, "name": name}


# ─────────────────────────────────────────────
def verify():
    from fastapi.testclient import TestClient
    c = TestClient(app)
    ok = c.get("/worlds/wuxia")
    assert ok.status_code == 200, f"存在的世界观应该返回 200，实际 {ok.status_code}"
    assert ok.json()["name"] == "武侠江湖"
    bad = c.get("/worlds/nonexistent")
    assert bad.status_code == 404, (
        f"不存在的世界观应该返回 404，实际返回 {bad.status_code}\n"
        f"     响应内容：{bad.json()!r}\n"
        "     （返回 200 + name=null 是不行的，前端没法靠状态码判断）"
    )
