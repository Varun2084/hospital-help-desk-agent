"""Keyword ko poore shabd ki tarah dhoondhna, taaki 'heart' me 'ear' na mile."""

import re

_EDGE = r"[\s,.;:!?()/'\"-]"


def contains_keyword(text: str, keyword: str) -> bool:
    """True tabhi, jab keyword ke dono taraf space, chinh (punctuation) ya text ka shuru/ant ho.
    Yeh Hindi (Devanagari) shabdon par bhi kaam karta hai."""
    pattern = rf"(?:^|{_EDGE}){re.escape(keyword.lower())}(?:$|{_EDGE})"
    return re.search(pattern, text.lower()) is not None
