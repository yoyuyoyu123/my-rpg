"""Small inspectable algorithms; model estimates are not objective literary scores."""
import math
import re

from app.schemas.novel import DraftReview, EventNode, NovelRuntime

STYLES = {
    "grounded": "具体而有余味：空间、动作、物件与人物的注意力互相联系；句式有呼吸，避免解释每种情绪。",
    "dialogue": "人物声线与潜台词：对话有各自目的，沉默和动作改变含义；允许不回答，不做信息播报员。",
    "lyrical": "有节制的意象与节奏：意象来自眼前环境和既有经历，长短句交错；不堆比喻，不统一煽情。",
}


def grams(text: str) -> set[str]:
    text = re.sub(r"\s+", "", text.lower())
    return {text[i:i + 2] for i in range(max(0, len(text) - 1))}


def similarity(a: set, b: set) -> float:
    return len(a & b) / max(1, len(a | b))


def recall(runtime: NovelRuntime, query: str, budget: int = 2400) -> list[dict]:
    """MMR over retained original excerpts. Budget is characters, not tokens."""
    q = grams(query)
    remaining = [(e, grams(e.text)) for e in runtime.excerpts]
    selected, used = [], 0
    while remaining:
        eligible = [(e, g) for e, g in remaining if len(e.text) + used <= budget]
        if not eligible:
            break
        e, g = max(eligible, key=lambda x: (
            0.8 * similarity(q, x[1])
            - 0.2 * max((similarity(x[1], z[1]) for z in selected), default=0),
            x[0].turn,
        ))
        # Do not spend the budget on unrelated prose just to fill a quota.
        if not (q & g):
            break
        selected.append((e, g))
        used += len(e.text)
        remaining.remove((e, g))
    return [e.model_dump() for e, _ in sorted(selected, key=lambda x: x[0].turn)]


def style_mean(runtime: NovelRuntime, style: str) -> float:
    p = runtime.preferences.get(style)
    return (1 + p.likes) / (2 + p.likes + p.dislikes) if p else 0.5


def choose_styles(runtime: NovelRuntime, count: int, turn: int) -> list[str]:
    """Beta posterior mean + small UCB exploration bonus; no implicit feedback."""
    styles = list(STYLES)
    rotated = styles[turn % 3:] + styles[:turn % 3]
    total = sum(p.likes + p.dislikes for p in runtime.preferences.values())
    def score(style):
        p = runtime.preferences.get(style)
        n = p.likes + p.dislikes if p else 0
        return style_mean(runtime, style) + 0.15 * math.sqrt(math.log(total + 2) / (n + 1))
    return sorted(rotated, key=score, reverse=True)[:count]


def choose_event(nodes: list[EventNode], evidence_text: str,
                 known_by_actor: dict[str, list[str]] | None = None) -> tuple[EventNode | None, dict]:
    """Validate a speculative DAG, then bounded beam search. Return FIRST action only."""
    counts = {n.id: sum(x.id == n.id for x in nodes) for n in nodes}
    valid = {}
    rejected = []
    for n in nodes:
        if (counts[n.id] != 1 or n.actor.lower() in {"player", "玩家", "你", "主角"}
                or not n.evidence or any(q not in evidence_text for q in n.evidence + n.perceived)):
            rejected.append(n.id)
        elif (known_by_actor is not None and n.actor.lower() != "world" and (
                n.actor not in known_by_actor
                or any(not any(q in fact for fact in known_by_actor[n.actor]) for q in n.perceived))):
            # A world fact does not automatically become every NPC's knowledge.
            rejected.append(n.id)
        else:
            valid[n.id] = n
    # A child must have its entire ancestry in the validated graph; cycles fail.
    def ancestry_ok(n):
        seen = {n.id}
        while n.parent:
            if n.parent in seen or n.parent not in valid:
                return False
            seen.add(n.parent)
            n = valid[n.parent]
        return True
    kept = {key: n for key, n in valid.items() if ancestry_ok(n)}
    rejected.extend(key for key in valid if key not in kept)
    def value(n):
        return (0.45 * n.causal + 0.30 * n.character + 0.25 * n.openness) / math.sqrt(n.duration)
    beam = sorted([(value(n), [n]) for n in kept.values() if not n.parent],
                  key=lambda x: x[0], reverse=True)[:3]
    all_paths = list(beam)
    for depth in range(1, 3):
        expanded = [(score + (0.65 ** depth) * value(n), path + [n])
                    for score, path in beam for n in kept.values() if n.parent == path[-1].id]
        beam = sorted(expanded, key=lambda x: x[0], reverse=True)[:3]
        all_paths.extend(beam)
    if not all_paths:
        return None, {"rejected": rejected, "path": [], "algorithm": "beam-3x3"}
    score, path = max(all_paths, key=lambda x: x[0])
    return path[0], {"rejected": rejected, "path": [n.id for n in path],
                     "estimated_value": round(score, 4), "algorithm": "beam-3x3"}


def select_review(reviews: list[DraftReview], styles: dict[int, str], runtime: NovelRuntime) -> DraftReview | None:
    safe = [r for r in reviews if r.id in styles and r.agency_ok and r.facts_ok and r.knowledge_ok]
    def vector(r):
        return (r.causal, r.character, r.prose, r.pacing)
    frontier = [r for r in safe if not any(
        all(a >= b for a, b in zip(vector(o), vector(r)))
        and any(a > b for a, b in zip(vector(o), vector(r))) for o in safe)]
    return max(frontier, key=lambda r: (
        0.25 * r.causal + 0.25 * r.character + 0.30 * r.prose + 0.20 * r.pacing
        + 0.12 * (style_mean(runtime, styles[r.id]) - 0.5)), default=None)
