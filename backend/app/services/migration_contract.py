"""迁移契约：把「必须发生的事」从模型判断改成程序保证。

为什么需要这一层
----------------
玩家在开局点了「穿越」。这是一个**确定性需求**——它必须发生，不是
「如果剧情自然演化到那里就发生」。但引擎此前把这件事整个交给了模型判断：
规划器读叙事、决定 premise_phase 要不要前进，程序只能观察和劝说。

四轮实测下来，模型「不推进」的方式是无穷的：

  第一轮  空转的计时器四回合刷到已抵达，玩家全程在原世界撸猫
  第二轮  反强推规则（2/3/4/8）把玩家点的单当成可选钩子，压着不许发生
  第三轮  停止点设在 purpose 兑现之前，每一幕都在兑现之前收场
  第四轮  专用约束「不得自行改成别的阶段」和硬规则 7 直接冲突，
          迁移只在模型违抗指令时前进——实测 4 次里 1 次、8 次里 2 次

每一轮都是真 bug，每一轮修完都验证生效，然后下一局冒出新的变种。
根因不是任何一条规则写错了，而是**架构把保证交给了没有保证能力的东西**。

这一层的做法
------------
程序拿回执行权，分两级：

  软 —— 每次规划都告诉规划器还剩几回合。模型有了可推理的调度信息，
        多数情况下它自己就会安排好，程序不必出手。
  硬 —— 预算用尽仍未落地时，程序**自己造一张场景卡**接管这一幕，
        写手必须照着写。

和第一轮那个失败的计时器的区别是决定性的：计时器推的是**账本**
（直接把 phase 改成 5，故事原地不动，于是写手同时收到「已经抵达」和
「在阳台撸猫」两条矛盾指令）。这里推的是**剧情**——程序下发的是一幕
真正要被写出来的戏，叙事和阶段一起走，不会分叉。

玩家的自主权并没有被拿走：他选择的是**如何应对**穿越，不是穿越是否
发生。那是他点单时就定下的前提。真正该防的「凭空塞入玩家没选的事件」
另有规则（硬规则 2/3/4）管，与这里无关。
"""
from __future__ import annotations

from typing import Any

# 从「穿越前提确立」到「必须已经落地」之间允许的回合数。
#
# 数字按小说的常规分寸取：穿越是第一章的事，不是第一卷的事。玩家点了
# 穿越却在原世界耗掉十几二十个回合，是实测里反复出现的抱怨。
# fast（快速迁移路线，默认开启）用下面这档；显式关掉的存档给双倍。
BUDGET_BY_PACE = {"short": 3, "medium": 5, "long": 8}
BUDGET_FALLBACK = 5
SLOW_ROUTE_MULTIPLIER = 2

# 阶段 4 = 首次落地。到这里就算穿越完成，程序不再接管。
LANDED_PHASE = 4


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def is_migration(premise_state: Any) -> bool:
    return isinstance(premise_state, dict) and premise_state.get("kind") == "transmigration"


def budget_total(premise_state: Any, pace: str) -> int:
    """这一局允许迁移占用多少回合。"""
    ps = premise_state if isinstance(premise_state, dict) else {}
    total = BUDGET_BY_PACE.get(str(pace or "").strip(), BUDGET_FALLBACK)
    # fast 缺省视为开启，与前端 normalizePremiseState 的处理一致。
    if ps.get("fast") is False:
        total *= SLOW_ROUTE_MULTIPLIER
    return max(1, total)


def turns_used(premise_state: Any, turn: int) -> int:
    ps = premise_state if isinstance(premise_state, dict) else {}
    return max(0, _int(turn) - _int(ps.get("startedAt"), 0))


def turns_left(premise_state: Any, turn: int, pace: str) -> int:
    return budget_total(premise_state, pace) - turns_used(premise_state, turn)


def current_phase(premise_state: Any) -> int:
    ps = premise_state if isinstance(premise_state, dict) else {}
    return max(0, min(5, _int(ps.get("phase"), 0)))


def should_force(premise_state: Any, turn: int, pace: str) -> bool:
    """预算已经用尽、而玩家还没落地。"""
    if not is_migration(premise_state):
        return False
    if current_phase(premise_state) >= LANDED_PHASE:
        return False
    return turns_left(premise_state, turn, pace) <= 0


