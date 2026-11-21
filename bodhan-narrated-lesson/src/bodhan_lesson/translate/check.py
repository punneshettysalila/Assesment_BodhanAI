"""Post-translation checks: numbers, LaTeX, script, length, emptiness."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from ..languages import script_ratio
from .mask import LATEX

_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def normalize_digits(s: str) -> str:
    return "".join(str(unicodedata.digit(c)) if c.isdigit() and unicodedata.digit(c, None) is not None else c for c in s)


def numbers(text: str) -> Counter:
    return Counter(_NUM.findall(normalize_digits(LATEX.sub(" ", text))))


def latex_spans(text: str) -> Counter:
    return Counter(re.sub(r"\s+", "", m) for m in LATEX.findall(text))


def check_block(src: str, tgt: str, tgt_lang: str, prose: bool = True) -> list[str]:
    issues: list[str] = []
    if not tgt.strip():
        return ["empty_translation"]
    if numbers(src) != numbers(tgt):
        issues.append("numbers_changed")
    if latex_spans(src) != latex_spans(tgt):
        issues.append("latex_changed")
    letters = len(re.findall(r"[^\W\d_]", LATEX.sub("", src)))
    if letters >= 20:
        ratio = len(tgt) / max(len(src), 1)
        if not 0.3 <= ratio <= 3.5:
            issues.append("length_ratio")
    if prose and tgt_lang != "en":
        sr = script_ratio(LATEX.sub("", tgt), tgt_lang)
        if sr is not None and sr < 0.4 and letters >= 20:
            issues.append("wrong_script")
    return issues
