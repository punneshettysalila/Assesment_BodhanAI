"""Join paragraphs and tables that continue across page breaks."""
from __future__ import annotations

import re

from ..models import Block, BlockType, Flag, text_hash

_TERMINATOR = re.compile(r"[.!?।॥:;\"”’)\]]\s*$")


def _rows(table: str) -> list[str]:
    return [l for l in table.splitlines() if l.strip()]


def _cols(table: str) -> int:
    r = _rows(table)
    return r[0].strip().strip("|").count("|") + 1 if r else 0


def _is_sep(row: str) -> bool:
    return bool(re.fullmatch(r"\|?[\s:|-]+\|?", row)) and "-" in row


def join_across_pages(blocks: list[Block]) -> list[Block]:
    out: list[Block] = []
    for b in blocks:
        prev = out[-1] if out else None
        if prev and b.page == prev.page + 1:
            if (prev.type == b.type == BlockType.PARAGRAPH and not _TERMINATOR.search(prev.text)
                    and not prev.flags and not b.flags):
                hyphen = prev.text.endswith("-") and b.text[:1].islower()
                prev.text = (prev.text[:-1] if hyphen else prev.text + " ") + b.text
                prev.text_sha = text_hash(prev.text)      # deliberate, deterministic merge
                prev.meta.setdefault("merged_ids", []).append(b.id)
                if Flag.SPLIT_ACROSS_PAGE not in prev.flags:
                    prev.flags.append(Flag.SPLIT_ACROSS_PAGE)
                continue
            if prev.type == b.type == BlockType.TABLE and _cols(prev.text) == _cols(b.text):
                rows, head = _rows(b.text), (_rows(prev.text) or [""])[0]
                if rows and rows[0] == head:               # repeated header row
                    rows = rows[1:]
                    if rows and _is_sep(rows[0]):
                        rows = rows[1:]
                prev.text = prev.text.rstrip() + "\n" + "\n".join(rows)
                prev.text_sha = text_hash(prev.text)
                prev.meta.setdefault("merged_ids", []).append(b.id)
                continue
        out.append(b)
    return out
