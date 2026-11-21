"""Remove running headers/footers and page numbers with a GENERIC rule:
text repeating in the edge band of >= 40% of pages is chrome, not content."""
from __future__ import annotations

import math
import re
import unicodedata
from collections import defaultdict

from ..models import Block, BlockType, Flag, Page

_PAGENUM = re.compile(r"^\W*(?:page\s*)?\d{1,4}\W*$", re.I)
CHROME = {BlockType.HEADER, BlockType.FOOTER, BlockType.PAGE_NUMBER}
PROTECTED = (BlockType.HEADING, BlockType.EQUATION, BlockType.TABLE, BlockType.FIGURE)


def norm(text: str) -> str:
    t = re.sub(r"\d+", "#", text.lower())
    t = "".join(c if (unicodedata.category(c)[0] in "LMN" or c.isspace()) else " " for c in t)
    return re.sub(r"\s+", " ", t).strip()


def _edge_blocks(page: Page, k: int, band: float) -> list[tuple[Block, str]]:
    bs = sorted(page.blocks, key=lambda b: b.order)
    if not bs:
        return []
    out: list[tuple[Block, str]] = []
    if any(b.bbox for b in bs):
        for b in bs:
            if b.bbox and b.bbox[3] <= band:
                out.append((b, "header"))
            elif b.bbox and b.bbox[1] >= 1 - band:
                out.append((b, "footer"))
    else:
        head = bs[:k]
        out += [(b, "header") for b in head]
        out += [(b, "footer") for b in bs[-k:] if b not in head]
    return out


def strip_running(pages: list[Page], cfg: dict, k: int = 2) -> list[dict]:
    c = cfg.get("layout", {})
    frac, band = c.get("header_footer_page_fraction", 0.40), c.get("band_height", 0.08)
    n = len([p for p in pages if p.blocks])
    removed: list[dict] = []
    seen: dict[str, set[int]] = defaultdict(set)
    edges = {p.number: _edge_blocks(p, k, band) for p in pages}
    for pno, lst in edges.items():
        for b, _ in lst:
            if b.type in PROTECTED:
                continue
            key = norm(b.text)
            if len(key) >= 3:
                seen[key].add(pno)
    need = max(2, math.ceil(frac * n))
    chrome_keys = {key for key, ps in seen.items() if len(ps) >= need}
    for pno, lst in edges.items():
        for b, where in lst:
            if b.type in PROTECTED:
                continue
            reason = None
            if _PAGENUM.match(b.text):
                reason, b.type = "page_number", BlockType.PAGE_NUMBER
            elif norm(b.text) in chrome_keys:
                reason = "repeated_edge_text"
                b.type = BlockType.HEADER if where == "header" else BlockType.FOOTER
            if reason:
                if Flag.RUNNING_HEADER not in b.flags:
                    b.flags.append(Flag.RUNNING_HEADER)
                b.meta["removed_reason"] = reason
                removed.append({"id": b.id, "page": pno, "text": b.text[:80], "reason": reason})
    return removed


def content_blocks(pages: list[Page]) -> list[Block]:
    out: list[Block] = []
    for p in sorted(pages, key=lambda p: p.number):
        out += [b for b in sorted(p.blocks, key=lambda b: b.order) if b.type not in CHROME]
    return out
