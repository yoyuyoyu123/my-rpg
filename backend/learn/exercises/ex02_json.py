"""
练习 02 · 返回 JSON
===================
概念：函数返回 Python 的 dict，FastAPI 会自动把它变成 JSON 发给前端。
     你不需要手动拼字符串。

任务：让 /world 返回这个 dict：{"id": "wuxia", "name": "武侠江湖"}
"""
from fastapi import FastAPI

app = FastAPI()


@app.get("/world")
def get_world():
    # TODO: 返回一个 dict，包含两个键：
    #   id   → "wuxia"
    #   name → "武侠江湖"
    return {}


# ─────────────────────────────────────────────
def verify():
    from fastapi.testclient import TestClient
    data = TestClient(app).get("/world").json()
    assert isinstance(data, dict), f"应该返回一个 dict，实际返回 {type(data).__name__}"
    assert data.get("id") == "wuxia", f'id 应该是 "wuxia"，实际是 {data.get("id")!r}'
    assert data.get("name") == "武侠江湖", f'name 应该是 "武侠江湖"，实际是 {data.get("name")!r}'
