"""
提示词编译测试
==============
这是整个后端里最不能出错的一块：提示词差一个字，模型行为就会变，
而这种变化没有报错、只会表现为「玩起来好像有点不对」——最难查的那一类。

所以这里锁的不是「大概对」，是具体的结构位置：
哪一段在缓存前缀区、哪一段在动态区、什么条件下出现什么内容。
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.worlds import WORLDS  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas.turn import TurnContext  # noqa: E402
from app.services.prompt_builder import (  # noqa: E402
    active_rule_packs, build_system_prompt, debug_hash,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def ctx(**kw) -> TurnContext:
    base = {"world_id": "wuxia", "pace": "long", "turns": 0,
            "game_state": {"revealed": False}}
    base.update(kw)
    return TurnContext(**base)


# ── 与前端旧实现的一致性锚点 ────────────────────────────────────

def test_debug_hash_matches_js():
    """
    FNV-1a 32 位，必须和前端 debugHash 逐位一致——
    它的值会写进提示词正文（设定哈希），对不上就等于提示词变了。
    这几个期望值是从浏览器里跑前端实现取回来的。
    """
    assert debug_hash("") == "811c9dc5"
    assert debug_hash("a") == "e40c292c"
    assert debug_hash("hello") == "4f9f2cab"
    # 中文要单独锚一条：JS 的 charCodeAt 给的是 UTF-16 码元，
    # Python 的 ord 给的是码点，BMP 内两者一致——这条就是在盯住这个前提
    assert debug_hash("武侠") == "815cd0bb"
    assert debug_hash("陈家渡·测试") == "cab1d527"


# ── 每个世界都要能编译出东西 ────────────────────────────────────

@pytest.mark.parametrize("world_id", list(WORLDS))
def test_every_world_compiles(world_id: str) -> None:
    """
    空串是个危险的返回值：它会让「前后端输出一致」的对拍变成假通过。
    所以每个世界都必须编译出实质内容。
    """
    sp = build_system_prompt(ctx(world_id=world_id))
    assert len(sp) > 3000
    assert "【世界包】" in sp
    assert "【角色卡与状态协议" in sp


def test_unknown_world_returns_empty() -> None:
    """世界不存在时返回空串，由调用方决定怎么处理，不在这里抛异常。"""
    assert build_system_prompt(ctx(world_id="根本没有这个世界")) == ""
    assert build_system_prompt(ctx(pace="不存在的篇幅")) == ""


# ── 缓存前缀区不能被污染 ────────────────────────────────────────

def test_cache_prefix_is_stable_across_turns() -> None:
    """
    固定前缀区每回合必须完全相同，否则各家 API 的 context cache 全部失效。
    随回合变化的内容（角色状态、大纲、事实库）只能待在动态区。
    """
    def common_prefix(a: str, b: str) -> int:
        n = 0
        while n < min(len(a), len(b)) and a[n] == b[n]:
            n += 1
        return n

    early = build_system_prompt(ctx(turns=3, game_state={"revealed": True}))
    later = build_system_prompt(ctx(
        turns=40, outline="主角要重开铁匠铺", names="地名:陈家渡",
        game_state={"revealed": True, "attrs": {"力量": 5}, "loc": "陈家渡"},
        lore_context="【已确立的设定】[person] 吴四娘：职业=洗衣妇",
    ))

    # 断言结构而不是一个拍脑袋的字数：共同前缀必须完整覆盖三块资产。
    # 具体字数会随世界包正文改动而变，钉死数字只会变成一个假警报源。
    shared = early[:common_prefix(early, later)]
    assert "【文字RPG叙事契约】" in shared      # 核心规则
    assert "【世界包】" in shared                # 世界设定正文
    assert "【角色卡与状态协议" in shared        # 状态协议
    assert "【篇幅】" in shared

    # 反过来，随回合变化的内容一个都不许落进共享前缀。
    # 挑断言词要小心：核心规则里就拿「陈家渡」当好名字的范例，
    # 拿它做检查会误报，所以只用确实唯一属于动态区的标记。
    assert "主角要重开铁匠铺" not in shared      # 大纲
    assert "【命名表" not in shared               # 命名表
    assert "吴四娘" not in shared                 # 事实库注入
    assert "【权威角色状态" not in shared         # 角色状态摘要


def test_reveal_shifts_prefix_but_only_once() -> None:
    """
    「未揭示角色卡」那段就坐在缓存前缀区里，揭示后会消失——前缀因此变短。
    这是可以接受的：一局里只会发生一次，而且不可逆。
    这个测试是把这个已知代价钉在这里，避免以后有人误以为前缀恒定。
    """
    hidden = build_system_prompt(ctx(turns=3, game_state={"revealed": False}))
    shown = build_system_prompt(ctx(turns=3, game_state={"revealed": True}))
    n = 0
    while n < min(len(hidden), len(shown)) and hidden[n] == shown[n]:
        n += 1
    # 分歧点在状态协议之后：前面的规则与世界包仍然共享
    assert n > 3000
    assert "【未揭示角色卡" in hidden[n - 50:n + 200]


# ── 条件段落 ────────────────────────────────────────────────────

def test_first_chapter_only_on_turn_zero() -> None:
    assert "【互动式序章】" in build_system_prompt(ctx(turns=0))
    assert "【互动式序章】" not in build_system_prompt(ctx(turns=1))


def test_opening_text_only_on_turn_zero() -> None:
    o = "【本局开局变体：普通一天】从一件正常事务开始。"
    assert o in build_system_prompt(ctx(turns=0, opening_text=o))
    assert o not in build_system_prompt(ctx(turns=1, opening_text=o))


def test_unrevealed_sheet_block_appears_only_when_hidden() -> None:
    """角色卡未揭示时要禁止模型凭空造数值，揭示后这段就该消失。"""
    hidden = build_system_prompt(ctx(game_state={"revealed": False}))
    shown = build_system_prompt(ctx(game_state={"revealed": True}))
    assert "【未揭示角色卡——最高优先级】" in hidden
    assert "【未揭示角色卡——最高优先级】" not in shown


def test_state_summary_switches_shape_on_reveal() -> None:
    gs = {"revealed": True, "attrs": {"力量": 5}, "res": {"体力": 80},
          "loc": "陈家渡", "skills": [], "inv": [], "talents": [], "npcs": {}}
    sp = build_system_prompt(ctx(game_state=gs))
    assert "属性:力量5" in sp and "资源:体力80" in sp and "位置:陈家渡" in sp

    gs2 = dict(gs, revealed=False)
    sp2 = build_system_prompt(ctx(game_state=gs2))
    assert "角色卡尚未揭示" in sp2 and "属性:力量5" not in sp2


def test_world_prompt_strips_legacy_status_block() -> None:
    """世界包里的旧状态栏/任务段落已被状态协议取代，必须摘掉。"""
    # 标记文字要挑独特的：状态协议正文里本来就有「状态栏」三个字，
    # 直接拿它做断言会误判成没删干净
    sp = build_system_prompt(ctx(
        world_id="__custom__",
        custom_world_prompt="自定义世界正文。\n【状态栏】XX该删掉的旧状态栏XX\n【任务】XX该删掉的旧任务行XX",
    ))
    assert "自定义世界正文。" in sp
    assert "XX该删掉的旧状态栏XX" not in sp
    assert "XX该删掉的旧任务行XX" not in sp


# ── 规则包挂载 ──────────────────────────────────────────────────

def test_rule_packs_are_route_dependent() -> None:
    """没有穿越的局不该挂异世界规则包——那是纯噪音，还白烧 token。"""
    plain = [label for _, label, _ in active_rule_packs(ctx())]
    assert plain == ["ordinary-world", "npc-knowledge", "identity-freedom", "world:wuxia"]

    game = [label for _, label, _ in active_rule_packs(ctx(
        premise_state={"kind": "transmigration", "frame": "游戏世界"}))]
    assert "isekai-modern" in game
    assert "gameworld-variants" in game
    assert "world:gamerpunk" in game


def test_rule_packs_never_duplicate() -> None:
    """世界扩展和预设扩展可能指向同一个包，不能挂两遍。"""
    labels = [label for _, label, _ in active_rule_packs(
        ctx(world_id="horror", preset_id="cthulhu"))]
    assert len(labels) == len(set(labels))


# ── 迁移阶段 ────────────────────────────────────────────────────

@pytest.mark.parametrize("phase,marker", [
    (0, "ORIGIN_LIFE"), (1, "APPROACH"), (2, "THRESHOLD"),
    (3, "IN_TRANSIT"), (4, "FIRST_LANDING"), (5, "ARRIVED"),
])
def test_premise_phases(phase: int, marker: str) -> None:
    sp = build_system_prompt(ctx(premise_state={
        "kind": "transmigration", "phase": phase, "mechanism": "游戏弹窗"}))
    assert marker in sp


def test_premise_absent_when_not_transmigration() -> None:
    assert "跨世界迁移状态" not in build_system_prompt(ctx(premise_state={"kind": "none"}))


def test_stuck_phase_adds_pressure() -> None:
    """同一阶段停留过久要加压，否则穿越会一直卡在原世界日常。"""
    normal = build_system_prompt(ctx(premise_state={
        "kind": "transmigration", "phase": 0, "phaseTurns": 0}))
    stuck = build_system_prompt(ctx(premise_state={
        "kind": "transmigration", "phase": 0, "phaseTurns": 2}))
    assert "该迁移态已经停留过久" in stuck
    assert "该迁移态已经停留过久" not in normal


# ── 锁定设定的字符预算 ──────────────────────────────────────────

def test_pins_respect_character_budget() -> None:
    """
    用字符预算而不是条数上限：条数上限会被几条特别长的记录撑爆上下文。
    超预算时保留较新的那些。
    """
    pins = [{"text": f"第{i}条：" + "内容" * 300} for i in range(20)]
    sp = build_system_prompt(ctx(pins=pins))
    assert "【不可更改的锁定设定" in sp
    assert "第19条：" in sp        # 最新的留下了
    assert "第0条：" not in sp      # 最旧的被挤掉了


def test_pins_absent_when_empty() -> None:
    assert "【不可更改的锁定设定" not in build_system_prompt(ctx(pins=[]))


# ── 世界书检索 ──────────────────────────────────────────────────

def test_lorebook_keyword_retrieval() -> None:
    book = [
        {"name": "铁掌帮", "keywords": ["铁掌"], "text": "本地帮派。"},
        {"name": "常驻", "keywords": [], "text": "始终注入。", "always": True},
        {"name": "无关条目", "keywords": ["宇宙飞船"], "text": "不该出现。"},
    ]
    sp = build_system_prompt(ctx(lorebook=book, recent_text="我去找铁掌帮问问"))
    assert "本地帮派。" in sp
    assert "始终注入。" in sp        # always 条目不看关键词
    assert "不该出现。" not in sp


# ── HTTP 契约 ───────────────────────────────────────────────────

def test_endpoint_returns_prompt_and_packs(client: TestClient) -> None:
    r = client.post("/api/turn/prompt", json={
        "world_id": "wuxia", "pace": "long", "turns": 0,
        "game_state": {"revealed": False}})
    assert r.status_code == 200
    body = r.json()
    assert body["chars"] == len(body["system_prompt"]) > 3000
    assert body["hash"] and body["rules_hash"]
    assert "ordinary-world" in body["rule_packs"]


def test_endpoint_rejects_bad_body(client: TestClient) -> None:
    assert client.post("/api/turn/prompt", json={}).status_code == 422
