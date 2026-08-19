"""
服务层 · 状态结算
=================
给定「当前状态」和「模型申报的变化」，算出新的权威状态。

这一层是游戏里「程序说了算」的部分。模型只能*申报*变化，
真正生效与否、生效多少，由这里的规则决定：
    属性单回合最多 ±1，且只能改已有的键
    资源不越上限、不为负
    NPC 态度单回合最多 ±1，范围 -5..5
    天赋只有角色卡揭示后才能加
没有这层约束，聊上几十回合属性就会被模型一路加上去。

移植自前端 applyStatePatch。同样要求逐字节（这里是逐字段）一致：
物品与技能的 id 由名字哈希而来，存在存档里、还被 activeCoreId 引用——
后端要是算出另一套 id，老存档的物品就会凭空多出一份。
"""
import re
import time
from typing import Any

from app.domain.worlds import WORLDS

MAX_LEDGER = 300


# ── 与前端逐位一致的 id 哈希 ────────────────────────────────────

def _to_int32(x: int) -> int:
    x = int(x) & 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x


def stable_state_id(prefix: str, value: Any) -> str:
    """
    复刻前端 stableStateId。

    注意它和 debugHash 不是同一个哈希：这里用移位版的 FNV 乘法，
    而且 JS 里 `h+=...` 是浮点加法，h 会临时超出 32 位，
    直到下一轮的位运算才被截回 int32。这个细节必须照搬，
    差一点点算出来就是另一套 id，老存档会认不出自己的物品。
    """
    s = str(value or "item")
    h = 2166136261
    for ch in s:
        h = _to_int32(h) ^ ord(ch)
        shifts = (_to_int32(_to_int32(h) << 1) + _to_int32(_to_int32(h) << 4)
                  + _to_int32(_to_int32(h) << 7) + _to_int32(_to_int32(h) << 8)
                  + _to_int32(_to_int32(h) << 24))
        h = h + shifts
    return f"{prefix}_{_np_base36(int(h) & 0xFFFFFFFF)}"


def _np_base36(n: int) -> str:
    """JS 的 Number.prototype.toString(36)，小写。"""
    if n == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while n:
        n, r = divmod(n, 36)
        out = digits[r] + out
    return out


# ── 归一化 ──────────────────────────────────────────────────────

class _Missing:
    """
    表示「这个键根本不存在」。

    JS 里 null 和 undefined 是两回事：Number(null) 是 0，Number(undefined) 是 NaN，
    而原实现大量用 `x===undefined` 做判断。JSON 解析后两者在 Python 里都是 None，
    所以要用哨兵把它们分开，否则 {"quantity":null} 会被当成没传。
    """
    def __repr__(self) -> str:
        return "<missing>"


MISSING = _Missing()
NAN = float("nan")


def js_number(v: Any) -> float:
    """
    复刻 JS 的 Number(x)。

    这些换算看着琐碎，但模型输出里 null / [] / 空串 都真实出现过，
    换算差一点，物品数量就会从「归零删除」变成「保持 1 件」。
    """
    if isinstance(v, _Missing):
        return NAN
    if v is None:            # Number(null) === 0
        return 0.0
    if isinstance(v, bool):  # Number(true) === 1
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        t = v.strip()
        if t == "":          # Number('') === 0
            return 0.0
        try:
            return float(t)
        except ValueError:
            return NAN
    if isinstance(v, list):  # Number([]) === 0；Number([5]) === 5；再长就是 NaN
        if not v:
            return 0.0
        return js_number(v[0]) if len(v) == 1 else NAN
    return NAN               # 对象、函数等一律 NaN


def js_truthy(v: Any) -> bool:
    """
    复刻 JS 的真值判断。和 Python 最要命的差别：空数组和空对象在 JS 里是**真**。
    `spec.quantity||spec.qty||1` 这种写法碰上 quantity=[] 会取到 []，
    再 Number([]) 得 0 —— 用 Python 的真值判断会走成完全不同的分支。
    """
    if isinstance(v, _Missing) or v is None:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return not (v == 0 or v != v)
    if isinstance(v, str):
        return v != ""
    return True   # 数组、对象都是真值


