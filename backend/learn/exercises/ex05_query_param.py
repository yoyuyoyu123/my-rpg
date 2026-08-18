"""
练习 05 · 查询参数
==================
概念：网址问号后面的东西叫查询参数，用来做筛选、翻页这类事。

     /worlds              →  family 是 None（没传）
     /worlds?family=东方   →  family 是 "东方"

     写法：函数参数【带默认值】就会被当成查询参数。

任务：让 /worlds 支持按 family 筛选。
"""
from fastapi import FastAPI

app = FastAPI()

WORLDS = [
    {"id": "wuxia", "name": "武侠江湖", "family": "东方"},
    {"id": "xianxia", "name": "仙侠修真", "family": "东方"},
    {"id": "cyber", "name": "赛博近未来", "family": "未来"},
]


@app.get("/worlds")
def list_worlds(family: str = None):
    # TODO:
    #   如果 family 是 None（没传参数）→ 返回全部 WORLDS
    #   如果 family 有值             → 只返回 family 匹配的那些
    #
    # 提示：可以用列表推导式
    #   [w for w in WORLDS if w["family"] == family]
    return WORLDS


# ─────────────────────────────────────────────
def verify():
    from fastapi.testclient import TestClient
    c = TestClient(app)
    all_ = c.get("/worlds").json()
    assert len(all_) == 3, f"不带参数时应该返回全部 3 条，实际返回 {len(all_)} 条"
    east = c.get("/worlds", params={"family": "东方"}).json()
    assert len(east) == 2, f'?family=东方 应该只返回 2 条，实际返回 {len(east)} 条'
    assert all(w["family"] == "东方" for w in east), "筛选结果里混进了其它家族"
    future = c.get("/worlds", params={"family": "未来"}).json()
    assert len(future) == 1, f'?family=未来 应该只返回 1 条，实际返回 {len(future)} 条'
