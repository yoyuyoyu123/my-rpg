"""写手输出的确定性解析。

新模型可以返回 JSON 信封，旧模型仍可返回普通正文。这个模块只负责识别
「看起来确实是写手信封」的 JSON，不把正文中偶然出现的花括号误当成协议。
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.schemas.writer import StructuredWriterResult


def _json_candidates(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.I)
    if fenced:
        candidates.insert(0, fenced.group(1).strip())

    # 只扫描最外层平衡对象，避免对普通正文里的半截 JSON 过度猜测。
    start = text.find("{")
    while start >= 0:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : index + 1])
                    break
        start = text.find("{", start + 1)
    return candidates


def normalize_writer_output(raw: str) -> StructuredWriterResult | None:
    """返回结构化写手结果；普通文本或不完整 JSON 返回 ``None``。"""

    for candidate in _json_candidates(raw):
        try:
            obj: Any = json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not isinstance(obj, dict) or not isinstance(obj.get("narrative"), str):
            continue
        # ``options`` 是信封识别的重要信号；没有它的 JSON 更可能是正文中的资料块。
        if not isinstance(obj.get("options"), list):
            continue
        return StructuredWriterResult.model_validate(obj)
    return None