def _is_finite(n: float) -> bool:
    return n == n and n not in (float("inf"), float("-inf"))


def _arr(v: Any) -> list:
    """
    复刻 `Array.isArray(x) ? x : []`。

    不能写成 `v or []`：模型把 inv_add 写成对象时，JS 会得到空数组，
    而 Python 会老老实实去遍历那个字典的键，两边行为就分岔了。
    """
    return v if isinstance(v, list) else []


def _has(d: Any, key: str) -> bool:
    """对应 `x[key] !== undefined`。显式的 null 算「有」。"""
    return isinstance(d, dict) and key in d


def _js_chain(*vals: Any) -> Any:
    """复刻 `a || b || c`：返回第一个 JS 真值，都不成立就返回最后一个。"""
    for v in vals[:-1]:
        if js_truthy(v):
            return v
    return vals[-1]


def clamp_num(v: Any, lo: float, hi: float, fallback: float) -> float:
    n = js_number(v)
    if not _is_finite(n):
        return fallback
    return max(lo, min(hi, n))


def _num(v: Any) -> float | None:
    """取有限数，拿不到就返回 None（对应前端的 !isFinite 分支）。"""
    n = js_number(v)
    return n if _is_finite(n) else None


def _int_or_float(n: float) -> int | float | None:
    """整数就存成整数，免得 JSON 里冒出 3.0 这种和前端对不上的写法。"""
    f = float(n)
    if f != f or f in (float("inf"), float("-inf")):
        return None       # NaN/Infinity 走 JSON 只能是 null，跟 JS 序列化一致
    return int(f) if f.is_integer() else f


def _get(o: Any, key: str) -> Any:
    """
    安全取属性。JS 里数组取不存在的属性得到 undefined，
    而 null.x 会抛异常——前端正是死在这上面（inv_add:[null]）。
    这里统一当作「没有这个属性」，是刻意比前端更耐操。
    """
    return o.get(key, MISSING) if isinstance(o, dict) else MISSING


def guess_item_category(name: str) -> str:
    name = str(name or "")
    if re.search(r"剑|刀|枪|弓|杖|刃|兵器|武器|匕首|火器", name):
        return "兵器"
    if re.search(r"甲|衣|袍|盔|靴|护腕|戒指|项链|饰物|装备", name):
        return "装备"
    if re.search(r"药|丹|散|丸|剂|绷带", name):
        return "药品"
    if re.search(r"饼|粮|肉|果|水|酒|茶|食物|面包", name):
        return "食物"
    if re.search(r"钱|银|金币|货币|积分|灵石", name):
        return "货币"
    if re.search(r"钥匙|令|信物|凭证|任务", name):
        return "关键物品"
    return "其他"


def guess_skill_category(name: str, world_id: str) -> str:
    name = str(name or "")
    if re.search(r"心法|内功|吐纳|冥想|魔力循环|协议|核心", name):
        return "核心"
    if re.search(r"步|身法|闪避|移动|潜行", name):
        return "身法"
    if re.search(r"被动|抗性|感知|洞察|专精|天赋", name):
        return "被动"
    w = WORLDS.get(world_id)
    return (w.skill_label if w else "") or "技能"


def _js_str(v: Any) -> str:
    """
    复刻 JS 的 String(x)。Python 的 str() 在这几处结果完全不同：
        None → "null"（不是 "None"）
        True → "true"（不是 "True"）
        1.0  → "1"（不是 "1.0"）—— 数量、系数写进存档时这个差别看得见
        []   → ""，[1,2] → "1,2"，{} → "[object Object]"
    """
    if isinstance(v, _Missing):
        return "undefined"
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        if v != v:
            return "NaN"
        return str(int(v)) if v.is_integer() else repr(v)
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return ",".join("" if x is None else _js_str(x) for x in v)
    return "[object Object]"


def _js_or(d: dict, keys: tuple[str, ...], fallback: Any) -> str:
    """复刻 `a || b || c || fallback` 的取值链：按 JS 真值判断挑第一个成立的。"""
    for k in keys:
        v = d.get(k, MISSING)
        if js_truthy(v):
            return _js_str(v)
    return _js_str(fallback)


