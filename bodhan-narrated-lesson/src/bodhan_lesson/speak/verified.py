"""Verified speech synthesis: Indic-Speak -> Indic-Transcribe -> CER, with targeted retries.
Detects repeated / omitted passages from character-level alignment + duration sanity."""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import jiwer

from ..audio.mix import concat_wavs, split_wav, wav_info
from ..translate.check import normalize_digits

log = logging.getLogger("bodhan_lesson.speak")
SpeakFn = Callable[[str, str, str | None], Awaitable[bytes]]
TranscribeFn = Callable[[bytes, str], Awaitable[str]]


@dataclass
class ChunkResult:
    text: str
    wav: bytes
    seconds: float
    cer: float | None
    attempts: int
    status: str                       # ok | retried_ok | degraded | unverified | failed
    flags: list[str] = field(default_factory=list)


def normalise_for_cer(s: str, ignore_digits: bool = True) -> str:
    s = unicodedata.normalize("NFC", normalize_digits(s)).lower()
    # keep letters, combining marks (Indic vowel signs!), digits, spaces; drop punctuation/symbols
    s = "".join(c if (unicodedata.category(c)[0] in "LMN" or c.isspace()) else " " for c in s)
    if ignore_digits:                      # ASR may write numbers as words or digits
        s = re.sub(r"\d+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def analyse(ref: str, hyp: str, seconds: float, cfg: dict) -> tuple[float, list[str]]:
    r, h = normalise_for_cer(ref, cfg.get("ignore_digits", True)), normalise_for_cer(hyp, cfg.get("ignore_digits", True))
    flags: list[str] = []
    if not r:
        return 0.0, flags
    if not h:
        return 1.0, ["empty_transcript"]
    out = jiwer.process_characters(r, h)
    n = max(len(r), 1)
    cer = (out.substitutions + out.deletions + out.insertions) / n
    if out.insertions / n > cfg.get("repeat_ratio", 0.25):
        flags.append("repeat_suspected")
    if out.deletions / n > cfg.get("omit_ratio", 0.25):
        flags.append("omission_suspected")
    spc = seconds / max(len(ref), 1)
    if spc < cfg.get("min_sec_per_char", 0.02):
        flags.append("too_short_for_text")
    if spc > cfg.get("max_sec_per_char", 0.40):
        flags.append("too_long_for_text")
    return cer, flags


def simplify(text: str) -> str:
    t = re.sub(r"[()\[\]{}\"“”‘’«»]", " ", text)
    t = t.replace(";", ",").replace("—", ",").replace("–", ",")
    return re.sub(r"\s+", " ", t).strip()


def halves(text: str) -> list[str]:
    mid = len(text) // 2
    cands = [m.end() for m in re.finditer(r"[.!?।॥,;:]\s+|\s+", text)]
    cut = min(cands, key=lambda i: abs(i - mid)) if cands else mid
    a, b = text[:cut].strip(), text[cut:].strip()
    return [x for x in (a, b) if x]


async def _transcribe(wav: bytes, lang: str, tfn: TranscribeFn, max_s: float) -> str:
    parts = split_wav(wav, max_s)
    return " ".join([await tfn(p, lang) for p in parts])


async def _attempt(text: str, lang: str, voice, speak: SpeakFn, tfn: TranscribeFn | None, cfg: dict):
    wav = await speak(text, lang, voice)
    _, secs = wav_info(wav)
    if tfn is None:
        return wav, secs, None, ["unverified"]
    try:
        hyp = await _transcribe(wav, lang, tfn, cfg.get("max_audio_seconds", 28))
    except Exception as e:                      # ASR down must not kill narration
        log.warning("verify_failed", extra={"err": str(e)})
        return wav, secs, None, ["unverified"]
    cer, flags = analyse(text, hyp, secs, cfg)
    return wav, secs, cer, flags


async def synth_verified(text: str, lang: str, voice: str | None, speak: SpeakFn,
                         tfn: TranscribeFn | None, cfg: dict) -> ChunkResult:
    max_cer, max_retries = cfg.get("max_cer", 0.12), cfg.get("max_retries", 3)
    best: ChunkResult | None = None
    variants = [lambda: [text], lambda: [simplify(text)], lambda: halves(text)]
    for n in range(1, max_retries + 1):
        pieces = variants[min(n - 1, 2)]()
        try:
            res = [await _attempt(p, lang, voice, speak, tfn, cfg) for p in pieces]
        except Exception as e:
            log.error("speak_failed", extra={"attempt": n, "err": str(e)})
            continue
        wavs = [r[0] for r in res]
        wav = wavs[0] if len(wavs) == 1 else concat_wavs(wavs, 0.12)
        cers = [r[2] for r in res if r[2] is not None]
        flags = sorted({f for r in res for f in r[3]})
        cer = sum(cers) / len(cers) if cers else None
        status = ("unverified" if cer is None else
                  "ok" if n == 1 else "retried_ok") if (cer is None or (cer <= max_cer and not
                  {"repeat_suspected", "omission_suspected"} & set(flags))) else "degraded"
        cur = ChunkResult(text, wav, wav_info(wav)[1], cer, n, status, flags)
        if best is None or (cur.cer is not None and (best.cer is None or cur.cer < best.cer)):
            best = cur
        if status in ("ok", "retried_ok", "unverified"):
            best = cur
            break
    if best is None:
        return ChunkResult(text, b"", 0.0, None, max_retries, "failed", ["synthesis_failed"])
    if best.status == "degraded":
        best.flags.append("shipped_best_attempt")
    return best
