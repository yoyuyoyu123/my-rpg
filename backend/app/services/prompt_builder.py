"""
服务层 · 提示词编译
===================
把「一回合的运行时状态」编译成发给模型的 system prompt。

为什么这件事该在后端：
    组装逻辑要读世界包正文、规则常量、状态协议——这些是核心资产。
    只要组装还在前端，资产就必须随 index.html 一起发出去，
    /api/worlds 不下发 prompt 的设计就是空的。

移植原则：**输出必须与前端旧实现逐字节一致**。
    提示词里任何一个字的差异都会改变模型行为，而这种变化没有报错、
    只会表现为「玩起来好像有点不对」——最难查的那一类问题。
    所以这里刻意不做「顺手优化」，连拼接顺序和换行都照抄。
"""
from app.domain.decks import PACE_CONFIG, STATE_SCHEMAS
from app.domain.rules import (
    AGENCY_RULES, ANTI_MYSTERY, CORE_RULES, FIRST_CHAPTER, GAMEWORLD_VARIANTS,
    IDENTITY_FREEDOM, ISEKAI_MODERN, NPC_KNOWLEDGE_RULES, OPTION_RULES,
    PRESET_EXPANSION_KEYS, WORLD_EXPANSION_KEYS, WORLD_EXPANSIONS,
)
from app.domain.worlds import WORLDS
from app.schemas.turn import TurnContext

import re

# 这两段原本内联在前端的 buildSystemPrompt 里，跟着世界包一起走
STATE_PROTOCOL = (
    '【角色卡与状态协议——覆盖世界包旧状态栏要求】前端已经显示唯一权威角色卡，正文不要输出另一套方括号状态栏，'
    '也不要自行重建属性表。核心属性名固定，只有长期训练、升级或重大伤病确实发生时才能用attr_delta，单回合最多±1；'
    '资源只能修改已经存在的键。物品、技能与重要人物是有ID或稳定名称的结构化记录，不得只在正文里声称变化。\n'
    '真实变化必须在末尾申报：【STATE】{"attr_delta":{"已有属性名":1},"res_delta":{"已有资源名":-1},'
    '"inv_delta":[{"name":"物品原名","delta":-1}],"inv_upsert":[{"name":"新物品","category":"分类","quantity":1,'
    '"description":"稳定说明","equipped":false}],"equip_set":{"物品原名":true},"skill_upsert":[{"name":"技能原名",'
    '"category":"类别","realm":"境界","coefficient":1.0,"proficiency":0,"attribute":"关联属性",'
    '"description":"稳定效果说明"}],"skill_progress":[{"name":"技能原名","delta":2,"realm":"可选的新境界"}],'
    '"active_skill":"技能原名或null","talent_add":[],"talent_rm":[],"npc_set":{"NPC原名":{"rel":"与玩家的已确认关系",'
    '"att":0,"note":"一句话当前事实","knows_add":["该NPC新确认的具体事实"],"knows_rm":["该NPC已明确推翻的旧事实"]}},'
    '"npc_rm":[],"loc":""}【/STATE】。只写实际发生的字段；同名物品增加或消耗用inv_delta，不得重复造新名称；'
    '修炼必须更新skill_progress，学会技能必须提供完整档案；只有值得长期记住的具名人物初次建立关系或其关系、态度、'
    '现状、独立知情事实确实改变时才写npc_set，普通路人不登记。knows_add只能记录玩家当面对其说出口、'
    '该NPC直接观察并可靠确认、或剧情明确发生信息传递的事实；猜测、旁白知识和隐藏蓝图禁止写入。'
    'npc_rm只用于关系明确终结且不再需要追踪的人物。没有真实变化就不输出。普通对话、查看面板和整理记忆不消耗生理资源。'
    '任务仅在玩家明确接受、承诺或主动设定目标后登记。'
)

