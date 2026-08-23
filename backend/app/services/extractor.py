"""
服务层 · 事实抽取
=================
职责：读一回合的叙事，把里面新确立的设定抽成结构化事实。

这是「文本 → 数据」的转换环节，也是整个一致性方案的入口。
没有它，事实库永远是空的。

设计要点：
    1. 用 ontology 的词表约束输出 —— 保证抽出来的 key 和查询时用的 key 一致
    2. 只抽「已经明确写出的」—— 不推测、不脑补，宁缺毋滥
    3. 失败不影响主流程 —— 抽取挂了最多是这回合没记事实，不能让玩家卡住
"""
import json
import re

from app.config import Settings
from app.domain.ontology import ATTRS_BY_KIND, KIND_MENU, EntityKind, attr_menu
from app.services.llm import LLMError, call_chat

# 抽取用小模型即可，省钱且够用
EXTRACT_MAX_TOKENS = 1600


def build_prompt(
    narrative: str,
    player_input: str,
    known_names: list[str],
    known_facts: str = "",
) -> str:
    """
    组装抽取提示词。

    把属性词表直接写进去，模型就只会用这些 key——
    这比事后清洗容易得多，也是「约束生成」的常见手法。
    """
    menus = "\n".join(
        f"  {kind.value}：{attr_menu(kind)}" for kind in ATTRS_BY_KIND
    )
    known = "、".join(known_names[:40]) if known_names else "（暂无）"
    # 抽取器只需要去重线索，不应把整库再次塞给模型；超出部分下一批仍可检索。
    facts = known_facts.strip()[:8000] or "（暂无已记录事实）"

    return (
        "你是文字游戏的设定记录员。从下面这一回合的内容里，"
        "提取【已经明确写出】的世界设定，输出结构化数据。\n\n"
        "严格规则：\n"
        "1. 只记录文本中明确交代的信息。不要推测、不要补全、不要归纳言外之意。\n"
        "2. 泛泛的路人（没有名字、只出现一次、无关剧情）不要记录。\n"
        "3. 主角自己不要作为实体记录（主角状态由其它系统管理）。\n"
        "4. 每条事实必须简短具体，一句话说清。\n"
        "5. 如果这一回合没有任何值得长期记住的新设定，返回空数组。\n"
        "6. 已记录事实只用于去重和核对：同一事实再次出现、换一种说法、增加不改变原意的修饰时，不要重复输出。\n"
        "7. 只有文本明确推翻旧值时才输出同一属性的新值；外貌、性格、氛围等普通补充不是矛盾，也不必每回合重记。\n"
        "8. events 只写本回合实际发生且会影响后续的事件；action 是发生了什么，outcome 是已落地结果。\n"
        "9. commitments 只写明确承诺、接受、拒绝或边界。玩家拒绝某个邀请时，kind=refusal、hard=true，并把不得换皮重提写进 forbids。履行/取消已记录承诺时必须复用已记录事实中的 com_ id 并更新 status。\n"
        "10. beliefs 是某个 NPC 自己知道、相信、怀疑或误解的内容，不等同于世界真相；文本未说明知识来源时不要抽。\n"
        "11. character_states 分 identity（身份/稳定性格）、mid_term（目标/顾虑）、short_term（眼前情绪/行动）、relationships（对具体人物）；只写本回合明确变化。\n"
        "12. 已记录事实中已有的 evt_ 事件不得重复输出；只有本回合另一个确实发生的事件才新增 events。\n\n"
        f"实体类型：{KIND_MENU}\n\n"
        f"各类型可用的属性名（必须从中选择，不要自造）：\n{menus}\n\n"
        f"已知实体（如果提到的是这些，请使用完全相同的名字）：{known}\n\n"
        f"已记录事实（不要重复抽取）：\n{facts}\n\n"
        "只输出一个 JSON 对象，不要任何解释文字；没有内容的数组留空：\n"
        '{"entities":[{"name":"规范名","kind":"person","aliases":["别名"],'
        '"importance":1,"facts":[{"key":"职业","value":"洗衣妇"}]}],'
        '"events":[{"id":"已有evt_ id或空","kind":"action","actor":"谁","action":"做了什么","outcome":"已发生结果",'
        '"location":"地点","participants":["参与者"],"cause_ids":[],"visibility":"public"}],'
        '"commitments":[{"id":"已有com_ id或空","kind":"promise|refusal|agreement|obligation|boundary","owner":"谁",'
        '"counterparty":"对谁","text":"具体内容","status":"active|fulfilled|rejected|cancelled|expired",'
        '"hard":false,"due_turn":null,"forbids":[]}],'
        '"beliefs":[{"npc":"谁","statement":"其本人掌握或相信的内容",'
        '"mode":"knows|believes|suspects|misinformed","confidence":100,"source":"亲眼/某人告知"}],'
        '"character_states":[{"name":"谁","identity":{},"mid_term":{},"short_term":{},"relationships":{}}]}\n\n'
        "importance 取 0-3：3=主线关键人物/地点，2=反复出现，1=一般，0=可有可无。\n\n"
        f"=== 玩家这一回合做了什么 ===\n{player_input[:800]}\n\n"
        f"=== 本回合叙事 ===\n{narrative[:4000]}"
    )


