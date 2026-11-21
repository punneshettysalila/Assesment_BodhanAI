"""Flag doubtful OCR blocks so garbage is never silently translated."""
from __future__ import annotations

import re
import unicodedata

from ..models import Block, BlockType, Flag

_LATEX_SPAN = re.compile(r"\$\$.+?\$\$|\$.+?\$|\\\(.+?\\\)|\\\[.+?\\\]", re.DOTALL)
_OK_PUNCT = set(".,;:!?()[]{}'\"-–—/%+=<>|*&…।॥°_^\\$#@~`•·’‘“”′″∠∥⊥△≅∼≠≤≥±×÷√π∴∵→⇒")
_REPEAT = re.compile(r"([^\s.\-_=|*~])\1{5,}")


def garbled_ratio(text: str) -> float:
    s = _LATEX_SPAN.sub("", text)
    chars = [c for c in s if not c.isspace()]
    if not chars:
        return 0.0
    bad = 0
    for c in chars:
        if c.isalnum() or c in _OK_PUNCT:
            continue
        cat = unicodedata.category(c)
        if cat[0] == "M" or cat == "Lm":
            continue
        bad += 1
    return bad / len(chars)


def latex_balanced(text: str) -> bool:
    if text.count("$$") % 2:
        return False
    stripped = text.replace("$$", "")
    if stripped.count("$") % 2:
        return False
    depth = 0
    for c in re.sub(r"\\[{}]", "", text):
        depth += (c == "{") - (c == "}")
        if depth < 0:
            return False
    if depth:
        return False
    return len(re.findall(r"\\begin\{", text)) == len(re.findall(r"\\end\{", text))


def assess(block: Block, cfg: dict) -> list[Flag]:
    c = cfg.get("ocr", {})
    flags: list[Flag] = []
    if block.confidence is not None and block.confidence < c.get("min_confidence", 0.8):
        flags.append(Flag.LOW_CONFIDENCE)
    if "\ufffd" in block.text or _REPEAT.search(block.text) or garbled_ratio(block.text) > c.get("max_garbage_ratio", 0.15):
        flags.append(Flag.GARBLED)
    if (block.type == BlockType.EQUATION or "$" in block.text or "\\begin" in block.text) and not latex_balanced(block.text):
        flags.append(Flag.BAD_LATEX)
    return flags


def apply_flags(blocks: list[Block], cfg: dict) -> int:
    n = 0
    for b in blocks:
        for f in assess(b, cfg):
            if f not in b.flags:
                b.flags.append(f)
        n += bool(b.flags)
    return n