# 有结构化场景卡时，叙事模型不再兼任编剧。短规则比把全部类型库和
# 反例库反复塞进上下文更可靠，也给长正文留下更多注意力预算。
AGENT_WRITER_RULES = (
    "【场景写手契约】你是互动小说的场景写手，不是剧情规划器。程序已经给出当前场景卡。\n"
    "1. 先完整回应玩家刚才的具体行动，只写该行动的直接过程、环境反馈与在场人物反应；玩家输入是尝试，不是既成结果。\n"
    "2. 只能沿场景卡的因果桥、人物眼前意图与允许发展推进。不得新开剧情线、突然制造阴谋、天命、追杀、秘密组织、第二套穿越机制或无关奇观。\n"
    "3. 不替玩家说话、选择、答应、相信、恐惧、感动或总结其内心；在玩家需要作出下一项决定的位置停下。\n"
    "4. NPC只依据其亲历、被告知或职业常识行动。能直接说的信息正常说；不知道就是不知道，不用欲言又止和神秘暗示代替信息。\n"
    "5. 描写必须服务于眼前行动、空间判断、人物关系或可用信息。一个回合只保留一个主要焦点，删除与本回合无因果关系的景物、路人和背景事件。\n"
    "6. 已确立事实和权威状态优先。不得凭空修改身份、身体、种族、职业、物品、能力、地点、关系与历史。\n"
    "7. 结尾给 2-4 个真正不同且立刻可做的行动参考，并明确允许自由输入；这些不是剧情唯一入口。\n"
    "8. 正文自然完整，篇幅服从场景而不是凑字数。状态确有改变时才使用指定协议块；不要解释规则、规划器或场景卡。\n"
    "9. 场景卡会标明本幕**详写还是略写**，这是硬要求，不是建议。\n"
    "   详写：逐步展开，停在玩家要反应的地方。\n"
    "   略写：用一到两段把**整段过程**概括完，直接抵达场景卡给出的终点，"
    "然后停在那里等玩家。不要逐步描写过程中的每一步、每一种感官、每一个细微变化——"
    "略写的段落里，过程本身只值一两句话，笔墨留给它的**结果**。\n"
    "   判断标准是「这一幕出岔子会怎样」：不会怎样的事，写长了就是水。"
)

# 略写模式下额外追加的一段。写成独立常量，是因为它要压过写手的默认倾向：
# 模型天然喜欢把每个瞬间都展开，而「赶路、等待、传送」这类过程一旦逐步描写，
# 一段几百字的传送能占掉十几个回合。实测过：一次穿越的传送过程写了 11 个回合
# 约 4500 字，每回合只是换个感官细节重复同一件事。
SUMMARY_MODE_RULES = (
    "【本幕略写——最高优先级，压过上面第 1 条的「完整回应」】\n"
    "这一幕是纯过程，结果已经确定，不值得逐步展开。请用一到两段写完整段过程并抵达终点：\n"
    "· 过程本身最多两三句，只保留对后续真正有影响的细节；\n"
    "· 不要逐一描写沿途所见、身体感受的每一层变化、时间的每一段推移；\n"
    "· 不要为了「有画面感」把同一件事换角度再写一遍；\n"
    "· 玩家的行动仍然要被如实回应，但回应可以浓缩成结果，不必还原每一步；\n"
    "· 抵达终点后停下，把回合交还给玩家。"
)


def debug_hash(text: str) -> str:
    """
    FNV-1a 32 位。必须和前端 debugHash 完全一致——
    它的值会写进提示词（设定哈希），对不上就等于提示词变了。
    """
    h = 2166136261
    for ch in str(text or ""):
        h ^= ord(ch)
        # JS 的 Math.imul 是 32 位有符号乘法，Python 整数无限精度，要手动截断
        h = (h * 16777619) & 0xFFFFFFFF
    return f"{h:08x}"[-8:]


def _canon_summary(canon: dict[str, str]) -> str:
    if not canon:
        return ""
    return "；".join(f"字段「{k}」=「{v}」" for k, v in canon.items())


def _effective_preset_note(note: str, advanced: dict) -> str:
    """玩家在高级选项里定死了魔法/时代时，把预设里与之冲突的措辞摘掉。"""
    out = str(note or "")
    if advanced.get("magic"):
        out = re.sub(r"(?:低魔|高魔|无魔|魔法稀少|魔法普及)[、，]?", "", out)
    if advanced.get("era"):
        out = re.sub(r"(?:古代|中世纪|近代|现代|近未来|远未来)[、，]?", "", out)
    return re.sub(r"^[、，；。\s]+|[、，；\s]+$", "", out).strip()


