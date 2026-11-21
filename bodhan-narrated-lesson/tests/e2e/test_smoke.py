"""End-to-end run with faked Bodhan models: proves orchestration, isolation and outputs."""
import io
import json
import math
import re
import struct
import wave
from pathlib import Path

import cv2
import numpy as np
import pytest

from bodhan_lesson.cli import main
from bodhan_lesson.memory.cases import CaseMemory
from bodhan_lesson.models import Block, BlockType
from bodhan_lesson.pipeline import RunOptions, run_pipeline
from bodhan_lesson.report.collector import Report

PAGES = {
    1: "# 6.1 Lines and Angles\n\nParallel lines never meet in a plane.\n\nThe sum of the angles in a triangle is\n\nwww.example-site.com study material",
    2: "180 degrees.\n\n| Name | Value |\n|---|---|\n| A | 30 |\n\n$$\\angle ABC = 90^\\circ$$\n\nwww.example-site.com study material",
    3: "## 6.2 Summary\n\nLines are everywhere in daily life.\n\nwww.example-site.com study material",
}
TAIL = {"hi": " यह एक परीक्षण वाक्य है जो हिंदी लिपि में लिखा गया है", "ta": " இது ஒரு சோதனை வாக்கியம் தமிழ் எழுத்தில் எழுதப்பட்டது"}
DIG = {"hi": "०१२३४५६७८९", "ta": "௦௧௨௩௪௫௬௭௮௯"}


def tone(seconds, sr=16000):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(9000 * math.sin(2 * math.pi * 300 * i / sr)))
                               for i in range(int(sr * seconds))))
    return b.getvalue()


class FakeBodhan:
    def __init__(self, break_lang=None):
        self.break_lang, self.spoken = break_lang, {}
        self.calls = {"ocr": 0, "translate": 0, "speak": 0, "transcribe": 0}

    @property
    def stats(self):
        z = {"calls": 0, "retries": 0, "failures": 0, "latency_s": 0.0, "cost_inr": 0.1, "units": 0.0}
        return {k: dict(z, calls=v) for k, v in self.calls.items()}

    async def ocr(self, path):
        self.calls["ocr"] += 1
        n = int(re.search(r"(\d+)", Path(path).name).group(1))
        return PAGES[n]

    async def translate(self, text, src, tgt):
        self.calls["translate"] += 1
        out = text.translate(str.maketrans("0123456789", DIG[tgt]))
        return "अनुवाद " + out + TAIL[tgt]

    async def speak(self, text, lang, voice=None):
        self.calls["speak"] += 1
        if lang == self.break_lang:
            raise RuntimeError("tts unavailable for this language")
        wav = tone(max(0.6, min(len(text) * 0.05, 12)))
        self.spoken[hash(wav)] = text
        return wav

    async def transcribe(self, wav, lang):
        self.calls["transcribe"] += 1
        return self.spoken.get(hash(wav), "")


@pytest.fixture
def scans(tmp_path):
    d = tmp_path / "scans"
    d.mkdir()
    for n in (1, 2, 3):
        img = np.full((300, 220), 255, np.uint8)
        cv2.putText(img, f"P{n}", (60, 150), cv2.FONT_HERSHEY_SIMPLEX, 2, 0, 4)   # distinct bytes per page (OCR cache is content-addressed)
        cv2.imwrite(str(d / f"page-{n}.png"), img)
    return d


async def run(scans, out, langs, bodhan, **kw):
    opts = RunOptions(input=scans, out=out, langs=langs, source_lang="en", **kw)
    rep = Report()
    code = await run_pipeline(opts, bodhan, None, {}, rep)
    rep.write(out / "report.json")
    return code, json.loads((out / "report.json").read_text(encoding="utf-8"))


async def test_full_run_two_languages(scans, tmp_path):
    out = tmp_path / "out"
    code, rep = await run(scans, out, ["hi", "ta"], FakeBodhan())
    assert code == 0, rep
    src = (out / "source" / "lesson.src.md").read_text(encoding="utf-8")
    assert "example-site" not in src and "triangle is 180 degrees." in src       # footer gone, page-break joined
    assert rep["source"]["removed_chrome"] == 3
    for lang in ("hi", "ta"):
        L = rep["languages"][lang]
        assert L["status"] == "ok" and L["structure_ok"] is True
        md = (out / lang / f"lesson.{lang}.md").read_text(encoding="utf-8")
        assert "$$\\angle ABC = 90^\\circ$$" in md and md.count("|---|---|") == 1
        assert len(L["sections"]) == 2 and all(s["file"] for s in L["sections"])
        assert (out / lang / f"lesson.{lang}.mp3").exists() and L["chapters"] == 2
        assert L["targets"]["loudness_ok"] is True, L["targets"]
        assert L["targets"]["section_mean_cer"] == 0 and L["targets"]["numbers_latex_issues"] == 0
        assert (out / L["sections"][0]["file"]).exists()
        assert (out / lang / f"narration_script.{lang}.json").exists()
        assert (out / lang / "narration").exists()
    assert rep["usage"]["total_cost_inr"] > 0
    assert rep["pages"]["1"]["ocr_attempts"] == 1
    assert (out / "source" / "pages" / "page-001.json").exists()