# ── 干预动作阶梯 ────────────────────────────────────────────────
#
# 搜索式 drama management 把「干预」拆成五类动作（Nelson & Mateas 在
# 交互小说 Anchorhead 上做的实验，见 docs/RESEARCH_MAP.md 第一节）：
#
#   causer      直接让某件事发生
#   denier      阻止某件事发生
#   temporer    临时阻止（必须配对 re-enabler）
#   re-enabler  解除临时阻止
#   hint        提示玩家往某个方向走
#
# 我们此前只有 causer，而且是最重的形态：预算用尽时程序接管整幕。
# 结果是干预要么完全不发生、要么一次性夺走一整幕的作者权，中间没有档位。
# 文献的共识是 DM 应当尽量少侵入——接管应该是兜底，不是唯一手段。
#
# 这里补上 hint 和 temporer/re-enabler，形成一条阶梯：
#
#   剩余预算 > 一半      不干预
#   剩余 ≤ 一半          hint：每回合要求正文给出一个指向迁移入口的行动选项
#   剩余 ≤ 2            hint + temporer：禁止规划器开启新的非迁移剧情线
#   剩余 ≤ 0            causer：程序接管整幕（原有行为）
#   已落地               re-enabler：全部解除
#
# denier 我们没有实现，也不打算实现：它在文献里的用途是「阻止剧情过早
# 到达高潮」，而我们的问题恰恰相反（永远到不了）。硬要加只会增加一条
# 可能把玩家卡死的路径。需要时再说。

# 剩几回合开始压制新支线。取 2 是因为一幕的最短视野就是 2 回合
# （迁移途中的 floor_gap），少于这个数再压制已经来不及了。
TEMPORER_TURNS_LEFT = 2


class DMActions:
    """本回合该采取哪些干预动作。"""

    __slots__ = ("hint", "temporer", "causer", "turns_left", "total")

    def __init__(self, hint: bool, temporer: bool, causer: bool,
                 turns_left: int, total: int) -> None:
        self.hint = hint
        self.temporer = temporer
        self.causer = causer
        self.turns_left = turns_left
        self.total = total

    @property
    def any(self) -> bool:
        return self.hint or self.temporer or self.causer

    def labels(self) -> list[str]:
        out = []
        if self.hint:
            out.append("hint")
        if self.temporer:
            out.append("temporer")
        if self.causer:
            out.append("causer")
        return out

    def __repr__(self) -> str:  # 调试面板和测试失败信息里要看得懂
        return f"DMActions({'+'.join(self.labels()) or 'none'}, left={self.turns_left})"


def dm_actions(premise_state: Any, turn: int, pace: str) -> DMActions:
    """按剩余预算决定干预强度。

    已经落地（阶段 ≥ LANDED_PHASE）时全部关闭——这就是 re-enabler：
    临时压制必须有解除条件，否则会永久卡死被压制的那条线。文献特别
    强调 temporer 与 re-enabler 必须配对。
    """
    if not is_migration(premise_state) or current_phase(premise_state) >= LANDED_PHASE:
        return DMActions(False, False, False, 0, 0)
    total = budget_total(premise_state, pace)
    left = turns_left(premise_state, turn, pace)
    return DMActions(
        hint=left <= total / 2,
        temporer=left <= TEMPORER_TURNS_LEFT,
        causer=left <= 0,
        turns_left=left,
        total=total,
    )


