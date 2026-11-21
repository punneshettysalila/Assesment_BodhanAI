"""Split narration into short TTS-friendly chunks (hosted TTS recommends short inputs)."""
from __future__ import annotations

import re

_SENT = re.compile(r"(?<=[.!?।॥])\s+")


def clean_for_speech(text: str) -> str:
    t = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.M)
    t = re.sub(r"[*_`>]+", "", t)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def split_chunks(text: str, max_chars: int = 220) -> list[str]:
    out: list[str] = []
    for sent in _SENT.split(clean_for_speech(text)):
        sent = sent.strip()
        if not sent:
            continue
        if len(sent) <= max_chars:
            out.append(sent)
            continue
        parts, cur = re.split(r"(?<=[,;:])\s+", sent), ""
        for p in parts:
            while len(p) > max_chars:                    # last resort: split on spaces
                cut = p.rfind(" ", 0, max_chars) or max_chars
                if cur:
                    out.append(cur); cur = ""
                out.append(p[:cut].strip()); p = p[cut:].strip()
            if len(cur) + len(p) + 1 > max_chars and cur:
                out.append(cur); cur = ""
            cur = f"{cur} {p}".strip()
        if cur:
            out.append(cur)
    # merge tiny fragments into the previous chunk so pacing stays natural
    merged: list[str] = []
    for c in out:
        if merged and len(c) < 25 and len(merged[-1]) + len(c) + 1 <= max_chars:
            merged[-1] += " " + c
        else:
            merged.append(c)
    return merged
