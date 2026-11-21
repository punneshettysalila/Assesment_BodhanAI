import cv2
import numpy as np
import pytest

from bodhan_lesson.assemble.headers_footers import content_blocks, strip_running
from bodhan_lesson.assemble.joiner import join_across_pages
from bodhan_lesson.assemble.sections import build_sections, render_markdown, structure_signature
from bodhan_lesson.ingest import quality
from bodhan_lesson.layout.llm_order import repair_order
from bodhan_lesson.layout.xycut import xy_cut_order
from bodhan_lesson.models import Block, BlockType, Flag, Page
from bodhan_lesson.ocr.doubt import assess, latex_balanced
from bodhan_lesson.ocr.parse import parse_ocr_response

MD = """# 6.1 Introduction

In earlier classes, you have studied lines.

| Angle | Value |
|---|---|
| A | 30 |

$$\\angle ABC = 90^\\circ$$

- one
- two
"""


def test_parse_markdown_types():
    bs = parse_ocr_response(1, MD)
    assert [b.type for b in bs] == [BlockType.HEADING, BlockType.PARAGRAPH, BlockType.TABLE,
                                    BlockType.EQUATION, BlockType.LIST]
    assert bs[0].text == "6.1 Introduction" and bs[0].id == "p01-b000"


def test_parse_json_blocks_with_bbox():
    raw = '{"blocks":[{"type":"paragraph","text":"hello","bbox":[0,0,1,0.1],"confidence":0.5}]}'
    b = parse_ocr_response(2, raw)[0]
    assert b.bbox == (0, 0, 1, 0.1) and b.confidence == 0.5


def test_doubt_flags():
    cfg = {"ocr": {"min_confidence": 0.8, "max_garbage_ratio": 0.15}}
    ok = Block(id="a", page=1, text="Two lines are parallel.", confidence=0.95)
    bad = Block(id="b", page=1, text="@@#~~^^ ¤¤§§ ¶¶ ȹȹ", confidence=0.4)
    assert assess(ok, cfg) == []
    f = assess(bad, cfg)
    assert Flag.GARBLED in f and Flag.LOW_CONFIDENCE in f
    assert not latex_balanced("$\\frac{a}{b$") and latex_balanced("$\\frac{a}{b}$")


def test_header_footer_generic_removal():
    pages = []
    for n in range(1, 6):
        blocks = [Block(id=f"p{n:02d}-b000", page=n, text=["Parallel lines never meet","Angle sum of a triangle","Vertically opposite angles","Linear pair axiom","Proof by contradiction"][n-1], order=0),
                  Block(id=f"p{n:02d}-b001", page=n, text="www.example-site.com Free study material", order=1)]
        pages.append(Page(number=n, image_path="x", blocks=blocks))
    removed = strip_running(pages, {})
    assert len(removed) == 5
    assert all("example-site" not in b.text for b in content_blocks(pages))


def test_join_paragraph_and_table():
    a = Block(id="p01-b009", page=1, type=BlockType.PARAGRAPH, text="the sum of angles is", order=9)
    b = Block(id="p02-b000", page=2, type=BlockType.PARAGRAPH, text="180 degrees.", order=0)
    t1 = Block(id="p02-b001", page=2, type=BlockType.TABLE, text="| a | b |\n|---|---|\n| 1 | 2 |", order=1)
    t2 = Block(id="p03-b000", page=3, type=BlockType.TABLE, text="| a | b |\n|---|---|\n| 3 | 4 |", order=0)
    out = join_across_pages([a, b, t1, t2])
    assert out[0].text == "the sum of angles is 180 degrees." and Flag.SPLIT_ACROSS_PAGE in out[0].flags
    assert out[0].intact()
    assert "| 3 | 4 |" in out[1].text and out[1].text.count("|---|") == 1


def test_sections_markdown_and_signature():
    bs = parse_ocr_response(1, MD)
    secs = build_sections(bs)
    md = render_markdown(secs)
    assert secs[0].slug == "6-1-introduction"
    assert structure_signature(md) == ["H", "T", "E"]
    assert "<!-- p01-b003 -->" in md


def _two_col():
    mk = lambda i, bb: Block(id=f"p01-b{i:03d}", page=1, text=f"t{i}", bbox=bb, order=i)
    # OCR emitted rows left-right-left-right; correct reading = title, left col, right col
    return [mk(0, (0.1, 0.02, 0.9, 0.08)), mk(1, (0.08, 0.12, 0.47, 0.30)), mk(2, (0.53, 0.12, 0.92, 0.30)),
            mk(3, (0.08, 0.33, 0.47, 0.60)), mk(4, (0.53, 0.33, 0.92, 0.60))]


def test_xycut_two_columns():
    ids = [b.id for b in xy_cut_order(_two_col())]
    assert ids == ["p01-b000", "p01-b001", "p01-b003", "p01-b002", "p01-b004"]


class FakeLLM:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    async def complete_json(self, system, user):
        self.calls += 1
        return self.replies.pop(0)


async def test_llm_order_rejects_bad_then_accepts():
    blocks = _two_col()
    good = ["p01-b000", "p01-b001", "p01-b003", "p01-b002", "p01-b004"]
    llm = FakeLLM([{"order": ["p01-b000", "p01-b000"]}, {"order": good}])
    ordered, rec = await repair_order(blocks, llm)
    assert [b.id for b in ordered] == good and rec["method"] == "llm" and llm.calls == 2


async def test_llm_order_falls_back_to_xycut():
    llm = FakeLLM([{"order": ["x"]}, {"order": ["y"]}])
    ordered, rec = await repair_order(_two_col(), llm)
    assert rec["method"] == "xycut_fallback" and ordered[2].id == "p01-b003"


def test_quality_skew_and_deskew(tmp_path):
    img = np.full((600, 500), 255, np.uint8)
    for y in range(60, 560, 18):
        cv2.line(img, (40, y), (460, y), 0, 5)
    m = cv2.getRotationMatrix2D((250, 300), 3.0, 1.0)
    tilted = cv2.warpAffine(img, m, (500, 600), borderValue=255)
    p = tmp_path / "t.png"
    cv2.imwrite(str(p), tilted)
    q = quality.measure(str(p))
    assert abs(abs(q["skew_deg"]) - 3.0) <= 0.75
    out, q2 = quality.prepare(str(p), tmp_path)
    assert q2["deskewed"] and abs(quality.measure(out)["skew_deg"]) <= 0.75
