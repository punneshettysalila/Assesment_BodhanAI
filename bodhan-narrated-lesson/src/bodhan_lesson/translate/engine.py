"""Block-level translation preserving headings, tables, equations, numbers and LaTeX.
Flagged (garbled / low-confidence) blocks are NEVER translated; they are reported."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Awaitable, Callable

from ..cache import DiskCache
from ..models import Block, BlockType, Flag
from .check import check_block
from .mask import lock_terms, mask_latex, unmask

log = logging.getLogger("bodhan_lesson.translate")
TranslateFn = Callable[[str, str, str], Awaitable[str]]
BLOCKING = {Flag.GARBLED, Flag.LOW_CONFIDENCE, Flag.BAD_LATEX}
MAX_CHARS = 6000          # far below the 32K-token window; keeps latency and drift low


def split_long(text: str, limit: int = MAX_CHARS) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.!?।॥])\s+", text):
        if len(cur) + len(sent) + 1 > limit and cur:
            parts.append(cur)
            cur = ""
        cur += (" " if cur else "") + sent
    return parts + ([cur] if cur else [])


class Translator:
    def __init__(self, fn: TranslateFn, cache: DiskCache, src: str, tgt: str,
                 locked: dict[str, str] | None = None, retries: int = 1):
        self.fn, self.cache, self.src, self.tgt = fn, cache, src, tgt
        self.locked, self.retries = locked or {}, retries
        self.issues: list[dict] = []
        self.skipped: list[dict] = []
        self.lock_fallbacks = 0

    async def _raw(self, text: str) -> str:
        key = DiskCache.key(text, self.src, self.tgt, getattr(self.fn, "cache_namespace", "tr-v1"))
        hit = self.cache.get("translate", key)
        if hit is None:
            hit = await self.fn(text, self.src, self.tgt)
            self.cache.set("translate", key, hit)
        return hit

    async def text(self, src_text: str, block_id: str, prose: bool = True) -> str:
        """Translate one run of text with LaTeX (and optional glossary) protected."""
        best, best_issues = "", ["untranslated"]
        for use_locks in ([True, False] if self.locked and self.src == "en" else [False]):
            masked, m1 = mask_latex(src_text)
            mapping = dict(m1)
            if use_locks:
                masked, m2 = lock_terms(masked, self.locked, start=len(m1))
                mapping.update(m2)
            for attempt in range(self.retries + 1):
                chunks = split_long(masked)
                out = " ".join([await self._raw(c) for c in chunks])
                restored, ok = unmask(out, mapping)
                if not ok:                       # placeholders lost: retry, then fall back to unmasked
                    if use_locks:
                        self.lock_fallbacks += 1
                    log.warning("mask_lost", extra={"block": block_id, "attempt": attempt})
                    continue
                issues = check_block(src_text, restored, self.tgt, prose)
                if not issues:
                    return restored
                if len(issues) < len(best_issues):
                    best, best_issues = restored, issues
            if best:
                break
        if not best:      # last resort: translate without masks, then verify numbers/LaTeX
            best = await self._raw(src_text)
            best_issues = check_block(src_text, best, self.tgt, prose) or ["mask_unavailable"]
        self.issues.append({"block": block_id, "issues": best_issues})
        return best

    async def table(self, md: str, block_id: str) -> str:
        rows = [r for r in md.splitlines() if r.strip()]
        out = []
        for r in rows:
            if re.fullmatch(r"\|?[\s:|-]+\|?", r) and "-" in r:
                out.append(r)
                continue
            lead, trail = r.strip().startswith("|"), r.strip().endswith("|")
            cells = r.strip().strip("|").split("|")
            new = await asyncio.gather(*[self._cell(c, block_id) for c in cells])
            out.append(("|" if lead else "") + "|".join(new) + ("|" if trail else ""))
        res = "\n".join(out)
        if len(res.splitlines()) != len(rows):
            self.issues.append({"block": block_id, "issues": ["table_rows_changed"]})
        return res

    async def _cell(self, cell: str, block_id: str) -> str:
        core = cell.strip()
        if not re.search(r"[^\W\d_]", re.sub(r"\$[^$]*\$", "", core)):   # numbers/LaTeX only
            return cell
        t = await self.text(core, block_id, prose=False)
        return f" {t.replace('|', '/')} "

    async def block(self, b: Block) -> str | None:
        """Return translated text for a block, or None if it is withheld/skipped."""
        if set(b.flags) & BLOCKING:
            self.skipped.append({"block": b.id, "reason": [f.value for f in b.flags if f in BLOCKING]})
            return None
        if b.type in (BlockType.EQUATION, BlockType.FIGURE):
            return b.text                         # math and image refs are never translated
        if b.type == BlockType.TABLE:
            return await self.table(b.text, b.id)
        if b.type == BlockType.LIST:
            lines = [l for l in b.text.splitlines() if l.strip()]
            outl = []
            for l in lines:
                m = re.match(r"^(\s*(?:[-*•]|\(?\d+[.)]|\(?[a-z][.)])\s+)(.*)$", l)
                lead, body = (m.group(1), m.group(2)) if m else ("", l)
                outl.append(lead + await self.text(body, b.id))
            return "\n".join(outl)
        return await self.text(b.text, b.id)

    async def blocks(self, blocks: list[Block]) -> dict[str, str | None]:
        res = await asyncio.gather(*[self.block(b) for b in blocks], return_exceptions=True)
        out: dict[str, str | None] = {}
        for b, r in zip(blocks, res):
            if isinstance(r, Exception):
                self.issues.append({"block": b.id, "issues": [f"error:{type(r).__name__}"]})
                out[b.id] = None
            else:
                out[b.id] = r
        return out