def takeover_verify_note(previous_runtime: Any) -> str:
    """接管之后的下一次规划，必须先核对写手到底穿没穿。

    程序发完强制卡就把阶段标成已抵达，是「推账本不推剧情」的另一种形态
    ——我以为自己避开了它，其实只避开了一半：test_forced_scene_moves_the_
    story_not_just_the_ledger 检查的是**卡片**是不是一幕真戏，没有任何东西
    检查**写手**是不是真的照做了。

    实测那一局：接管当回合写手照旧写了回仓库拍照发微信，而程序已经标记
    已抵达，于是下一幕只能让玩家凭空出现在异世界的石板路上，中间一片空白。

    程序判断不了叙事有没有跨过去（正则实测 14 回合命中 0 次），但规划器
    读得到最近对话。所以这里把核对这件事显式交给它——向下修正本来就是
    采纳的，缺的只是有人提醒它去看。
    """
    prev = previous_runtime if isinstance(previous_runtime, dict) else {}
    scene = prev.get("current_scene")
    if not isinstance(scene, dict) or scene.get("premise_phase_forced") is not True:
        return ""
    return (
        "【核对上一幕】上一幕是程序接管的，要求当场完成穿越并落地。"
        "**请先读最近对话再填 premise_phase**：玩家真的到新世界了吗？\n"
        "· 到了——正常继续，规划新世界的场景。\n"
        "· 没到（正文仍在原世界，或者只写了玩家的日常动作）——**如实填写更低的阶段**，"
        "程序会采纳并重新接管。不要因为程序说已抵达就顺着写下去，"
        "那会让玩家凭空出现在异世界，中间一片空白。\n\n"
    )


def hint_directive(actions: DMActions) -> str:
    """hint 动作：提示**玩家**，不是提示模型。

    此前的 budget_note 是说给规划器听的（「你还剩几回合」），玩家在屏幕上
    看不到任何变化。真正的 hint 要落到玩家能点的东西上——结尾的行动选项里
    得有一个真的指向迁移入口，否则玩家根本不知道有这条路。

    这条每回合都发。规划器只在刷新场景卡时才跑（每 2-4 回合一次），
    靠它给提示会漏掉中间的回合；程序每回合都能保证。
    """
    if not actions.hint or actions.causer:
        return ""
    return (
        "\n\n【本回合行动选项要求】结尾给出的行动参考里，"
        "**必须有一个是指向当前那个迁移入口／异常的具体行动**"
        "（去看、去碰、去问、去接受都算，写成玩家可以直接照做的一句话）。"
        "其余选项照常给，不要把这一个写成唯一出路，也不要替玩家评价它好不好。"
    )


def temporer_note(actions: DMActions) -> str:
    """temporer 动作：临时压制新支线，说给规划器听。"""
    if not actions.temporer:
        return ""
    return (
        f"【临时压制·新支线】迁移只剩 {max(0, actions.turns_left)} 个回合的预算。"
        "本次规划**不要新开剧情线**——已有的线继续维护，但不要引入新的职业任务、"
        "邻里纠纷、商业机会这类和迁移无关的新线程。玩家落地之后自动解除。\n\n"
    )


def budget_note(premise_state: Any, turn: int, pace: str) -> str:
    """软提示：把剩余预算摆给规划器，让它自己安排。

    这是常态路径。规划器拿到「还剩 2 回合」这种可推理的信息，通常就会
    把本幕安排成决定性的一幕；程序接管只是兜底，不该是常态。
    """
    if not is_migration(premise_state):
        return ""
    phase = current_phase(premise_state)
    if phase >= LANDED_PHASE:
        return ""
    left = turns_left(premise_state, turn, pace)
    total = budget_total(premise_state, pace)
    if left <= 0:
        return (
            f"【迁移预算已用尽】玩家在第 {_int(premise_state.get('startedAt'), 0)} 回合就点了穿越，"
            f"到现在已经过去 {turns_used(premise_state, turn)} 回合，人还在阶段 {phase}。"
            "本幕**必须**把穿越走完并让玩家在新世界落地——这不是可以再铺垫一轮的事。"
            "如果你这一幕仍然只是加深征兆，程序会直接接管本幕。\n\n"
        )
    if left <= 2:
        return (
            f"【迁移预算】只剩 {left} 个回合，穿越必须完成（总预算 {total} 回合）。"
            "现在应当安排决定性的一幕，不要再规划新的铺垫。\n\n"
        )
    return f"【迁移预算】还有 {left} 个回合完成穿越（总预算 {total} 回合）。\n\n"