def _state_summary(gs: dict) -> str:
    """
    权威角色状态摘要。

    这是「程序说了算」的那份事实——叙事不得与它矛盾。
    未揭示角色卡时输出的是另一套内容，不能混。
    """
    npcs = gs.get("npcs") or {}
    nk = list(npcs.keys())
    npc_text = ""
    if nk:
        parts = []
        for n in nk[-12:]:
            v = npcs.get(n) or {}
            kn = v.get("knows") if isinstance(v.get("knows"), list) else []
            note = f",{v['note']}" if v.get("note") else ""
            parts.append(
                f"{n}({v.get('rel') or '?'},态度{int(v.get('att') or 0)}{note},"
                f"已知={'／'.join(kn) if kn else '无额外秘密'})"
            )
        npc_text = "人物认知(各自独立，不得共享):" + "；".join(parts)

    if not gs.get("revealed"):
        hidden = ["角色卡尚未揭示：不得假定属性值、职业Build或异世界面板，不得进行数值检定。"]
        inv = gs.get("inv") or []
        if inv:
            hidden.append("已确认背包:" + "、".join(f"{x['name']}×{x['quantity']}" for x in inv))
        skills = gs.get("skills") or []
        if skills:
            hidden.append("已由剧情明确获得但尚未建卡的能力:" + "、".join(s["name"] for s in skills))
        if gs.get("loc"):
            hidden.append("位置:" + gs["loc"])
        if npc_text:
            hidden.append(npc_text)
        return "｜".join(hidden)

    parts: list[str] = []
    attrs = gs.get("attrs") or {}
    if attrs:
        parts.append("属性:" + "/".join(f"{k}{v}" for k, v in attrs.items()))
    skills = gs.get("skills") or []
    if skills:
        parts.append("技能索引:" + "、".join(
            f"{s['name']}{{{s.get('category','')},{s.get('realm','')},系数{s.get('coefficient','')},"
            f"熟练{s.get('proficiency','')}%"
            f"{',' + s['attribute'] if s.get('attribute') else ''}"
            f"{',当前运转' if s.get('active') else ''}}}"
            for s in skills
        ))
    talents = gs.get("talents") or []
    if talents:
        parts.append("天赋(完整列表):" + "、".join(talents))
    inv = gs.get("inv") or []
    if inv:
        parts.append("背包索引:" + "、".join(
            f"{x['name']}×{x['quantity']}{{{x.get('category','')}"
            f"{',已装备' if x.get('equipped') else ''}}}"
            for x in inv
        ))
    res = gs.get("res") or {}
    if res:
        parts.append("资源:" + "/".join(f"{k}{v}" for k, v in res.items()))
    if gs.get("loc"):
        parts.append("位置:" + gs["loc"])
    if npc_text:
        parts.append(npc_text)
    return "｜".join(parts)


def _premise_directive(ps: dict, prefs: dict) -> str:
    """
    跨世界迁移的阶段指令。

    分阶段推进是为了不让「穿越」被一段摘要一口气写完——
    每个可反应的节点都要交还玩家。
    """
    if not ps or ps.get("kind") != "transmigration":
        return ""

    n = int(ps.get("phase") or 0)
    held = int(ps.get("phaseTurns") or 0)
    fast = ps.get("fast") is True
    extra = f"玩家硬性备注：{prefs['extra']}。" if prefs.get("extra") else ""

    base = (
        "【跨世界迁移状态——程序持久化事实；这里的英文状态名不是剧情内的阶段、协议或组织编号】"
        "本局已经选定游戏世界/异世界穿越为故事前提。固定迁移形式："
        f"{ps.get('mechanism') or '未额外限定'}。固定触发："
        f"{ps.get('trigger') or '由场景自然形成'}。{extra}"
        "这些固定事实不得被相似的科技系统、秘密机构、梦境、实验或另一套阶段协议替代。"
        "不得替玩家作出点击、接受、上线或心理决定；但外部事件可以自行发生。"
        "玩家拒绝或忽略某个入口，只会改变穿越路径与当下反应，不会取消本局前提，也不得把同一入口换皮重发。"
        "每回合仍只推进一个迁移态并在可反应处停下。"
    )
    if fast:
        base += "这是快速迁移路线：原世界只保留一个可感知起点，不扩写职业生活；已有触发或玩家回应后，按阶段直接推进到阈限、转移和首次落地。"

    if n == 0:
        return base + "当前迁移态=ORIGIN_LIFE（原世界生活）。只建立生活与第一项眼前刺激，不完成穿越。" + (
            "该迁移态已经停留过久：本回合必须让第一项可回应的外部刺激抵达玩家面前，然后立刻停下。"
            if held >= 2 else ""
        )
    if n == 1:
        return base + (
            "当前迁移态=APPROACH（回应与逼近）。完整回应玩家刚才的行动；若玩家主动触发，可让转移征兆开始。"
            "若玩家忽略或拒绝入口，世界照常运转，但随后由与该选择无关的客观外部变化接管穿越路径，"
            "不能劝回同一按钮。"
        ) + (
            "该迁移态已经停留过久：本回合必须出现可感知且不可逆的外部阈限征兆，不能继续现实生活支线。"
            if held >= 2 else ""
        )
    if n == 2:
        return base + (
            "当前迁移态=THRESHOLD（阈限事件）。玩家此前的拒绝已经生效，原入口作废；"
            "本回合必须让另一条客观穿越过程开始。这不是替玩家选择。重点描写过程，"
            "并在玩家仍能反应或观察的位置停下，不能继续写现实生活支线。"
            "严禁把THRESHOLD解释成剧情中某个机构的“阶段2”。"
        )
    if n == 3:
        return base + (
            "当前迁移态=IN_TRANSIT（转移途中）。完整描写时间、空间、身体、意识或数据层面的过渡，"
            "让玩家能够尝试观察、挣扎、呼喊或保持不动；本回合不得退回普通现实日常，结尾接近或刚触及落点。"
        ) + (
            "该迁移态已经停留过久：本回合必须抵达新世界的最初落点，但只写首次感知，不替玩家探索。"
            if held >= 2 else ""
        )
    if n == 4:
        return base + (
            "当前迁移态=FIRST_LANDING（首次落地）。本回合进入新世界并只呈现最初可感知环境与一个迫近的互动点；"
            "不得总结“已经适应数日”，不得一次讲完身份、系统和世界说明。"
        )
    return base + (
        "当前迁移态=ARRIVED（穿越完成）。故事重心留在新世界；身份、身体、游戏规则和能力只能由玩家逐项探索，"
        "不自动全知。不得又把主角送回原世界重演入口，除非玩家日后主动追求返乡。"
    )


