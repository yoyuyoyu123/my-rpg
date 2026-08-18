"""
练习 07 · 契约会拦住你
======================
概念：这是 Pydantic 真正值钱的地方——它在运行时【真的会检查】。

     Literal["东方","未来"] 的意思是：这个字段只能是这两个值之一，
     写别的立刻报错。这就叫"契约"。

任务：把下面那条坏数据修好，让它符合契约。
"""
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class World(BaseModel):
    id: str
    name: str
    # family 只允许这三个值中的一个
    family: Literal["东方", "未来", "现代"]


@app.get("/worlds")
def list_worlds():
    return [
        World(id="wuxia", name="武侠江湖", family="东方"),
        # TODO: 下面这条的 family 是 "东方大陆"，不在允许的取值里，会抛错。
        #       把它改成合法的值（"东方"）。
        World(id="xianxia", name="仙侠修真", family="东方大陆"),
    ]


# ─────────────────────────────────────────────
def verify():
    from fastapi.testclient import TestClient
    data = TestClient(app).get("/worlds").json()
    assert len(data) == 2, f"应该返回 2 条，实际 {len(data)} 条"
    for w in data:
        assert w["family"] in ("东方", "未来", "现代"), f'family={w["family"]!r} 不在允许取值里'
