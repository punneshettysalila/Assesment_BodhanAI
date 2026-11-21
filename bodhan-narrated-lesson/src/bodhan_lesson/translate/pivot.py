"""Indian-language source -> English pivot built ONCE and reused for every target.
Round-trip scoring (pivot -> source language, compared with the OCR text) flags
blocks where meaning was lost on the first hop, before it is lost a second time."""
from __future__ import annotations

import difflib
import re
import unicodedata

from ..models import Block
from .engine import Translator
from .mask import LATEX


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", LATEX.sub("", s).lower())
    s = "".join(c if (unicodedata.category(c)[0] in "LMN" or c.isspace()) else " " for c in s)
    return re.sub(r"\s+", " ", s).strip()


def similarity(a: str, b: str) -> float:
    """Word-level similarity (char-level is too lenient within one script)."""
    return difflib.SequenceMatcher(None, _norm(a).split(), _norm(b).split()).ratio()


async def build_pivot(blocks: list[Block], tr_to_en: Translator, tr_back: Translator | None,
                      min_similarity: float = 0.30) -> tuple[dict[str, str | None], list[dict]]:
    pivot = await tr_to_en.blocks(blocks)
    weak: list[dict] = []
    if tr_back is not None:
        by_id = {b.id: b for b in blocks}
        for bid, en in pivot.items():
            b = by_id[bid]
            if en is None or len(b.text) < 40 or b.type.value in ("equation", "figure", "table"):
                continue
            back = await tr_back.text(en, bid)
            s = similarity(b.text, back)
            if s < min_similarity:
                weak.append({"block": bid, "roundtrip_similarity": round(s, 2)})
    return pivot, weak