def _agent_mode(ctx: TurnContext) -> bool:
    runtime = ctx.story_runtime or {}
    return isinstance(runtime.get("current_scene"), dict) and bool(runtime["current_scene"].get("id"))


PREMISE_LABELS = ["原世界生活", "入口逼近", "阈限事件", "转移途中", "首次落地", "已经抵达"]

# 同一阶段停留多少回合之后开始加压。
# 之前这个压力阀被拆掉了（注释写着「节拍由场景卡决定」），但场景卡永远不会
# 自己决定穿越——规划器被要求「不要为了赶进度虚报」。结果是玩家选了穿越
# 却几十回合停在原世界。压力要加回来，但要加在提示词上，不能靠偷偷推进计数器。
PREMISE_STALL_TURNS = 3


def premise_stall_note(ps: dict) -> str:
    """在同一迁移阶段停留过久时给出的加压文字。空串表示不需要加压。"""
    if not ps or ps.get("kind") != "transmigration":
        return ""
    try:
        phase = max(0, min(5, int(ps.get("phase") or 0)))
        held = int(ps.get("phaseTurns") or 0)
    except (TypeError, ValueError):
        return ""
    if phase >= 5 or held < PREMISE_STALL_TURNS:
        return ""

    nudge = {
        0: "本场景必须让第一项可回应的迁移征兆真正抵达玩家面前，然后在玩家能反应处停下。",
        1: "本场景必须出现可感知且不可逆的外部阈限征兆，不能再写现实生活支线。",
        2: "本场景必须让客观的穿越过程开始，重点写过程本身。",
        3: "本场景必须抵达新世界的最初落点。",
        4: "本场景必须呈现新世界的最初可感知环境。",
    }[phase]

    # 停得更久时必须换一句话说。
    # 实测踩过的坑：征兆第 0 回合就出现了，但阶段判定没认出来，于是往后每回合
    # 都在重复「让第一项征兆抵达」——模型照做，就把同一团光越描越细，
    # 连着八回合都是「戳它、碰它、捧着它」。指令已经被满足却还在重复，
    # 模型唯一能做的就是把它做得更彻底。
    if held >= PREMISE_STALL_TURNS * 2:
        # 升级档要说的是「结束当前阶段」，不能再重复上面那句 nudge——
        # 那句要求的事早就做过了，再说一遍正是模型把同一团光越描越细的原因。
        escalated = {
            0: "征兆已经出现过了，本场景必须让它产生实际后果并把玩家推向阈限，"
               "不能停留在观察、触碰、感受的循环里。",
            1: "逼近阶段该结束了，本场景必须发生不可逆的阈限事件。",
            2: "阈限已经发生，本场景必须让转移过程真正开始。",
            3: "转移该落地了，本场景必须抵达新世界。",
            4: "落地已经完成，本场景必须让玩家开始真正身处新世界的日常。",
        }[phase]
        return (
            f"【迁移严重停滞】已在「{PREMISE_LABELS[phase]}」停留 {held} 回合。"
            "不要再把同一个对象或同一种感受反复加深、细化、重新呈现——那不是推进。"
            f"{escalated}"
            "如果玩家一直没有主动推进，就让外部事件自行发生并把局面带过去；"
            "玩家仍然自由选择如何应对，但世界不会永远停在同一帧。"
        )

    return (
        f"【迁移已停滞】已在「{PREMISE_LABELS[phase]}」停留 {held} 回合，"
        f"玩家选择的是穿越前提，不能一直停在这里。{nudge}"
        "这不是替玩家做决定——外部事件可以客观发生，玩家仍然自由选择如何应对。"
    )


