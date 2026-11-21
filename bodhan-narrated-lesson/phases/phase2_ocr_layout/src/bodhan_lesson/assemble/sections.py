"""Group ordered blocks into sections by headings; render the lesson Markdown."""
from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, Field

from ..models import Block, BlockType


class Section(BaseModel):
    index: int
    title: str
    level: int = 2
    slug: str = "section"
    blocks: list[Block] = Field(default_factory=list)


def slugify(text: str, fallback: str = "section") -> str:
    s = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:48]
    return s or fallback


def build_sections(blocks: list[Block], untitled: str = "Introduction") -> list[Section]:
    secs: list[Section] = []
    cur: Section | None = None
    for b in blocks:
        if b.type == BlockType.HEADING:
            cur = Section(index=len(secs) + 1, title=b.text, level=int(b.meta.get("level", 2)), blocks=[b])
            secs.append(cur)
        else:
            if cur is None:
                cur = Section(index=1, title=untitled, level=2)
                secs.append(cur)
            cur.blocks.append(b)
    for s in secs:
        s.slug = slugify(s.title, f"section-{s.index}")
    return secs


def _eq_md(text: str) -> str:
    t = text.strip()
    return t if t.startswith("$$") or t.startswith("\\[") else f"$$\n{t}\n$$"


def render_markdown(sections: list[Section], trace: bool = True) -> str:
    out: list[str] = []
    for s in sections:
        for b in s.blocks:
            tag = f"<!-- {b.id} -->\n" if trace else ""
            if b.type == BlockType.HEADING:
                out.append(f"{tag}{'#' * max(1, min(int(b.meta.get('level', 2)), 4))} {b.text}")
            elif b.type == BlockType.EQUATION:
                out.append(f"{tag}{_eq_md(b.text)}")
            else:
                out.append(f"{tag}{b.text}")
    return "\n\n".join(out) + "\n"


def structure_signature(md: str) -> list[str]:
    """Ordered H/T/E skeleton of a Markdown lesson, for structure-survival checks."""
    sig: list[str] = []
    in_math = in_table = False
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("<!--"):
            continue
        if s.startswith("$$") and s.endswith("$$") and len(s) > 4:
            sig.append("E"); in_table = False
            continue
        if s.count("$$") % 2 == 1:
            if not in_math:
                sig.append("E")
            in_math, in_table = not in_math, False
            continue
        if in_math:
            continue
        if s.startswith("|"):
            if not in_table:
                sig.append("T")
            in_table = True
            continue
        in_table = False
        if s.startswith("#"):
            sig.append("H")
    return sig