async def test_language_failure_is_isolated_and_cache_reused(scans, tmp_path):
    out = tmp_path / "out"
    code, rep = await run(scans, out, ["hi", "ta"], FakeBodhan(break_lang="ta"))
    assert code == 1
    assert rep["languages"]["hi"]["status"] == "ok" and rep["languages"]["ta"]["status"] == "failed"
    assert (out / "hi" / "lesson.hi.mp3").exists()
    # rerun: OCR + translation come from cache -> zero repeat calls to paid text models
    b2 = FakeBodhan()
    await run(scans, out, ["hi"], b2)
    assert b2.calls["ocr"] == 0 and b2.calls["translate"] == 0


async def test_no_audio_mode_and_flagged_blocks_withheld(scans, tmp_path, monkeypatch):
    PAGES[3] = "## 6.2 Summary\n\n\ufffd\ufffd\ufffd broken \ufffd\ufffd\n\nLines are everywhere in daily life.\n\nwww.example-site.com study material"
    try:
        out = tmp_path / "out"
        code, rep = await run(scans, out, ["hi"], FakeBodhan(), no_audio=True)
        assert code == 0 and rep["languages"]["hi"]["status"] == "partial"
        assert rep["languages"]["hi"]["skipped_blocks"] and "broken" not in (out / "hi" / "lesson.hi.md").read_text(encoding="utf-8")
        assert rep["source"]["flagged_blocks"] == 1
    finally:
        PAGES[3] = "## 6.2 Summary\n\nLines are everywhere in daily life.\n\nwww.example-site.com study material"


async def test_max_cost_stops_remaining_section_audio(scans, tmp_path):
    out = tmp_path / "budget-out"
    code, rep = await run(scans, out, ["hi"], FakeBodhan(), max_cost_inr=0.1)
    assert code == 0
    assert rep["languages"]["hi"]["status"] == "partial"
    assert any(w["msg"] == "audio stopped: INR cost budget reached" for w in rep["warnings"])


def test_cli_exits_2_without_keys(tmp_path, monkeypatch):
    for k in ("BODHAN_OCR_KEY", "BODHAN_TRANSLATE_KEY", "BODHAN_SPEAK_KEY", "BODHAN_TRANSCRIBE_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert main(["--input", str(tmp_path), "--out", str(tmp_path / "o"), "--langs", "hi",
                 "--env-file", str(tmp_path / "none.env")]) == 2


def test_case_memory_records_only_nontrivial_verified_decisions(tmp_path):
    mk = lambda i, bb: Block(id=f"p01-b{i:03d}", page=1, text=f"t{i}", bbox=bb, order=i)
    blocks = [mk(0, (0.1, 0.02, 0.9, 0.08)), mk(1, (0.08, 0.12, 0.47, 0.3)), mk(2, (0.53, 0.12, 0.92, 0.3)),
              mk(3, (0.08, 0.33, 0.47, 0.6)), mk(4, (0.53, 0.33, 0.92, 0.6))]
    mem = CaseMemory(tmp_path / "cases.jsonl")
    mem.record(blocks, [b.id for b in blocks], "llm")                     # identity: ignored
    mem.record(blocks, ["p01-b000", "p01-b001", "p01-b003", "p01-b002", "p01-b004"], "xycut_fallback")  # unverified
    assert mem.cases == []
    mem.record(blocks, ["p01-b000", "p01-b001", "p01-b003", "p01-b002", "p01-b004"], "llm")
    assert len(mem.cases) == 1 and "[0, 1, 3, 2, 4]" in mem.examples(blocks)
    assert "t0" not in json.dumps(mem.cases)                              # structure only, never page text
    assert len(CaseMemory(tmp_path / "cases.jsonl").cases) == 1           # persisted