def _strip_json(text: str) -> dict:
    """
    从模型输出里挖出 JSON。

    即使要求「只输出 JSON」，模型偶尔仍会包一层 ```json 或加一句说明，
    所以要容错——这属于「LLM 输出不可信」的常规防御。
    """
    t = text.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    m = re.search(r"\{[\s\S]*\}", t)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def parse_result(raw_text: str) -> list[dict]:
    """
    把模型的原始输出变成干净的实体列表。

    单独暴露出来，是为了支持「前端代跑模型」的模式：
    直连模式下浏览器持有 API key，后端没有——
    那就由后端出题（build_prompt）、前端交卷（这个函数解析）。
    好处是本体词表和清洗规则只有一份，不会前后端各写一套写着写着就不一致。
    """
    return _sanitize(_strip_json(raw_text))


def parse_bundle(raw_text: str) -> dict[str, list[dict]]:
    """解析完整叙事账本；旧版只返回 entities 的 JSON 仍然完全兼容。"""
    return _sanitize_bundle(_strip_json(raw_text))


def _sanitize(data: dict) -> list[dict]:
    """
    清洗模型输出，只留合法的部分。

    模型可能给出不存在的 kind、词表外的 key、超长字符串——
    这里全部过滤掉，保证进库的数据是干净的。
    """
    out: list[dict] = []
    for raw in (data.get("entities") or [])[:12]:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()[:80]
        kind_raw = str(raw.get("kind") or "").strip()
        if not name or kind_raw not in {k.value for k in EntityKind}:
            continue

        kind = EntityKind(kind_raw)
        allowed = set(ATTRS_BY_KIND.get(kind, {}))

        facts = []
        for f in (raw.get("facts") or [])[:8]:
            if not isinstance(f, dict):
                continue
            key = str(f.get("key") or "").strip()[:40]
            value = str(f.get("value") or "").strip()[:400]
            # 词表外的 key 直接丢弃——否则查询和矛盾检测都会失效
            if key in allowed and value:
                facts.append({"key": key, "value": value})

        if not facts:
            continue

        aliases = [
            str(a).strip()[:80]
            for a in (raw.get("aliases") or [])[:5]
            if str(a).strip()
        ]
        try:
            importance = max(0, min(3, int(raw.get("importance", 1))))
        except (TypeError, ValueError):
            importance = 1

        out.append({
            "name": name, "kind": kind.value, "aliases": aliases,
            "importance": importance, "facts": facts,
        })
    return out


