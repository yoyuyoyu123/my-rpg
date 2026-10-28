"""不依赖模型的规则结算。"""
from __future__ import annotations

import math
import secrets
from typing import Any

from app.schemas.rules import RuleActionIn, RuleActionOut, RuleCheckIn, RuleCheckOut


def resolve_check(req: RuleCheckIn) -> RuleCheckOut:
    die = req.die if req.die is not None else secrets.randbelow(100) + 1
    attr_value = max(0.0, min(20.0, float(req.attr_value)))
    bonus = max(-20.0, min(50.0, float(req.skill_bonus) + float(req.talent_bonus)))
    total = die + attr_value * 5 + bonus
    dc = max(1, min(100, int(req.dc)))
    outcome = "成功" if total >= dc else "失败"
    if total - dc >= 30:
        outcome = "大成功"
    elif dc - total >= 30:
        outcome = "大失败"
    return RuleCheckOut(
        action=str(req.action or "行动检定")[:40],
        attr=str(req.attr or "行动")[:20],
        attr_value=attr_value,
        skill=str(req.skill or "")[:60],
        die=die,
        total=total,
        dc=dc,
        outcome=outcome,
        success=outcome in ("成功", "大成功"),
    )


def _text(value: Any, limit: int = 120) -> str:
    return str(value or "").strip()[:limit]


def _number(value: Any, *, minimum: float = 0, maximum: float = 1_000_000) -> float | None:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(n) or n < minimum or n > maximum:
        return None
    return n