def normalize_item(raw: Any, index: int = 0) -> dict:
    o: dict[str, Any] = {}
    if isinstance(raw, str):
        m = re.match(r"^(.*?)(?:\s*[x×]\s*(\d+(?:\.\d+)?))?$", raw.strip(), re.I)
        o["name"] = (m.group(1) if m and m.group(1) else raw).strip()
        o["quantity"] = float(m.group(2)) if m and m.group(2) else 1
    elif isinstance(raw, dict):
        o = dict(raw)

    o["name"] = _js_or(o, ("name", "label", "id"), f"物品{index + 1}").strip()[:60]
    o["id"] = str(o["id"]) if js_truthy(o.get("id", MISSING)) \
        else stable_state_id("item", o["name"])
    o["category"] = _js_or(o, ("category", "type"), guess_item_category(o["name"]))[:20]
    # quantity 用的是 ===undefined 判断，null 要落到 Number(null)=0 而不是默认 1
    qty = o.get("quantity", MISSING)
    if isinstance(qty, _Missing):
        qty = 1 if isinstance(o.get("qty", MISSING), _Missing) else o["qty"]
    o["quantity"] = _int_or_float(clamp_num(qty, 0, 999999, 1))
    o["description"] = _js_or(o, ("description", "desc"), "")[:500]
    o["equipped"] = js_truthy(o.get("equipped", MISSING))
    cons = o.get("consumable", MISSING)
    o["consumable"] = (bool(re.search(r"食物|药品", o["category"]))
                       if isinstance(cons, _Missing) else js_truthy(cons))
    tags = o.get("tags")
    o["tags"] = [str(t) for t in tags[:8]] if isinstance(tags, list) else []
    # 原样保留传进来的其它键。前端是 Object.assign({}, raw) 起手的，
    # 所以 {name:'干粮', delta:2} 会留下一个多余的 delta 字段。
    # 这算个小瑕疵，但它已经写进现有存档了——这次是迁移不是改行为，
    # 要清理得单独做成一次看得见的改动。
    return o


def normalize_skill(raw: Any, world_id: str, index: int = 0) -> dict:
    o = {"name": raw} if isinstance(raw, str) else (
        dict(raw) if isinstance(raw, dict) else {})
    o["name"] = _js_or(o, ("name", "label", "id"), f"技能{index + 1}").strip()[:60]
    o["id"] = str(o["id"]) if js_truthy(o.get("id", MISSING)) \
        else stable_state_id("skill", o["name"])
    o["category"] = _js_or(o, ("category", "type"),
                           guess_skill_category(o["name"], world_id))[:20]
    o["realm"] = _js_or(o, ("realm", "rank"), "初学")[:20]
    coef = o.get("coefficient", MISSING)
    o["coefficient"] = _int_or_float(
        clamp_num(1 if isinstance(coef, _Missing) else coef, 0, 5, 1))
    prof = o.get("proficiency", MISSING)
    if isinstance(prof, _Missing):
        prof = 0 if isinstance(o.get("mastery", MISSING), _Missing) else o["mastery"]
    o["proficiency"] = _int_or_float(clamp_num(prof, 0, 100, 0))
    o["attribute"] = _js_or(o, ("attribute", "attr"), "")[:20]
    o["description"] = _js_or(o, ("description", "desc"), "")[:600]
    o["active"] = js_truthy(o.get("active", MISSING))
    return o   # 同 normalize_item：其它键原样保留


def normalize_inventory(items: Any) -> list[dict]:
    """合并同名同 id 的条目——否则模型换个说法就会造出重复物品。"""
    out: list[dict] = []
    src = items if isinstance(items, list) else []
    for x in (normalize_item(i, n) for n, i in enumerate(src)):
        if not (x["quantity"] > 0 and x["name"]):
            continue
        old = next((v for v in out if v["id"] == x["id"] or v["name"] == x["name"]), None)
        if old:
            old["quantity"] = _int_or_float(old["quantity"] + x["quantity"])
            if not old["description"] and x["description"]:
                old["description"] = x["description"]
            old["equipped"] = old["equipped"] or x["equipped"]
        else:
            out.append(x)
    return out


