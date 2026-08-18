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
EXTRACT_MAX_TOKENS = 900


def build_prompt(narrative: str, player_input: str, known_names: list[str]) -> str:
    """
    组装抽取提示词。

    把属性词表直接写进去，模型就只会用这些 key——
    这比事后清洗容易得多，也是「约束生成」的常见手法。
    """
    menus = "\n".join(
        f"  {kind.value}：{attr_menu(kind)}" for kind in ATTRS_BY_KIND
    )
    known = "、".join(known_names[:40]) if known_names else "（暂无）"

    return (
        "你是文字游戏的设定记录员。从下面这一回合的内容里，"
        "提取【已经明确写出】的世界设定，输出结构化数据。\n\n"
        "严格规则：\n"
        "1. 只记录文本中明确交代的信息。不要推测、不要补全、不要归纳言外之意。\n"
        "2. 泛泛的路人（没有名字、只出现一次、无关剧情）不要记录。\n"
        "3. 主角自己不要作为实体记录（主角状态由其它系统管理）。\n"
        "4. 每条事实必须简短具体，一句话说清。\n"
        "5. 如果这一回合没有任何值得长期记住的新设定，返回空数组。\n\n"
        f"实体类型：{KIND_MENU}\n\n"
        f"各类型可用的属性名（必须从中选择，不要自造）：\n{menus}\n\n"
        f"已知实体（如果提到的是这些，请使用完全相同的名字）：{known}\n\n"
        "只输出一个 JSON 对象，不要任何解释文字：\n"
        '{"entities":[{"name":"规范名","kind":"person","aliases":["别名"],'
        '"importance":1,"facts":[{"key":"职业","value":"洗衣妇"}]}]}\n\n'
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


async def extract_facts(
    *,
    settings: Settings,
    provider_id: str,
    model: str,
    narrative: str,
    player_input: str = "",
    known_names: list[str] | None = None,
) -> list[dict]:
    """
    抽取一回合的事实。

    返回清洗后的实体列表；任何环节出问题都返回空列表——
    抽取失败只是「这回合没记住东西」，绝不能让玩家的回合失败。
    """
    if not narrative.strip():
        return []

    prompt = build_prompt(narrative, player_input, known_names or [])

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
        return []
    except Exception:
        return []

    return _sanitize(_strip_json(result.content))