def _agent_premise_directive(ps: dict) -> str:
    """
    规划模式下的迁移状态。节拍主要由场景卡决定，但停滞过久时要加压——
    没有这个阀门，「选了穿越却永远不穿越」会稳定复现。
    """
    if not ps or ps.get("kind") != "transmigration":
        return ""
    phase = max(0, min(5, int(ps.get("phase") or 0)))
    fast = ps.get("fast") is True
    stall = premise_stall_note(ps)
    return (
        "【迁移进度事实】当前=" + PREMISE_LABELS[phase]
        + "。迁移形式=" + str(ps.get("mechanism") or "未限定")
        + "；触发=" + str(ps.get("trigger") or "自然形成")
        + ("；这是快速迁移路线，不扩写原世界职业生活，已有触发后直接安排下一阶段" if fast else "")
        + "。只按当前场景卡推进，不为赶阶段重复入口或突然跳步；玩家拒绝过的入口继续视为无效。"
        + (("\n" + stall) if stall else "")
    )


def _story_scene_summary(runtime: dict) -> str:
    """只把公开、可执行的场景信息交给写手，幕后原因留在规划器。"""
    scene = runtime.get("current_scene") if isinstance(runtime, dict) else None
    if not isinstance(scene, dict):
        return ""
    lines = [
        "【当前场景卡——只写这一幕，不自行规划后续】",
        "场景:" + str(scene.get("title") or scene.get("id") or "未命名"),
        "眼前处境:" + str(scene.get("situation") or ""),
        "本场作用:" + str(scene.get("purpose") or ""),
        "可见因果桥:" + str(scene.get("causal_bridge") or ""),
        "强度预算:压力=" + str(scene.get("pressure_budget", 1))
        + "/4，悬疑=" + str(scene.get("mystery_budget", 0))
        + "/4。预算是上限而非配额，不必花完；禁止用力过猛的辞藻虚抬强度。",
        # 详写/略写要和场景标题、处境挨在一起，别让写手读到一半才知道该压缩
        "叙事密度:" + ("略写——一到两段带过整段过程"
                       if scene.get("narration") == "summary" else "详写——逐步展开"),
    ]
    if scene.get("narration") == "summary" and scene.get("summary_target"):
        lines.append("本幕要跨过并抵达:" + str(scene["summary_target"]))
    intents = scene.get("participant_intents") or {}
    if isinstance(intents, dict) and intents:
        lines.append("在场人物眼前意图:" + "；".join(f"{k}={v}" for k, v in list(intents.items())[:8]))
    for key, label in (
        ("available_information", "当前可公开信息"),
        ("affordances", "本幕可用行动空间"),
        ("allowed_developments", "允许的自然发展"),
        ("forbidden", "本幕明确禁止"),
        ("stop_points", "必须停下的交互点"),
    ):
        values = scene.get(key) or []
        if isinstance(values, list) and values:
            lines.append(label + ":" + "；".join(str(x) for x in values[:10]))
    causal_ids = scene.get("causal_event_ids") or []
    commitment_ids = scene.get("soft_commitment_ids") or []
    if causal_ids:
        lines.append("本幕因果依据:" + "、".join(str(x) for x in causal_ids[:8]))
    if commitment_ids:
        lines.append("需尊重的承诺/拒绝:" + "、".join(str(x) for x in commitment_ids[:8]))

    active = set(scene.get("active_thread_ids") or [])
    public_threads = []
    for thread in runtime.get("threads") or []:
        if not isinstance(thread, dict) or thread.get("id") not in active:
            continue
        bit = str(thread.get("title") or thread.get("id") or "")
        if thread.get("public_goal"):
            bit += "：" + str(thread["public_goal"])
        clues = thread.get("established_clues") or []
        if clues:
            bit += "（已公开=" + "／".join(str(x) for x in clues[:5]) + "）"
        public_threads.append(bit)
    if public_threads:
        lines.append("当前公开目标:" + "；".join(public_threads))
    lines.append("private_cause、未公开答案和未满足前置条件均未提供给你；禁止猜测补完。")
    return "\n".join(lines)