def normalize_skills(items: Any, world_id: str) -> list[dict]:
    out: list[dict] = []
    src = items if isinstance(items, list) else []
    for x in (normalize_skill(i, world_id, n) for n, i in enumerate(src)):
        if not x["name"]:
            continue
        old = next((v for v in out if v["id"] == x["id"] or v["name"] == x["name"]), None)
        if not old:
            out.append(x)
        elif x["description"] and not old["description"]:
            old["description"] = x["description"]
    return out


class StateEngine:
    """
    一次结算。

    做成类是因为整个过程要反复读写同一份 state 和同一本账本，
    用函数传参会把每个 helper 都变成三参数。
    """

    def __init__(self, state: dict, world_id: str, turn: int):
        self.s = state
        self.world_id = world_id
        self.turn = turn
        self.now_ms = int(time.time() * 1000)

    # ── 账本 ────────────────────────────────────────────────────
    def ledger(self, type_: str, ref: str, note: str, delta: Any = None) -> None:
        """
        每一次数值变动都记一条。玩家发现数字不对时，这是唯一能回答
        「什么时候、因为什么变的」的地方。
        """
        if not isinstance(self.s.get("ledger"), list):
            self.s["ledger"] = []
        self.s["ledger"].append({
            "turn": self.turn, "time": self.now_ms, "type": str(type_ or "state"),
            "ref": str(ref or ""), "note": str(note or ""),
            "delta": None if delta is None else delta,
        })
        if len(self.s["ledger"]) > MAX_LEDGER:
            self.s["ledger"] = self.s["ledger"][-MAX_LEDGER:]

    # ── 查找 ────────────────────────────────────────────────────
    def find_item(self, ref: Any) -> dict | None:
        ref = str(ref or "").strip()
        return next((x for x in self.s["inv"] if x["id"] == ref or x["name"] == ref), None)

    def find_skill(self, ref: Any) -> dict | None:
        ref = str(ref or "")
        return next((x for x in self.s["skills"] if x["id"] == ref or x["name"] == ref), None)

    def sync(self) -> None:
        """整理集合并校正「当前运转」的技能，和前端 syncStateCollections 对齐。"""
        if not isinstance(self.s.get("loadout"), dict):
            self.s["loadout"] = {"activeCoreId": None}
        self.s["inv"] = normalize_inventory(self.s.get("inv"))
        self.s["skills"] = normalize_skills(self.s.get("skills"), self.world_id)
        if not self.s.get("skillCapacity"):
            self.s["skillCapacity"] = 20
        if not isinstance(self.s.get("ledger"), list):
            self.s["ledger"] = []

        active_id = self.s["loadout"].get("activeCoreId")
        active = next((x for x in self.s["skills"] if x["id"] == active_id), None)
        if active is None:
            active = next((x for x in self.s["skills"] if x.get("active")), None)
        self.s["loadout"]["activeCoreId"] = active["id"] if active else None
        for sk in self.s["skills"]:
            sk["active"] = bool(active) and sk["id"] == active["id"]

    # ── 物品 ────────────────────────────────────────────────────
    def item_delta(self, raw: Any, default_delta: Any = MISSING) -> None:
        # Object.assign({}, x)：x 是原始值时只会得到空对象，不会报错
        spec = normalize_item(raw) if isinstance(raw, str) else (
            dict(raw) if isinstance(raw, dict) else {})
        ref = _js_chain(_get(spec, "id"), _get(spec, "name"), MISSING)
        cur = self.find_item("" if isinstance(ref, _Missing) else ref)

        delta = js_number(spec.get("delta", MISSING))
        if not _is_finite(delta):
            if isinstance(default_delta, _Missing):
                delta = js_number(_js_chain(spec.get("quantity", MISSING),
                                            spec.get("qty", MISSING), 1))
            else:
                delta = default_delta
        # 这里不能提前 return：JS 里 NaN 会一路往下走，
        # 和 0 比较全为 false、参与加法后让数量变成 NaN，
        # 最后由 normalizeItem 兜底成 1。行为必须照搬。

        if cur is None and delta > 0:
            spec["quantity"] = delta
            cur = normalize_item(spec)
            self.s["inv"].append(cur)
            self.ledger("item", cur["name"], "获得", _int_or_float(delta))
            return
        if cur is None:
            return

        # Math.max(0, NaN) 在 JS 里是 NaN，而 Python 的 max(0, nan) 会返回 0——
        # 差在这里，数量就会从「变成 NaN 再被兜底成 1」变成「归零删除」
        total = js_number(_js_chain(cur.get("quantity", MISSING), 0)) + delta
        cur["quantity"] = NAN if total != total else _int_or_float(max(0, total))
        if js_truthy(_get(spec, "category")):
            cur["category"] = str(spec["category"])[:20]
        desc = _js_chain(_get(spec, "description"), _get(spec, "desc"), MISSING)
        if js_truthy(desc):
            cur["description"] = str(desc)[:500]
        if _has(spec, "equipped"):
            cur["equipped"] = js_truthy(spec["equipped"])
        self.ledger("item", cur["name"], "增加" if delta >= 0 else "减少", _int_or_float(delta))
        if cur["quantity"] <= 0:
            self.s["inv"] = [x for x in self.s["inv"] if x["id"] != cur["id"]]

    def item_upsert(self, raw: Any) -> None:
        if not raw:
            return
        spec = normalize_item(raw)
        cur = self.find_item(spec["id"]) or self.find_item(spec["name"])
        if cur is None:
            self.s["inv"].append(spec)
            self.ledger("item", spec["name"], "新增档案", spec["quantity"])
            return
        raw_d = raw if isinstance(raw, dict) else {}
        for k in ("name", "category", "description", "equipped", "consumable", "tags"):
            alias = "desc" if k == "description" else k
            if _has(raw_d, k) or _has(raw_d, alias):
                cur[k] = spec[k]
        if _has(raw_d, "quantity") or _has(raw_d, "qty"):
            cur["quantity"] = spec["quantity"]
        self.ledger("item", cur["name"], "更新档案")

    # ── 技能 ────────────────────────────────────────────────────
    def skill_upsert(self, raw: Any) -> None:
        if not raw:
            return
        spec = normalize_skill(raw, self.world_id)
        cur = next((x for x in self.s["skills"]
                    if x["id"] == spec["id"] or x["name"] == spec["name"]), None)
        if cur is None:
            self.s["skills"].append(spec)
            cur = spec
            self.ledger("skill", cur["name"], "学会技能")
        else:
            raw_d = raw if isinstance(raw, dict) else {}
            for k in ("name", "category", "realm", "coefficient", "proficiency",
                      "attribute", "description"):
                alias = {"realm": "rank", "description": "desc"}.get(k, k)
                if _has(raw_d, k) or _has(raw_d, alias):
                    cur[k] = spec[k]
            self.ledger("skill", cur["name"], "更新技能")
        if isinstance(raw, dict) and raw.get("active") is True:
            self.s["loadout"]["activeCoreId"] = cur["id"]


