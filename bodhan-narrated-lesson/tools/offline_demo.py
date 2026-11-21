#!/usr/bin/env python
"""Offline demo: runs the REAL pipeline with SIMULATED models (no API keys, no network).

!!  The OCR / translation / speech / ASR here are fakes (canned markdown, tagged text, sine tones).
!!  They exist so you can see the full output tree, report.json and report.html, and capture
!!  screenshots, without credits. Never submit these outputs as results. The real run uses Bodhan.

    python tools/offline_demo.py --out out/offline_demo
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import math
import re
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from bodhan_lesson.pipeline import RunOptions, run_pipeline  # noqa: E402
from bodhan_lesson.report.collector import Report  # noqa: E402

PAGES = {
    1: "# 6.1 Lines and Angles\n\nParallel lines never meet in a plane.\n\nThe sum of the angles in a triangle is\n\nwww.example-site.com free study material",
    2: "180 degrees.\n\n| Angle | Value |\n|---|---|\n| A | 30 |\n| B | 60 |\n\n$$\\angle ABC = 90^\\circ$$\n\nwww.example-site.com free study material",
    3: "## 6.2 Summary\n\nLines and angles are everywhere in daily life.\n\n- Parallel lines\n- Transversals\n\nwww.example-site.com free study material",
}
TAIL = {"hi": " यह एक परीक्षण वाक्य है जो हिंदी लिपि में लिखा गया है",
        "ta": " இது ஒரு சோதனை வாக்கியம் தமிழ் எழுத்தில் எழுதப்பட்டது",
        "bn": " এটি বাংলা লিপিতে লেখা একটি পরীক্ষামূলক বাক্য"}
DIG = {"hi": "०१२३४५६७८९", "ta": "௦௧௨௩௪௫௬௭௮௯", "bn": "০১২৩৪৫৬৭৮৯"}


def tone(seconds: float, sr: int = 16000) -> bytes:
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(9000 * math.sin(2 * math.pi * 300 * i / sr)))
                               for i in range(int(sr * seconds))))
    return b.getvalue()


class SimulatedBodhan:
    """Same interface as clients.bodhan.Bodhan, with canned behaviour."""

    def __init__(self):
        self.spoken: dict[int, str] = {}
        self.calls = {"ocr": 0, "translate": 0, "speak": 0, "transcribe": 0}

    @property
    def stats(self):
        base = {"calls": 0, "retries": 0, "failures": 0, "latency_s": 0.0, "units": 0.0}
        price = {"ocr": 0.20, "translate": 0.02, "speak": 0.30, "transcribe": 0.02}
        return {k: dict(base, calls=v, cost_inr=round(v * price[k], 3)) for k, v in self.calls.items()}

    async def ocr(self, path):
        self.calls["ocr"] += 1
        return PAGES[int(re.search(r"(\d+)", Path(path).name).group(1))]

    async def translate(self, text, src, tgt):
        self.calls["translate"] += 1
        return "अनुवाद " + text.translate(str.maketrans("0123456789", DIG[tgt])) + TAIL[tgt]

    async def speak(self, text, lang, voice=None):
        self.calls["speak"] += 1
        wav = tone(max(0.6, min(len(text) * 0.05, 12)))
        self.spoken[hash(wav)] = text
        return wav

    async def transcribe(self, wav, lang):
        self.calls["transcribe"] += 1
        return self.spoken.get(hash(wav), "")

    async def aclose(self):
        pass


def make_scans(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for n, text in PAGES.items():
        img = np.full((560, 400), 250, np.uint8)
        y = 40
        for para in text.split("\n\n"):
            for line in para.splitlines()[:4]:
                cv2.putText(img, line[:40], (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, 20, 1, cv2.LINE_AA)
                y += 20
            y += 14
        cv2.imwrite(str(folder / f"page-{n}.png"), img)


async def main(out: Path, langs: list[str]) -> int:
    scans = out / "synthetic_scans"
    make_scans(scans)
    (out / "OFFLINE_DEMO_NOT_REAL_BODHAN.txt").write_text(
        "These outputs were produced with SIMULATED models (tools/offline_demo.py). Not real Bodhan results.\n")
    report = Report()
    report.warn("OFFLINE DEMO: models are simulated, outputs are not real Bodhan results")
    opts = RunOptions(input=scans, out=out, langs=langs, source_lang="en")
    code = await run_pipeline(opts, SimulatedBodhan(), None, {}, report)
    report.write(out / "report.json")
    print(f"offline demo finished (exit {code}); open {out / 'report.html'}")
    return code


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "out" / "offline_demo")
    ap.add_argument("--langs", default="hi,ta,bn")
    a = ap.parse_args()
    sys.exit(asyncio.run(main(a.out, a.langs.split(","))))