def active_rule_packs(ctx: TurnContext) -> list[tuple[str, str, str]]:
    """
    挑出当前路线用得上的规则包，返回 (内部键, 展示名, 正文)。

    全部塞进去会稀释注意力，也白烧 token——
    比如没有穿越的局，异世界规则包就是纯噪音。

    展示名一并返回，是为了前端的调试追踪能显示「这一回合挂了哪几个包」
    而不必在前端再抄一份映射表——抄了就会漂移。
    """
    if _agent_mode(ctx):
        out = [("agent-writer", "agent-writer", AGENT_WRITER_RULES)]
        scene = (ctx.story_runtime or {}).get("current_scene") or {}
        if scene.get("narration") == "summary":
            # 只在略写时挂。详写场景挂上它是纯噪音，还会诱导模型压缩不该压缩的戏。
            out.append(("summary-mode", "summary-mode", SUMMARY_MODE_RULES))
        return out

    packs: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add(key: str, label: str, text: str) -> None:
        if not text or key in seen:
            return
        seen.add(key)
        packs.append((key, label, text))

    add("ordinary", "ordinary-world", ANTI_MYSTERY)
    add("knowledge", "npc-knowledge", NPC_KNOWLEDGE_RULES)
    add("identity", "identity-freedom", IDENTITY_FREEDOM)

    ps = ctx.premise_state or {}
    trans = ps.get("kind") == "transmigration"
    frame = str(ps.get("frame") or "") if trans else ""
    if trans:
        add("isekai", "isekai-modern", ISEKAI_MODERN)
    if re.search(r"游戏|穿书|原作", frame):
        add("gameworld", "gameworld-variants", GAMEWORLD_VARIANTS)
    if "游戏" in frame:
        add("exp-gamerpunk", "world:gamerpunk", WORLD_EXPANSIONS.get("gamerpunk", ""))

    preset_key = PRESET_EXPANSION_KEYS.get(ctx.preset_id)
    if preset_key:
        add("exp-" + preset_key, "preset:" + preset_key, WORLD_EXPANSIONS.get(preset_key, ""))
    world_key = WORLD_EXPANSION_KEYS.get(ctx.world_id)
    if world_key:
        add("exp-" + world_key, "world:" + world_key, WORLD_EXPANSIONS.get(world_key, ""))

    return packs


def _active_narrative_rules(ctx: TurnContext) -> str:
    return "\n\n".join(text for _, _, text in active_rule_packs(ctx))


def _relevant_lore(recent_text: str, lorebook: list[dict]) -> str:
    """世界书检索：只带回本回合文本命中关键词的条目。"""
    if not lorebook:
        return ""
    hay = (recent_text or "").lower()
    picked = []
    for chunk in lorebook:
        if chunk.get("always"):
            picked.append(chunk)
            continue
        kws = chunk.get("keywords") or []
        if any(str(kw).lower() in hay for kw in kws):
            picked.append(chunk)
    picked = picked[:6]
    return "\n\n".join(f"[{c.get('name','')}] {c.get('text','')}" for c in picked)


def derived_name_table(ctx) -> str:
    """从已经存在的事实里推出命名表。

    为什么需要：命名表本来是死代码。前端只在模型输出 【命名表】…【/命名表】
    时才填 NAMES，而**没有任何一处提示词要求模型输出这个块**——全部引用都是
    「剥离它」「提取它（如果有）」「回灌它（如果非空）」。翻遍全部历史导出，
    这个块一次都没有产出过，于是 ctx.names 恒为空，命名一致性从未生效。

    与其加一条让写手每回合多输出一个块的指令（每回合都要付 token，而且模型
    经常漏），不如从系统本来就维护的权威事实里推：地点和 NPC 名字本来就在
    game_state 里。这样命名表零成本、且永远不会和状态栏对不上。
    """
    gs = ctx.game_state if isinstance(ctx.game_state, dict) else {}
    places = [str(gs.get("loc") or "").strip()]
    npcs = gs.get("npcs")
    people = [str(k).strip() for k in npcs][:20] if isinstance(npcs, dict) else []
    lines = []
    places = [p for p in places if p]
    if places:
        lines.append("地点：" + "、".join(dict.fromkeys(places)))
    if people:
        lines.append("人物：" + "、".join(dict.fromkeys(people)))
    return "\n".join(lines)