def apply_patch(state: dict, patch: dict, *, world_id: str = "", turn: int = 0) -> dict:
    """
    把一份申报的变化结算进状态，返回新状态。

    不改传入的 state（调用方可能还要拿它做对比或回滚）。
    """
    import copy
    s = copy.deepcopy(state or {})
    eng = StateEngine(s, world_id, turn)
    if not isinstance(patch, dict):
        eng.sync()
        return s

    p = patch
    eng.sync()
    revealed = bool(s.get("revealed"))
    s.setdefault("attrs", {})
    s.setdefault("res", {})

    # 属性：只能改已有的键，且单回合最多 ±1 —— 否则聊几十回合就会被一路加上去
    if isinstance(p.get("attr_set"), dict) and revealed:
        for k, raw in p["attr_set"].items():
            v = _num(raw)
            if k not in s["attrs"] or v is None:
                continue
            old = _num(s["attrs"][k]) or 0
            target = round_half_up(v)
            s["attrs"][k] = int(max(0, min(20, max(old - 1, min(old + 1, target)))))

    if isinstance(p.get("attr_delta"), dict) and revealed:
        for k, raw in p["attr_delta"].items():
            d = _num(raw)
            if k not in s["attrs"] or d is None:
                continue
            step = max(-1, min(1, round_half_up(d)))
            s["attrs"][k] = int(max(0, min(20, (_num(s["attrs"][k]) or 0) + step)))

    # 资源：不为负，且不越上限
    caps = s.get("caps") or {}
    if isinstance(p.get("res_delta"), dict):
        for k, raw in p["res_delta"].items():
            d = _num(raw)
            if k not in s["res"] or d is None:
                continue
            nv = max(0, (_num(s["res"][k]) or 0) + d)
            cap = caps.get(k)
            s["res"][k] = _int_or_float(min(cap, nv) if cap else nv)
    if isinstance(p.get("res_set"), dict):
        for k, raw in p["res_set"].items():
            v = _num(raw)
            if k not in s["res"] or v is None:
                continue
            nv = max(0, v)
            cap = caps.get(k)
            s["res"][k] = _int_or_float(min(cap, nv) if cap else nv)

    # 物品
    # JS 里 typeof null === 'object'，数组也是 object——分支判断要照这个来
    def _is_js_object(v: Any) -> bool:
        return v is None or isinstance(v, (dict, list))

    # 注意末尾的 isFinite(q)?q:1 —— 取不到数量时退成 1 件，不是放弃这一条
    for it in _arr(p.get("inv_add")):
        q = js_number(_js_chain(_get(it, "quantity"), _get(it, "qty"),
                                _get(it, "delta"), 1)) if _is_js_object(it) else (
            js_number(normalize_item(it)["quantity"]))
        eng.item_delta(it, q if _is_finite(q) else 1)
    for it in _arr(p.get("inv_rm")):
        q = js_number(_js_chain(_get(it, "quantity"), _get(it, "qty"), 1)) \
            if _is_js_object(it) else js_number(normalize_item(it)["quantity"])
        eng.item_delta(it, -abs(q if _is_finite(q) else 1))
    for it in _arr(p.get("inv_upsert")):
        eng.item_upsert(it)

    if isinstance(p.get("inv_delta"), list):
        for x in p["inv_delta"]:
            d = js_number(_get(x, "delta"))
            eng.item_delta(x, d if (_is_finite(d) and d != 0) else 0)
    elif isinstance(p.get("inv_delta"), dict):
        for k, v in p["inv_delta"].items():
            d = js_number(v)
            eng.item_delta({"name": k, "delta": d if _is_finite(d) else NAN}, d)

    if isinstance(p.get("inv_set"), dict):
        for k, raw in p["inv_set"].items():
            cur = eng.find_item(k)
            n = js_number(raw)
            v = max(0, n if _is_finite(n) and n != 0 else 0)
            if cur:
                cur["quantity"] = _int_or_float(v)
                eng.ledger("item", cur["name"], "校准数量", _int_or_float(v))
            elif v > 0:
                eng.item_upsert({"name": k, "quantity": v})

    if isinstance(p.get("equip_set"), dict):
        for k, v in p["equip_set"].items():
            it = eng.find_item(k)
            if it:
                it["equipped"] = js_truthy(v)
                eng.ledger("equip", it["name"], "装备" if it["equipped"] else "卸下")

    # 技能
    for x in _arr(p.get("skill_add")):
        eng.skill_upsert(x)
    for x in _arr(p.get("skill_upsert")):
        eng.skill_upsert(x)
    for ref in _arr(p.get("skill_rm")):
        ref = (ref.get("id") or ref.get("name")) if isinstance(ref, dict) else ref
        sk = eng.find_skill(str(ref))
        if sk:
            s["skills"] = [x for x in s["skills"] if x["id"] != sk["id"]]
            if s["loadout"].get("activeCoreId") == sk["id"]:
                s["loadout"]["activeCoreId"] = None
            eng.ledger("skill", sk["name"], "失去技能")

    prog = p.get("skill_progress")
    if isinstance(prog, (list, dict)):
        rows = prog if isinstance(prog, list) else [
            {"name": k, "delta": v} for k, v in prog.items()]
        for x in rows:
            if not isinstance(x, dict):
                continue
            ref = _js_chain(x.get("id", MISSING), x.get("name", MISSING), "")
            sk = eng.find_skill("" if isinstance(ref, _Missing) else str(ref))
            if not sk:
                continue
            d = js_number(x.get("delta", MISSING))
            if _is_finite(d):
                sk["proficiency"] = _int_or_float(
                    clamp_num((js_number(sk["proficiency"]) or 0) + d, 0, 100, sk["proficiency"]))
                eng.ledger("skill_progress", sk["name"], "熟练度变化", _int_or_float(d))
            if js_truthy(x.get("realm", MISSING)):
                sk["realm"] = str(x["realm"])[:20]
            if _has(x, "coefficient"):
                sk["coefficient"] = _int_or_float(
                    clamp_num(x["coefficient"], 0, 5, sk["coefficient"]))

    if "active_skill" in p:
        ask = None if p["active_skill"] is None else eng.find_skill(str(p["active_skill"]))
        s["loadout"]["activeCoreId"] = ask["id"] if ask else None
        eng.ledger("loadout", ask["name"] if ask else "无",
                   "切换当前运转" if ask else "停止当前运转")

    # 天赋：角色卡揭示前不许加，否则会凭空给玩家安上没声明过的来历
    if not isinstance(s.get("talents"), list):
        s["talents"] = []
    for x in (_arr(p.get("talent_add")) if revealed else []):
        x = _js_str(x).strip()[:30]
        if x and x not in s["talents"]:
            s["talents"].append(x)
    for x in _arr(p.get("talent_rm")):
        x = _js_str(x).strip()
        s["talents"] = [v for v in s["talents"] if v != x]

    if js_truthy(p.get("loc", MISSING)):
        s["loc"] = _js_str(p["loc"])

    # NPC
    if not isinstance(s.get("npcs"), dict):
        s["npcs"] = {}
    if isinstance(p.get("npc_set"), dict):
        for n, raw in p["npc_set"].items():
            n = str(n).strip()
            if not n:
                continue
            v = raw if isinstance(raw, dict) else {}
            cur = s["npcs"].get(n) or {"rel": "", "att": 0, "note": "", "knows": []}
            if not isinstance(cur.get("knows"), list):
                cur["knows"] = []
            if js_truthy(v.get("rel", MISSING)):
                cur["rel"] = _js_str(v["rel"])[:12]
            att_raw = js_number(v["att"]) if _has(v, "att") else NAN
            att = att_raw if _is_finite(att_raw) else None
            if att is not None:
                # 态度单回合最多挪一格：关系不会因为一句话就从陌生变生死之交
                target = max(-5, min(5, round_half_up(att)))
                prev = js_number(cur.get("att", MISSING))
                prev = prev if _is_finite(prev) else 0
                target = min(target, prev + 1)
                target = max(target, prev - 1)
                cur["att"] = int(target)
            if js_truthy(v.get("note", MISSING)):
                cur["note"] = _js_str(v["note"])[:40]
            for f in _arr(v.get("knows_add")):
                f = _js_str(f).strip()[:80]
                if f and f not in cur["knows"] and len(cur["knows"]) < 30:
                    cur["knows"].append(f)
            for f in _arr(v.get("knows_rm")):
                f = _js_str(f).strip()
                cur["knows"] = [x for x in cur["knows"] if x != f]
            s["npcs"][n] = cur
    for n in _arr(p.get("npc_rm")):
        s["npcs"].pop(_js_str(n).strip(), None)

    eng.sync()
    return s


def round_half_up(x: float) -> int:
    """
    JS 的 Math.round：.5 一律向上（朝正无穷），
    而 Python 内建 round 是银行家舍入，-1.5 会变成 -2 而不是 -1。
    """
    import math
    return math.floor(x + 0.5)
