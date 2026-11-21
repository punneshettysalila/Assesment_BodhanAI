"""Protect LaTeX (and glossary-locked terms) from the translator with placeholders."""
from __future__ import annotations

import re

LATEX = re.compile(r"\$\$.+?\$\$|\$[^$\n]+?\$|\\\(.+?\\\)|\\\[.+?\\\]", re.DOTALL)
MASK_RE = re.compile(r"\[\[(\d+)\]\]")


def mask_latex(text: str, start: int = 0) -> tuple[str, dict[int, str]]:
    mapping: dict[int, str] = {}

    def sub(m: re.Match) -> str:
        i = start + len(mapping)
        mapping[i] = m.group(0)
        return f"[[{i}]]"

    return LATEX.sub(sub, text), mapping


def lock_terms(text: str, terms: dict[str, str], start: int = 0) -> tuple[str, dict[int, str]]:
    """Replace whole-word occurrences of English terms by placeholders mapped to their target rendering."""
    mapping: dict[int, str] = {}
    for term in sorted(terms, key=len, reverse=True):
        pat = re.compile(r"(?<!\w)" + re.escape(term) + r"(?!\w)", re.I)

        def sub(m: re.Match, tgt=terms[term]) -> str:
            i = start + len(mapping)
            mapping[i] = tgt
            return f"[[{i}]]"

        text = pat.sub(sub, text)
    return text, mapping


def unmask(text: str, mapping: dict[int, str]) -> tuple[str, bool]:
    """Restore placeholders. Returns (text, ok) where ok means every placeholder came back exactly once, in order."""
    found = [int(m) for m in MASK_RE.findall(text)]
    ok = found == sorted(mapping) 
    out = MASK_RE.sub(lambda m: mapping.get(int(m.group(1)), m.group(0)), text)
    return out, ok and not MASK_RE.search(out)