def build_system_prompt(ctx: TurnContext) -> str:
    """
    编译一回合的 system prompt。

    结构分两区，顺序不能动：
      固定前缀区（规则 + 世界包 + 状态协议）—— 每回合完全相同，用来命中各家的
                                              context cache
      动态区（本局设定 + 角色状态 + 事实库 + 检索结果）—— 随回合变化
    任何随回合变化的内容一旦挪进前缀区，整段缓存就失效了。
    """
    world = WORLDS.get(ctx.world_id)
    pace = PACE_CONFIG.get(ctx.pace)
    world_prompt_src = ctx.custom_world_prompt if world is None else world.prompt
    if (world is None and not ctx.custom_world_prompt) or not pace:
        return ""

    agent_mode = _agent_mode(ctx)
    sp = AGENT_WRITER_RULES if agent_mode else CORE_RULES
    canon = _canon_summary(ctx.player_canon)
    # 无论是否启用剧情规划 Agent，前端都依赖同一份选项协议把文本变成按钮。
    # 之前 agent_mode 只保留了“给 2-4 个参考”的语义要求，却漏掉精确格式，
    # 导致模型常写成 Markdown/【行动选项】而前端无法识别。
    sp += "\n\n" + OPTION_RULES
    if not agent_mode:
        sp += "\n\n" + AGENCY_RULES

    # 世界包里的旧状态栏/任务段落要摘掉——它们已经被下面的状态协议取代
    world_prompt = re.sub(r"\n【状态栏】[\s\S]*?(?=\n【任务】|$)", "", str(world_prompt_src or ""), count=1)
    world_prompt = re.sub(r"\n【任务】[^\n]*", "", world_prompt)
    sp += "\n\n【世界包】\n" + world_prompt
    sp += "\n" + STATE_PROTOCOL

    if not ctx.game_state.get("revealed"):
        schema = STATE_SCHEMAS.get(ctx.world_id) or STATE_SCHEMAS["__custom__"]
        sp += (
            "\n【未揭示角色卡——最高优先级】当前尚未建立数值。穿越前、游戏外或身份尚未由玩家说明时，"
            "按叙事常识表现普通人的能力，不显示异世界数值，不掷骰，不暗中预设职业、Build、技能或天赋。"
            "只有玩家明确主动查看状态/面板/自身能力，或玩家已经亲自完成使能力可被认识的操作时，"
            "才可在回复最末输出一次【SHEET_INIT】JSON【/SHEET_INIT】。仅抵达异世界、醒来、被召唤或看见提示不构成授权。"
            "初始化属性键必须且只能是：" + "、".join(schema["attrs"]) + "；数值0-10，根据玩家此前明确描述分配，"
            "未得到支持的一律为1。资源键必须且只能是：" + "、".join(schema["res"].keys()) + "。格式："
            '【SHEET_INIT】{"attrs":{},"res":{},"talents":[],"skills":[{"name":"名称","category":"类别",'
            '"realm":"境界","coefficient":1,"proficiency":0,"attribute":"关联属性","description":"效果"}]}'
            "【/SHEET_INIT】。没有确凿技能就返回空数组，不得补造玩家未声明的经历或专长。"
        )

    if ctx.preset_id and world and world.presets:
        pp = next((x for x in world.presets if x.id == ctx.preset_id), None)
        pn = _effective_preset_note(pp.note, ctx.prefs.get("advanced") or {}) if pp else ""
        if pn:
            sp += "\n【本局特色侧重——已移除与最终设定冲突的部分】" + pn

    sp += "\n\n【篇幅】" + pace["instruction"]
    if ctx.story_dna:
        sp += "\n\n" + ctx.story_dna
    if ctx.locked_tags and not agent_mode:
        sp += ("\n\n【玩家指定核心标签】" + "、".join(ctx.locked_tags)
               + "。落实其类型特征；若表达宽泛，以玩家更具体的身份、世界和额外要求为准。")
    if ctx.inspiration_tags and not agent_mode:
        sp += ("\n\n【研究库灵感候选】" + "、".join(ctx.inspiration_tags)
               + "。只采用与已确认设定自然相容的部分；不必逐项出现，"
                 "不得为凑标签新增无关角色、事件、阴谋或机制。")
    if ctx.turns == 0 and not agent_mode:
        sp += "\n\n" + FIRST_CHAPTER
    if ctx.turns == 0 and ctx.opening_text:
        sp += "\n\n" + ctx.opening_text

    pd = _agent_premise_directive(ctx.premise_state) if agent_mode else _premise_directive(ctx.premise_state, ctx.prefs)
    if pd:
        sp += "\n\n" + pd

    if agent_mode:
        scene_summary = _story_scene_summary(ctx.story_runtime)
        if scene_summary:
            sp += "\n\n" + scene_summary
        # 略写指令紧跟场景卡：它要用到卡上的 summary_target，隔远了就断了。
        # 注意 agent 模式下规则包整体不追加（写手契约已经是提示词开头），
        # 所以这里必须直接拼，不能指望 active_rule_packs。
        if (ctx.story_runtime.get("current_scene") or {}).get("narration") == "summary":
            sp += "\n\n" + SUMMARY_MODE_RULES

    names = ctx.names or derived_name_table(ctx)
    if names:
        sp += "\n\n【命名表——地名/势力/人名优先取自此表，新名字保持同风格】\n" + names
    if ctx.outline and not agent_mode:
        sp += ("\n\n【剧情备忘——保持目标与因果连续的编剧笔记，不是悬念清单】\n" + ctx.outline
               + "\n（剧情实质推进时才输出更新版【大纲】块）")
    if canon:
        sp += (
            "\n\n【主角身份档案——程序锁定的最高优先级事实】" + canon
            + "。每个字段属于独立命名空间：现实姓名不等于游戏ID，游戏ID不等于游戏角色名，"
              "旧世界身份不等于穿越后身份。只能在对应语境使用对应值；不得合并、互换、缩写、改写或用摘要覆盖。"
              "档案中没有的字段就是尚未确定，不得擅自补全。玩家以后明确修改时，以程序下一回合提供的新档案为准。"
        )

    ss = _state_summary(ctx.game_state)
    if ss:
        sp += ("\n\n【权威角色状态——系统维护的唯一事实，叙事与状态栏不得与此矛盾；技能列表是全集】\n" + ss)

    # 事实库检索结果。历史被压缩后这些设定仍然在，这正是它存在的意义。
    if ctx.lore_context:
        sp += "\n\n" + ctx.lore_context

    if ctx.pins:
        # 新的锁定设定优先保留，用字符预算而不是条数上限——
        # 条数上限会因为几条特别长的记录把整体挤爆
        pin_lines: list[str] = []
        pin_chars = 0
        for pin in reversed(ctx.pins):
            pl = "- " + str(pin.get("text") or "").strip()
            if pl == "- " or pin_chars + len(pl) > 6000:
                continue
            pin_lines.insert(0, pl)
            pin_chars += len(pl)
        sp += ("\n\n【不可更改的锁定设定——除程序身份档案与权威角色卡外的最高优先级】\n"
               + "\n".join(pin_lines) + "\n若其中某条旧记录与主角身份档案冲突，忽略该旧记录。")

    lore_blocks = _relevant_lore(ctx.recent_text, ctx.lorebook)
    if lore_blocks:
        sp += "\n\n【相关背景资料——本回合参考】\n" + lore_blocks

    active_rules = _active_narrative_rules(ctx)
    if active_rules and not agent_mode:
        sp += "\n\n【本局实际启用的叙事规则包——只包含当前路线相关内容】\n" + active_rules

    if ctx.story_dna and not agent_mode:
        sp += (
            "\n\n【最终一致性闸门｜设定哈希 " + debug_hash(ctx.story_dna)
            + "】输出前核对：世界类型、时代、基调、故事引擎、穿越形式和玩家硬性备注只能来自“本局最终有效设定”。"
              "较早剧情摘要只负责连续性，不能创建另一套世界前提。若历史与最终设定冲突，以最终设定为准，"
              "并在不替玩家行动的前提下让眼前场景自然回到有效设定。"
        )

    if agent_mode and ctx.story_dna:
        sp += (
            "\n\n【写手终检｜设定哈希 " + debug_hash(ctx.story_dna)
            + "】回应玩家；服从权威状态与场景卡；不新增因果；在下一个玩家决定前停下。"
        )

    return sp


