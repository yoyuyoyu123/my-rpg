"""
练习 06 · 第一个数据模型
========================
概念：到目前为止你返回的都是 dict —— 没人管里面有什么。
     Pydantic 模型可以规定"这种数据必须长什么样"。

     class World(BaseModel):
         id: str        ← 必须有 id，而且是字符串
         name: str      ← 必须有 name

     好处：写错了会立刻报错，而不是把烂数据发给前端。

任务：给 World 模型补上 family 字段（字符串），然后创建一个实例。
"""
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class World(BaseModel):
    id: str
    name: str
    # TODO 1: 在这里加一行，声明 family 字段，类型是 str


@app.get("/world")
def get_world():
    # TODO 2: 创建一个 World 实例并返回
    #   id="wuxia", name="武侠江湖", family="东方"
    #
    # 写法：World(id="...", name="...", family="...")
    return None


# ─────────────────────────────────────────────
def verify():
    from fastapi.testclient import TestClient
    fields = set(World.model_fields.keys())
    assert "family" in fields, f"World 模型还缺 family 字段，现在只有 {sorted(fields)}"
    data = TestClient(app).get("/world").json()
    assert data is not None, "/world 还返回 None，你还没创建 World 实例"
    assert data == {"id": "wuxia", "name": "武侠江湖", "family": "东方"}, f"返回的内容不对：{data!r}"
