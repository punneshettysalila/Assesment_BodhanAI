import io
import math
import struct
import wave

import pytest

from bodhan_lesson.audio import mix
from bodhan_lesson.models import Block, BlockType
from bodhan_lesson.narrate.chunker import clean_for_speech, split_chunks
from bodhan_lesson.narrate.latex_speech import inline_math_to_speech, latex_to_speech
from bodhan_lesson.narrate.planner import PlanContext, plan_section, table_to_english, table_to_english_deterministic
from bodhan_lesson.speak.verified import analyse, halves, normalise_for_cer, synth_verified


def tone(seconds=1.0, sr=24000, freq=440, amp=0.3):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(b"".join(struct.pack("<h", int(amp * 32767 * math.sin(2 * math.pi * freq * i / sr)))
                               for i in range(int(sr * seconds))))
    return b.getvalue()


def test_latex_speech():
    assert latex_to_speech("$\\angle ABC = 90^\\circ$")[0] == "angle A B C equals 90 degrees"
    assert latex_to_speech("$AB \\parallel CD$")[0] == "A B is parallel to C D"
    assert latex_to_speech("$$\\frac{1}{2} x^2$$")[0] == "1 over 2 x squared"
    s, unk = latex_to_speech("$\\weirdcmd + 3$")
    assert unk == ["\\weirdcmd"] and "3" in s
    assert inline_math_to_speech("so $x + y = 180$ holds")[0] == "so x plus y equals 180 holds"


def test_chunker_limits_and_cleaning():
    text = "First sentence here. " * 30 + "A very long clause, " * 30
    chunks = split_chunks(text, 120)
    assert all(len(c) <= 120 for c in chunks) and len(chunks) > 5
    assert clean_for_speech("<!-- p01-b001 -->\n## Title **bold**") == "Title bold"


def test_table_narration_keeps_numbers():
    md = "| Angle | Value |\n|---|---|\n| A | 30 |\n| B | 60 |"
    det = table_to_english_deterministic(md)
    assert "30" in det and "60" in det and "2 rows" in det


async def test_table_llm_rejected_when_numbers_invented():
    class L:
        async def complete(self, s, u): return "The table lists angle A as 31 and B as 60."
    md = "| Angle | Value |\n|---|---|\n| A | 30 |\n| B | 60 |"
    text, notes = await table_to_english(L(), md)
    assert notes == ["deterministic_fallback"] and "30" in text


async def test_planner_block_types_and_skips():
    async def tr(t, s, l): return f"[{l}] {t}"
    ctx = PlanContext("hi", tr)
    pairs = [
        (Block(id="a", page=1, type=BlockType.HEADING, text="Lines"), "रेखाएँ"),
        (Block(id="b", page=1, type=BlockType.PARAGRAPH, text="x"), "कोण $x + y = 180$ है।"),
        (Block(id="c", page=1, type=BlockType.EQUATION, text="$$\\angle A = 30^\\circ$$"), "$$\\angle A = 30^\\circ$$"),
        (Block(id="d", page=1, type=BlockType.PARAGRAPH, text="bad"), None),
        (Block(id="e", page=1, type=BlockType.TABLE, text="| h |\n|---|\n| 5 |"), "| ह |\n|---|\n| 5 |"),
    ]
    items, skipped = await plan_section(pairs, ctx)
    assert [i.kind for i in items] == ["heading", "prose", "equation", "table"]
    assert "x plus y equals 180" in items[1].text
    assert items[2].text.startswith("[hi] Equation: angle A equals 30 degrees")
    assert skipped == [{"block": "d", "reason": "ocr_doubtful_or_untranslatable"}]


def test_cer_analysis_detects_repeat_and_omission():
    ref = "समांतर रेखाएँ कभी नहीं मिलतीं"
    cer, fl = analyse(ref, ref, 3.0, {})
    assert cer == 0 and fl == []
    cer, fl = analyse(ref, ref + " " + ref, 6.0, {})
    assert "repeat_suspected" in fl
    cer, fl = analyse(ref, "समांतर", 1.0, {})
    assert "omission_suspected" in fl
    assert normalise_for_cer("Angle ३० है!") == "angle है"


async def test_synth_verified_retry_then_ok():
    text = "यह एक छोटा परीक्षण वाक्य है।"
    calls = {"n": 0}

    async def speak(t, lang, voice): return tone(2.0)

    async def asr(wav, lang):
        calls["n"] += 1
        return "कुछ" if calls["n"] == 1 else text.replace("।", "")     # first take is an omission

    r = await synth_verified(text, "hi", None, speak, asr, {"max_cer": 0.12, "max_retries": 3})
    assert r.status == "retried_ok" and r.attempts == 2 and r.cer == 0


async def test_synth_verified_degraded_ships_best_and_asr_outage_is_unverified():
    async def speak(t, lang, voice): return tone(1.0)
    async def bad(wav, lang): return "बिल्कुल अलग"
    r = await synth_verified("यह एक लंबा वाक्य है जो नहीं मिलेगा", "hi", None, speak, bad, {"max_retries": 2})
    assert r.status == "degraded" and "shipped_best_attempt" in r.flags

    async def down(wav, lang): raise RuntimeError("asr down")
    r2 = await synth_verified("छोटा वाक्य", "hi", None, speak, down, {})
    assert r2.status == "unverified" and r2.wav


def test_halves_and_wav_helpers():
    a, b = halves("एक दो तीन, चार पांच छह")
    assert a and b
    w1, w2 = tone(1.0), tone(1.0)
    both = mix.concat_wavs([w1, w2], 0.5)
    assert abs(mix.wav_info(both)[1] - 2.5) < 0.01
    assert len(mix.split_wav(tone(65.0, sr=8000), 28)) == 3


@pytest.mark.skipif(not mix.have_ffmpeg(), reason="ffmpeg required")
def test_loudnorm_and_chapters(tmp_path):
    raw = tmp_path / "raw.wav"
    raw.write_bytes(tone(6.0, amp=0.05))
    meta, js = tmp_path / "ch.txt", tmp_path / "ch.json"
    chapters = mix.write_chapters([("One", 3.0), ("Two", 3.0)], meta, js)
    assert chapters[1]["start_s"] == 3.0
    out = tmp_path / "out.mp3"
    lufs = mix.normalise(raw, out, chapters_file=meta, metadata={"comment": "AI-generated narration"})
    assert lufs is not None and abs(lufs + 16) <= 1.0