def _item_ref(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("item")
    if isinstance(raw, dict):
        return {k: _text(raw[k], 80) for k in ("id", "name") if raw.get(k)}
    item: dict[str, Any] = {}
    if payload.get("item_id"):
        item["id"] = _text(payload.get("item_id"), 80)
    if payload.get("item_name") or raw:
        item["name"] = _text(payload.get("item_name") or raw, 80)
    return item


def _inventory_quantity(state: dict[str, Any], item: dict[str, Any]) -> float:
    inv = state.get("inv") if isinstance(state, dict) else []
    if not isinstance(inv, list):
        return 0
    total = 0.0
    for row in inv:
        if not isinstance(row, dict):
            continue
        if (item.get("id") and row.get("id") == item["id"]) or (
            item.get("name") and row.get("name") == item["name"]
        ):
            total += _number(row.get("quantity"), maximum=1_000_000) or 0
    return total


def _quest_rows(quests: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bucket in ("main", "side"):
        values = quests.get(bucket) if isinstance(quests, dict) else []
        if isinstance(values, list):
            rows.extend(x for x in values if isinstance(x, dict))
    return rows


def resolve_action(req: RuleActionIn) -> RuleActionOut:
    """结算移动、交易、任务动作；不修改输入状态。"""
    if req.kind == "move":
        destination = _text(req.payload.get("destination") or req.payload.get("loc"), 120)
        if not destination:
            return RuleActionOut(accepted=False, kind=req.kind, message="缺少目的地", errors=["destination_required"])
        known = {_text(x, 120) for x in req.known_locations if _text(x, 120)}
        if known and destination not in known:
            return RuleActionOut(accepted=False, kind=req.kind, message="目的地尚未解锁", errors=[f"unknown_location:{destination}"])
        current = _text((req.state or {}).get("loc"), 120)
        if current == destination:
            return RuleActionOut(accepted=True, kind=req.kind, message="已经在该地点", effects={"clock_delta": 0})
        return RuleActionOut(
            accepted=True, kind=req.kind, message=f"已移动至{destination}",
            patch={"loc": destination}, effects={"clock_delta": 1},
        )

    if req.kind == "trade":
        payload = req.payload or {}
        direction = _text(payload.get("direction") or payload.get("side"), 10).lower()
        if direction not in {"buy", "sell"}:
            return RuleActionOut(accepted=False, kind=req.kind, message="交易方向无效", errors=["direction_required"])
        item = _item_ref(payload)
        if not item:
            return RuleActionOut(accepted=False, kind=req.kind, message="缺少交易物品", errors=["item_required"])
        quantity = _number(payload.get("quantity"), minimum=1, maximum=9999)
        price = _number(payload.get("unit_price"), minimum=0, maximum=1_000_000)
        if quantity is None or quantity != int(quantity):
            return RuleActionOut(accepted=False, kind=req.kind, message="数量必须是正整数", errors=["quantity_invalid"])
        if price is None:
            return RuleActionOut(accepted=False, kind=req.kind, message="单价无效", errors=["unit_price_invalid"])
        quantity = int(quantity)
        total = quantity * price
        currency = _text(payload.get("currency") or "coins", 30)
        resources = (req.state or {}).get("res") or {}
        if currency not in resources:
            return RuleActionOut(accepted=False, kind=req.kind, message="当前状态没有这种货币", errors=[f"currency_missing:{currency}"])
        balance = _number(resources.get(currency), minimum=0) or 0
        if direction == "buy" and balance < total:
            return RuleActionOut(accepted=False, kind=req.kind, message="货币不足", errors=["insufficient_funds"])
        if direction == "sell" and _inventory_quantity(req.state, item) < quantity:
            return RuleActionOut(accepted=False, kind=req.kind, message="物品数量不足", errors=["insufficient_item"])
        delta = -total if direction == "buy" else total
        item_delta = dict(item)
        item_delta["delta"] = quantity if direction == "buy" else -quantity
        return RuleActionOut(
            accepted=True, kind=req.kind, message=("购买完成" if direction == "buy" else "出售完成"),
            patch={"res_delta": {currency: delta}, "inv_delta": [item_delta]},
            effects={"total": total, "currency": currency, "clock_delta": 1},
        )

    payload = req.payload or {}
    op = _text(payload.get("op") or payload.get("action"), 12).lower()
    if op not in {"add", "complete", "abandon"}:
        return RuleActionOut(accepted=False, kind=req.kind, message="任务操作无效", errors=["quest_op_invalid"])
    raw = payload.get("quest") if isinstance(payload.get("quest"), dict) else payload
    name = _text(raw.get("name") or raw.get("title"), 160)
    qid = _text(raw.get("id"), 100)
    if not name and not qid:
        return RuleActionOut(accepted=False, kind=req.kind, message="缺少任务标识", errors=["quest_identity_required"])
    rows = _quest_rows(req.quests)
    found = next((q for q in rows if (qid and _text(q.get("id"), 100) == qid) or (name and _text(q.get("name") or q.get("title"), 160) == name)), None)
    if op == "add":
        if found:
            return RuleActionOut(accepted=False, kind=req.kind, message="任务已存在", errors=["quest_exists"])
        bucket = _text(raw.get("type") or raw.get("bucket") or "side", 10).lower()
        bucket = "main" if bucket in {"main", "主线"} else "side"
        row = {k: raw[k] for k in ("id", "name", "title", "description", "next_step") if raw.get(k) is not None}
        if not row.get("name") and row.get("title"):
            row["name"] = row["title"]
        row["done"] = False
        row["status"] = "active"
        return RuleActionOut(accepted=True, kind=req.kind, message="任务已登记", quest_patch={"add": [{"bucket": bucket, "quest": row}], "complete": [], "abandon": []})
    if not found:
        return RuleActionOut(accepted=False, kind=req.kind, message="任务不存在", errors=["quest_not_found"])
    target = {"id": found.get("id"), "name": found.get("name") or found.get("title")}
    return RuleActionOut(
        accepted=True, kind=req.kind, message=("任务已完成" if op == "complete" else "任务已放弃"),
        quest_patch={"add": [], "complete": [target] if op == "complete" else [], "abandon": [target] if op == "abandon" else []},
    )
