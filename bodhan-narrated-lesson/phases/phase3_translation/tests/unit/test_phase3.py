import pytest

from bodhan_lesson.assemble.sections import structure_signature
from bodhan_lesson.cache import DiskCache
from bodhan_lesson.glossary.terms import build_glossary, coverage, extract_terms
from bodhan_lesson.models import Block, BlockType, Flag
from bodhan_lesson.translate.check import check_block, normalize_digits, numbers
from bodhan_lesson.translate.engine import Translator, split_long
from bodhan_lesson.translate.mask import lock_terms, mask_latex, unmask
from bodhan_lesson.translate.pivot import build_pivot, similarity

HI = {"parallel lines": "समांतर रेखाएँ", "angle": "कोण", "The": "यह", "is": "है"}


async def fake_hi(text, src, tgt):
    """Mock translator: keeps [[n]] tokens, swaps digits to Devanagari, writes Hindi-script text."""
    out = text
    for k, v in HI.items():
        out = out.replace(k, v)
    out = out.translate(str.maketrans("0123456789", "०१२३४५६७८९"))
    return "अनुवाद " + out + " यह एक परीक्षण वाक्य है जो हिंदी लिपि में लिखा गया है"


def tr(fn=fake_hi, locked=None, tgt="hi", cache=None):
    return Translator(fn, cache or DiskCache(None), "en", tgt, locked=locked)


def test_mask_roundtrip_and_loss_detection():
    m, mp = mask_latex("Angle $\\angle ABC = 90^\\circ$ and $$x+y=180$$ done")
    assert m.count("[[") == 2
    out, ok = unmask(m, mp)
    assert ok and "$\\angle ABC = 90^\\circ$" in out
    _, ok2 = unmask("lost one [[0]]", mp)
    assert not ok2


def test_lock_terms_whole_word():
    m, mp = lock_terms("Parallel lines and angles; angle", {"angle": "कोण"})
    assert "angles" in m and list(mp.values()) == ["कोण"]


def test_numbers_survive_indic_digits():
    assert numbers("angle 30 and 4.5") == numbers("कोण ३० और ४.५")
    assert normalize_digits("१२") == "12"
    assert "numbers_changed" in check_block("angle 30", "कोण ४० " * 3, "hi")


async def test_translate_keeps_latex_numbers_and_flags_skip():
    t = tr()
    good = Block(id="p01-b000", page=1, text="The angle is 30 degrees, $\\angle A = 30^\\circ$.")
    bad = Block(id="p01-b001", page=1, text="@@@@~~~", flags=[Flag.GARBLED])
    eq = Block(id="p01-b002", page=1, type=BlockType.EQUATION, text="$$x+y=180$$")
    out = await t.blocks([good, bad, eq])
    assert "$\\angle A = 30^\\circ$" in out["p01-b000"] and "३०" in out["p01-b000"]
    assert out["p01-b001"] is None and t.skipped[0]["reason"] == ["garbled"]
    assert out["p01-b002"] == "$$x+y=180$$"
    assert t.issues == []


async def test_table_translation_keeps_shape():
    t = tr()
    tbl = Block(id="p02-b000", page=2, type=BlockType.TABLE,
                text="| Name | Value |\n|---|---|\n| angle | 30 |")
    out = (await t.blocks([tbl]))["p02-b000"]
    lines = out.splitlines()
    assert len(lines) == 3 and lines[1] == "|---|---|" and lines[2].count("|") == 3
    assert "30" in lines[2]            # numeric cell untouched


async def test_glossary_lock_and_fallback_when_tokens_dropped():
    async def drops_tokens(text, src, tgt):
        return "अनुवाद " + text.replace("[[0]]", "") + " यह एक परीक्षण वाक्य है जो हिंदी लिपि में है"

    locked_ok = tr(locked={"angle": "कोण"})
    b = Block(id="p01-b000", page=1, text="The angle is acute and this sentence is long enough.")
    assert "कोण" in (await locked_ok.block(b))
    t = tr(fn=drops_tokens, locked={"angle": "कोण"})
    await t.block(b)
    assert t.lock_fallbacks >= 1          # fell back instead of silently losing the term


async def test_changed_numbers_reported_not_hidden():
    async def wrong_numbers(text, src, tgt):
        return "अनुवाद ९९ यह एक परीक्षण वाक्य है जो हिंदी लिपि में लिखा गया है"
    t = tr(fn=wrong_numbers)
    await t.block(Block(id="p01-b000", page=1, text="The angle is 30 degrees in this long sentence."))
    assert t.issues and "numbers_changed" in t.issues[0]["issues"]


def test_split_long_respects_limit():
    parts = split_long("Sentence one. " * 50, 100)
    assert all(len(p) <= 120 for p in parts) and len(parts) > 3


async def test_glossary_build_and_coverage():
    class L:
        async def complete_json(self, s, u):
            return {"terms": ["parallel lines", "angle", "made up term"]}
    text = "Parallel lines never meet. Each angle is measured."
    terms = await extract_terms(L(), text)
    assert terms == ["parallel lines", "angle"]            # hallucinated term rejected
    gl = await build_glossary(terms, fake_hi, "hi", user={"angle": {"hi": "कोण"}})
    assert gl["angle"] == "कोण"
    cov = coverage({"b1": text}, {"b1": "समांतर रेखाएँ कभी नहीं मिलतीं। हर कोण मापा जाता है।"}, gl)
    assert cov["misses"] >= 0 and cov["hits"] >= 1


async def test_pivot_roundtrip_flags_lost_meaning():
    src_blocks = [Block(id="p01-b000", page=1, text="समांतर रेखाएँ कभी नहीं मिलतीं और उनके बीच की दूरी समान रहती है")]

    async def to_en(text, s, t): return "Parallel lines never meet and distance stays equal"
    async def back_bad(text, s, t): return "कुछ और बिल्कुल अलग बात यहाँ लिखी है जो असंबंधित है"
    p, weak = await build_pivot(src_blocks, Translator(to_en, DiskCache(None), "hi", "en"),
                                Translator(back_bad, DiskCache(None), "en", "hi"))
    assert weak and weak[0]["block"] == "p01-b000"
    assert similarity("abc def", "abc def") == 1.0


def test_structure_signature_matches_after_translation():
    src = "# T\n\n| a |\n|---|\n| 1 |\n\n$$x$$\n"
    assert structure_signature(src) == ["H", "T", "E"] == structure_signature(src.replace("T", "शीर्षक"))
