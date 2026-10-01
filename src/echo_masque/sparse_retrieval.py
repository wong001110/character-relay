"""Bounded lexical matching shared by explicit recall and expression metadata."""

import math
import re
import unicodedata
from collections import Counter

_WORD_PATTERN = re.compile(r"[a-z0-9_]+|[\u3400-\u9fff]+", re.IGNORECASE)
_CJK_PATTERN = re.compile(r"^[\u3400-\u9fff]+$")


def normalize_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def semantic_tokens(value: str) -> list[str]:
    normalized = normalize_text(value)
    tokens: list[str] = []
    for match in _WORD_PATTERN.findall(normalized):
        tokens.append(match)
        if _CJK_PATTERN.match(match):
            tokens.extend(match)
            tokens.extend(match[index : index + 2] for index in range(len(match) - 1))
    return tokens


def sparse_score(query: str, content: str) -> float:
    left, right = Counter(semantic_tokens(query)), Counter(semantic_tokens(content))
    if not left or not right:
        return 0.0
    dot = sum(value * right.get(key, 0) for key, value in left.items())
    norm = math.sqrt(sum(value * value for value in left.values())) * math.sqrt(
        sum(value * value for value in right.values())
    )
    return dot / norm