def _short_list(value: object, limit: int, chars: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[:limit]:
        text = str(item or "").strip()[:chars]
        if text and text not in out:
            out.append(text)
    return out


def _safe_id(value: object, limit: int = 64) -> str:
    text = str(value or "").strip()[:limit]
    return text if re.fullmatch(r"[A-Za-z0-9_.:-]+", text) else ""


def _clean_dict(value: object, limit: int = 12, chars: int = 300) -> dict:
    if not isinstance(value, dict):
        return {}
    out: dict[str, object] = {}
    for key, item in list(value.items())[:limit]:
        k = str(key or "").strip()[:60]
        if not k:
            continue
        if isinstance(item, (str, int, float, bool)) or item is None:
            out[k] = str(item).strip()[:chars] if isinstance(item, str) else item
        elif isinstance(item, list):
            out[k] = _short_list(item, 8, 100)
    return out


def _sanitize_bundle(data: dict) -> dict[str, list[dict]]:
    events: list[dict] = []
    for raw in (data.get("events") or [])[:8]:
        if not isinstance(raw, dict):
            continue
        action = str(raw.get("action") or "").strip()[:500]
        outcome = str(raw.get("outcome") or "").strip()[:900]
        if not action and not outcome:
            continue
        visibility = str(raw.get("visibility") or "public")
        if visibility not in {"public", "participants", "private"}:
            visibility = "public"
        events.append({
            "id": _safe_id(raw.get("id")),
            "kind": str(raw.get("kind") or "scene").strip()[:32],
            "actor": str(raw.get("actor") or "").strip()[:80],
            "action": action, "outcome": outcome,
            "location": str(raw.get("location") or "").strip()[:120],
            "participants": _short_list(raw.get("participants"), 12, 80),
            "cause_ids": _short_list(raw.get("cause_ids"), 8, 64),
            "visibility": visibility,
        })

    commitments: list[dict] = []
    for raw in (data.get("commitments") or [])[:8]:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()[:500]
        if not text:
            continue
        kind = str(raw.get("kind") or "promise")
        if kind not in {"promise", "refusal", "agreement", "obligation", "boundary"}:
            kind = "promise"
        status = str(raw.get("status") or "active")
        if status not in {"active", "fulfilled", "rejected", "cancelled", "expired"}:
            status = "active"
        due = raw.get("due_turn")
        try:
            due = max(0, int(due)) if due is not None else None
        except (TypeError, ValueError):
            due = None
        commitments.append({
            "id": _safe_id(raw.get("id")),
            "kind": kind, "owner": str(raw.get("owner") or "").strip()[:80],
            "counterparty": str(raw.get("counterparty") or "").strip()[:80],
            "text": text, "status": status, "hard": bool(raw.get("hard")),
            "due_turn": due, "forbids": _short_list(raw.get("forbids"), 8, 240),
            "source_event_id": _safe_id(raw.get("source_event_id")),
        })

    beliefs: list[dict] = []
    for raw in (data.get("beliefs") or [])[:16]:
        if not isinstance(raw, dict):
            continue
        npc = str(raw.get("npc") or "").strip()[:80]
        statement = str(raw.get("statement") or "").strip()[:500]
        if not npc or not statement:
            continue
        mode = str(raw.get("mode") or "knows")
        if mode not in {"knows", "believes", "suspects", "misinformed"}:
            mode = "knows"
        try:
            confidence = max(0, min(100, int(raw.get("confidence", 100))))
        except (TypeError, ValueError):
            confidence = 100
        beliefs.append({"npc": npc, "statement": statement, "mode": mode,
                        "confidence": confidence,
                        "source": str(raw.get("source") or "").strip()[:100]})

    states: list[dict] = []
    for raw in (data.get("character_states") or [])[:10]:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()[:80]
        if not name:
            continue
        state = {"name": name, "identity": _clean_dict(raw.get("identity")),
                 "mid_term": _clean_dict(raw.get("mid_term")),
                 "short_term": _clean_dict(raw.get("short_term")),
                 "relationships": _clean_dict(raw.get("relationships"))}
        if any(state[k] for k in ("identity", "mid_term", "short_term", "relationships")):
            states.append(state)

    return {"entities": _sanitize(data), "events": events, "commitments": commitments,
            "beliefs": beliefs, "character_states": states}


async def extract_bundle(
    *,
    settings: Settings,
    provider_id: str,
    model: str,
    narrative: str,
    player_input: str = "",
    known_names: list[str] | None = None,
    known_facts: str = "",
) -> dict[str, list[dict]]:
    """
    抽取一回合的事实。

    返回清洗后的实体列表；任何环节出问题都返回空列表——
    抽取失败只是「这回合没记住东西」，绝不能让玩家的回合失败。
    """
    if not narrative.strip():
        return {"entities": [], "events": [], "commitments": [], "beliefs": [], "character_states": []}

    prompt = build_prompt(
        narrative, player_input, known_names or [], known_facts=known_facts,
    )

    try:
        result = await call_chat(
            settings=settings,
            provider_id=provider_id,
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,          # 抽取要稳定，不要发挥
            max_tokens=EXTRACT_MAX_TOKENS,
        )
    except LLMError:
        return {"entities": [], "events": [], "commitments": [], "beliefs": [], "character_states": []}
    except Exception:
        return {"entities": [], "events": [], "commitments": [], "beliefs": [], "character_states": []}

    return _sanitize_bundle(_strip_json(result.content))


async def extract_facts(
    *,
    settings: Settings,
    provider_id: str,
    model: str,
    narrative: str,
    player_input: str = "",
    known_names: list[str] | None = None,
    known_facts: str = "",
) -> list[dict]:
    """兼容旧调用：只取完整账本中的实体事实。"""
    bundle = await extract_bundle(
        settings=settings, provider_id=provider_id, model=model,
        narrative=narrative, player_input=player_input,
        known_names=known_names, known_facts=known_facts,
    )
    return bundle["entities"]