def forced_scene(premise_state: Any, turn: int, previous_scene: Any) -> dict:
    """程序接管本幕时下发的场景卡。

    关键在于它是**一幕要被写出来的戏**，不是一个被改写的数字。写手照着
    它写，阶段和叙事就一起走到了新世界；这正是当年那个计时器缺的东西。

    分寸按小说的常规做法：**转移过程压缩，抵达单独成幕**。

    这一幕只负责把玩家送过去，停在落地睁眼的那一刻，不描写新世界的环境
    ——那是下一幕的事，而且值得详写。实测过反面：一张略写卡把转移和抵达
    一起包了，第二个回合用「略写」写了 597 字的新世界环境，最该详写的
    第一眼被压扁了。

    因此落点填阶段 5（已抵达），不是 4（首次落地）：填 4 会让下一幕再规划
    一次「落地」，玩家看到的就是穿越隔了一回合才完成。ARRIVED_PHASE 仍然
    留在 4，那是「已经跨过去、不必再接管」的判据，两者用途不同。
    """
    ps = premise_state if isinstance(premise_state, dict) else {}
    prev = previous_scene if isinstance(previous_scene, dict) else {}
    situation = str(prev.get("situation") or "").strip()

    # 用玩家开局声明的触发方式与迁移形式来造这一幕。
    #
    # 此前这里完全没读 premise_state 里的 mechanism / trigger，只会写
    # 「此前积累的异常在这一刻收束」——可实测那一局根本没有积累任何异常
    # （故事在查一块带符号的布），于是写手无从下手，接管当回合照旧写了
    # 拍照发微信，而程序已经把阶段标成已抵达，下一幕只能让玩家凭空出现在
    # 异世界的石板路上。玩家的原话是「莫名其妙搬箱子触发了」。
    #
    # 程序手里明明有「触发=正常生活中的睡眠或非自愿失去意识」这句话，
    # 不用它就等于自己撕毁玩家点的单。
    trigger = str(ps.get("trigger") or "").strip()
    mechanism = str(ps.get("mechanism") or "").strip()
    if trigger:
        bridge = (
            (f"{situation[:140]}——" if situation else "")
            + f"本局开局就定下的触发方式在此刻发生：{trigger[:120]}。"
            "它不需要此前有过任何征兆，就是这一刻发生的。"
        )
    elif situation:
        bridge = f"{situation[:160]}——此前积累的异常在这一刻收束，不再是征兆，它直接把玩家带走。"
    else:
        bridge = "此前已经出现的异常在这一刻收束，不再是征兆——它直接把玩家带走。"

    purpose = "本幕完成穿越：玩家离开原世界，穿过转移过程，落在新世界站稳并睁开眼。"
    if mechanism:
        purpose += f"迁移形式按开局设定：{mechanism[:120]}。"

    return {
        "id": f"crossing-{turn}",
        "title": "穿过去",
        "situation": situation or "玩家所处的日常场景。",
        "purpose": purpose,
        "causal_bridge": bridge,
        "active_thread_ids": [],
        "participant_intents": {},
        "available_information": [],
        "causal_event_ids": [],
        "affordances": ["在被带走的瞬间做出反应", "落地后开口说话"],
        "allowed_developments": ["穿越发生并完成", "玩家在新世界站稳并睁开眼"],
        "forbidden": [
            "把本幕写成又一次征兆、预感或前兆",
            "本幕结束时玩家仍然留在原世界",
            "逐步描写转移过程的每一层感受",
            "详细铺开新世界的环境——落地的第一眼留给下一幕详写",
            "替玩家决定他到达后的身份、能力或立场",
        ],
        "soft_commitment_ids": [],
        "pressure_budget": 3,
        "mystery_budget": 1,
        # 转移过程本身是纯过程，正是略写该管的东西。
        "narration": "summary",
        "summary_target": "跨过阈限、穿过转移过程，停在落地站稳、睁开眼的那一刻；新世界的样子留给下一幕。",
        "stop_points": ["玩家在新世界站定睁眼之后，轮到他决定下一步时。"],
        # 下一回合就重新规划：接管只负责这一幕，之后交还给规划器。
        "refresh_after_turn": _int(turn) + 1,
        # 填 5（已抵达）而不是 4：填 4 会让下一幕再规划一次「落地」，
        # 玩家看到的就是穿越隔了一回合才完成。见本函数 docstring。
        "premise_phase": 5,
        # 程序下的令，不是模型提案——前端的 +1 钳制不适用。
        "premise_phase_forced": True,
        "status": "active",
    }