def turn_mandate(ctx) -> str:
    """程序接管本幕时，压过每回合指令的强制令。

    为什么必须放在最后
    ------------------
    前端每回合会在整份系统提示词之后再追加一句「【本回合】只完成玩家明确
    行动及其直接反馈，在下一个决策边界前停下」。实测里程序接管的那一幕
    就是被这句话吃掉的：写手拿到了「本幕完成穿越」的场景卡，玩家输入是
    「拿起那枚铜钱，看颤动是否还在」，写手于是只拿起了铜钱——它服从了
    最靠后、最具体的那条指令，穿越推迟到了下一回合。

    这和规划器那次是同一种病（两条指令冲突，模型跟更近更具体的那条）。
    所以这里不去改那句话，而是把强制令放到比它更后的位置——用同一个
    机制反过来解决问题。
    """
    scene = (getattr(ctx, "story_runtime", None) or {}).get("current_scene") or {}
    if not isinstance(scene, dict) or scene.get("premise_phase_forced") is not True:
        return ""
    purpose = str(scene.get("purpose") or "").strip()
    target = str(scene.get("summary_target") or "").strip()
    note = (
        "\n\n【本回合强制事件——优先级高于上面「只完成玩家明确行动、"
        "在决策边界前停下」的要求】\n"
        f"{purpose}\n"
        "玩家的行动仍然要如实回应，但回应之后，本幕的事件**必须在这一回合内发生并走完**，"
        "不得停在决策边界之前，不得推迟到下一回合，也不得只写成征兆或预感。"
    )
    if target:
        note += f"\n本回合要抵达的终点：{target}"
    return note
