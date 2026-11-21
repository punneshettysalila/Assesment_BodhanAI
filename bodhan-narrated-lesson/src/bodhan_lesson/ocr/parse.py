"""Indic-OCR response -> Blocks. Accepts structured JSON blocks or Markdown text.
Text is copied verbatim from OCR; nothing here rewrites it."""
from __future__ import annotations

import json
import re

from ..models import Block, BlockType

_LIST = re.compile(r"^\s*(?:[-*•]|\(?\d+[.)]|\(?[a-z][.)])\s+")
_CAPTION = re.compile(r"^\s*(?:fig(?:ure)?\.?|चित्र|படம்|চিত্র)\s*[\d.]*", re.I)


def _classify(chunk: str) -> tuple[BlockType, str, dict]:
    s = chunk.strip()
    first = s.splitlines()[0] if s else ""
    if first.lstrip().startswith("#"):
        level = len(first) - len(first.lstrip("#"))
        return BlockType.HEADING, first.lstrip("#").strip(), {"level": min(max(level, 1), 4)}
    lines = [l for l in s.splitlines() if l.strip()]
    if lines and all(l.strip().startswith("|") for l in lines):
        return BlockType.TABLE, s, {}
    if s.startswith("$$") or s.startswith("\\[") or re.fullmatch(r"\s*\\begin\{(?:align|equation|gather)\*?\}.*", s, re.S):
        return BlockType.EQUATION, s, {}
    if s.startswith("![") or re.match(r"^\[(?:figure|image)", s, re.I):
        return BlockType.FIGURE, s, {}
    if _CAPTION.match(s) and len(s) < 200:
        return BlockType.CAPTION, s, {}
    if lines and all(_LIST.match(l) for l in lines):
        return BlockType.LIST, s, {}
    return BlockType.PARAGRAPH, s, {}


def _split_markdown(md: str) -> list[str]:
    """Blank-line split that keeps $$...$$ and tables together."""
    chunks, cur, in_math = [], [], False
    for line in md.splitlines():
        if line.count("$$") % 2 == 1:
            in_math = not in_math
        if not line.strip() and not in_math:
            if cur:
                chunks.append("\n".join(cur))
                cur = []
        else:
            cur.append(line)
    if cur:
        chunks.append("\n".join(cur))
    return [c for c in chunks if c.strip()]


def parse_ocr_response(page: int, raw: str) -> list[Block]:
    raw = raw.strip()
    blocks: list[Block] = []
    data = None
    if raw[:1] in "[{":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = None
    if isinstance(data, dict):
        data = data.get("blocks") or data.get("regions")
    if isinstance(data, list):
        for i, d in enumerate(data):
            if not isinstance(d, dict) or not str(d.get("text", "")).strip():
                continue
            t = str(d.get("type", "")).lower()
            aliases = {
                "chapter-title": BlockType.HEADING, "section-title": BlockType.HEADING,
                "title": BlockType.HEADING, "sectionheader": BlockType.HEADING,
                "heading": BlockType.HEADING, "paragraph": BlockType.PARAGRAPH,
                "text": BlockType.PARAGRAPH, "list": BlockType.LIST, "table": BlockType.TABLE,
                "equation": BlockType.EQUATION, "formula": BlockType.EQUATION,
                "caption": BlockType.CAPTION, "picture": BlockType.FIGURE,
                "figure": BlockType.FIGURE, "header": BlockType.HEADER,
                "footer": BlockType.FOOTER, "page-number": BlockType.PAGE_NUMBER,
                "handwriting": BlockType.HANDWRITTEN, "handwritten": BlockType.HANDWRITTEN,
            }
            try:
                bt = BlockType(t)
            except ValueError:
                bt = aliases.get(t.replace("_", "").replace(" ", "").lower())
                if bt is None:
                    label = str(d.get("type", d.get("label", ""))).lower().replace("_", "-").replace(" ", "-")
                    bt = next((kind for name, kind in aliases.items() if name in label), None)
                if bt is None:
                    bt, _, _ = _classify(d["text"])
            bbox = d.get("bbox")
            blocks.append(Block(
                id=f"p{page:02d}-b{i:03d}", page=page, type=bt, text=str(d["text"]).strip(),
                bbox=tuple(map(float, bbox)) if bbox and len(bbox) == 4 else None,
                confidence=d.get("confidence"), order=int(d.get("order", i)),
                meta={**({"level": d.get("level", 2)} if bt == BlockType.HEADING else {}),
                      **({"layout_confidence": d["layout_confidence"]} if d.get("layout_confidence") is not None else {})}))
        return blocks
    for i, chunk in enumerate(_split_markdown(raw)):
        bt, text, meta = _classify(chunk)
        blocks.append(Block(id=f"p{page:02d}-b{i:03d}", page=page, type=bt, text=text, order=i, meta=meta))
    return blocks
