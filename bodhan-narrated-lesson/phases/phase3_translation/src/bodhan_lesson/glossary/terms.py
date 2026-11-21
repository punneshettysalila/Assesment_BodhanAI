"""Per-chapter glossary: LLM picks English key terms (validated against the text),
Indic-Translate renders each once per language, and user glossary.yaml overrides win."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from ..clients.llm import LLM

SYSTEM = ("From this English textbook chapter text pick the key technical terms a student must learn "
          "(2-4 words max each, no sentences). Reply JSON only: {\"terms\": [\"...\"]}. Max {n} terms.")


def _in_text(term: str, text: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text, re.I) is not None


async def extract_terms(llm: LLM | None, english_text: str, max_terms: int = 40) -> list[str]:
    if llm is None:
        return []
    try:
        data = await llm.complete_json(SYSTEM.replace("{n}", str(max_terms)), english_text[:12000])
        terms = [str(t).strip() for t in data.get("terms", [])]
    except Exception:
        return []
    seen, out = set(), []
    for t in terms:
        k = t.lower()
        if t and k not in seen and len(t.split()) <= 4 and _in_text(t, english_text):   # reject hallucinations
            seen.add(k)
            out.append(t)
    return out[:max_terms]


def load_user_glossary(path: Path | None) -> dict[str, dict[str, str]]:
    if not path or not Path(path).exists():
        return {}
    raw = yaml.safe_load(Path(path).read_text()) or {}
    return {str(k): {str(l): str(v) for l, v in (vals or {}).items()} for k, vals in raw.items()}


async def build_glossary(terms: list[str], translate_fn, tgt: str,
                         user: dict[str, dict[str, str]] | None = None) -> dict[str, str]:
    """English term -> target-language rendering (user overrides first)."""
    user = user or {}
    out: dict[str, str] = {}
    for t in terms:
        if t in user and tgt in user[t]:
            out[t] = user[t][tgt]
        else:
            out[t] = (await translate_fn(t, "en", tgt)).strip().strip(".")
    for t, per in user.items():
        if tgt in per:
            out[t] = per[tgt]
    return {k: v for k, v in out.items() if v}


def coverage(en_blocks: dict[str, str], tgt_blocks: dict[str, str | None], glossary: dict[str, str]) -> dict:
    """How consistently each term's chosen rendering appears where the English term occurs."""
    hits = misses = 0
    miss_list = []
    for bid, en in en_blocks.items():
        tgt = tgt_blocks.get(bid)
        if not tgt:
            continue
        for term, rendering in glossary.items():
            if _in_text(term, en):
                stem = rendering[:-1] if len(rendering) > 3 else rendering      # tolerate inflection
                if stem in tgt:
                    hits += 1
                else:
                    misses += 1
                    miss_list.append({"block": bid, "term": term})
    total = hits + misses
    return {"hits": hits, "misses": misses, "consistency": round(hits / total, 3) if total else None,
            "miss_examples": miss_list[:10]}
