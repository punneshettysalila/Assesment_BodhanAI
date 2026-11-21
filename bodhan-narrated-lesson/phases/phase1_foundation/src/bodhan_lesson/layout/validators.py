"""Guards that make the LLM rules enforceable in code.

Rules from the assignment:
  * The LLM may reorder / flag OCR blocks BY REFERENCE (ids), never touch text.
  * The LLM may edit ENGLISH text only, and must not alter numbers or LaTeX.
  * It must never write or rewrite Indian-language text.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from ..models import Block, Flag


class GuardViolation(ValueError):
    """Raised when an LLM response breaks a rule. Callers retry or fall back."""


def validate_reorder(blocks: list[Block], proposed_ids: list[str]) -> list[Block]:
    """Proposed order must be an exact permutation of the input block ids."""
    known = {b.id: b for b in blocks}
    if len(proposed_ids) != len(set(proposed_ids)):
        dup = [i for i, c in Counter(proposed_ids).items() if c > 1]
        raise GuardViolation(f"duplicate ids in reorder: {dup}")
    unknown = [i for i in proposed_ids if i not in known]
    if unknown:
        raise GuardViolation(f"unknown ids in reorder: {unknown}")
    missing = [i for i in known if i not in set(proposed_ids)]
    if missing:
        raise GuardViolation(f"reorder dropped ids: {missing}")
    original_ids = [b.id for b in blocks]
    ordered = [known[i] for i in proposed_ids]
    for n, b in enumerate(ordered):
        b.order = n
        if proposed_ids[n] != original_ids[n] and Flag.REORDERED not in b.flags:
            b.flags.append(Flag.REORDERED)
    return ordered


def validate_flags(blocks: list[Block], proposed: dict[str, list[str]]) -> dict[str, list[Flag]]:
    """LLM may flag blocks by id using known flag names only."""
    known = {b.id for b in blocks}
    valid = {f.value for f in Flag}
    out: dict[str, list[Flag]] = {}
    for bid, flags in proposed.items():
        if bid not in known:
            raise GuardViolation(f"flag for unknown id: {bid}")
        bad = [f for f in flags if f not in valid]
        if bad:
            raise GuardViolation(f"unknown flags for {bid}: {bad}")
        out[bid] = [Flag(f) for f in flags]
    return out


def assert_text_intact(blocks: list[Block]) -> None:
    """After any LLM step, no block's OCR text may have changed."""
    tampered = [b.id for b in blocks if not b.intact()]
    if tampered:
        raise GuardViolation(f"OCR text modified for blocks: {tampered}")


# ---- English-only edit guard -------------------------------------------------

_LATEX = re.compile(r"\$\$.+?\$\$|\$.+?\$|\\\(.+?\\\)|\\\[.+?\\\]", re.DOTALL)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def latin_ratio(text: str) -> float:
    """Share of alphabetic characters that are Latin script."""
    letters = [c for c in _LATEX.sub("", text) if c.isalpha()]
    if not letters:
        return 1.0
    latin = sum(1 for c in letters if "LATIN" in unicodedata.name(c, ""))
    return latin / len(letters)


def is_english(text: str, threshold: float = 0.95) -> bool:
    return latin_ratio(text) >= threshold


def validate_english_edit(original: str, edited: str) -> str:
    """Accept an LLM edit only if the text is English and numbers + LaTeX survive."""
    if not is_english(original):
        raise GuardViolation("LLM may not edit non-English text")
    if not is_english(edited):
        raise GuardViolation("LLM edit introduced non-English text")
    if Counter(_LATEX.findall(original)) != Counter(_LATEX.findall(edited)):
        raise GuardViolation("LaTeX changed by LLM edit")
    if Counter(_NUMBER.findall(_LATEX.sub("", original))) != Counter(_NUMBER.findall(_LATEX.sub("", edited))):
        raise GuardViolation("numbers changed by LLM edit")
    return edited
