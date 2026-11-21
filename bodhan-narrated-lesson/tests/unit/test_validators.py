import pytest

from bodhan_lesson.layout.validators import (
    GuardViolation, assert_text_intact, is_english,
    validate_english_edit, validate_flags, validate_reorder,
)
from bodhan_lesson.models import Block, Flag


def mk(n):
    return [Block(id=f"p01-b{i:03d}", page=1, text=f"text {i}", order=i) for i in range(n)]


def test_reorder_accepts_permutation_and_flags_moved():
    blocks = mk(3)
    out = validate_reorder(blocks, ["p01-b001", "p01-b000", "p01-b002"])
    assert [b.id for b in out] == ["p01-b001", "p01-b000", "p01-b002"]
    assert Flag.REORDERED in out[0].flags and Flag.REORDERED in out[1].flags
    assert Flag.REORDERED not in out[2].flags


@pytest.mark.parametrize("bad", [
    ["p01-b000", "p01-b000", "p01-b002"],   # duplicate
    ["p01-b000", "p01-b001"],                # dropped
    ["p01-b000", "p01-b001", "p01-b999"],   # unknown
])
def test_reorder_rejects_non_permutations(bad):
    with pytest.raises(GuardViolation):
        validate_reorder(mk(3), bad)


def test_flags_validation():
    blocks = mk(2)
    assert validate_flags(blocks, {"p01-b000": ["garbled"]})["p01-b000"] == [Flag.GARBLED]
    with pytest.raises(GuardViolation):
        validate_flags(blocks, {"p01-b000": ["made_up"]})
    with pytest.raises(GuardViolation):
        validate_flags(blocks, {"nope": ["garbled"]})


def test_text_tamper_detected():
    blocks = mk(2)
    blocks[1].text = "silently rewritten by LLM"
    with pytest.raises(GuardViolation):
        assert_text_intact(blocks)


def test_english_detection():
    assert is_english("Lines and angles, Class IX $\\angle ABC = 90^\\circ$")
    assert not is_english("रेखाएँ और कोण")
    assert not is_english("கோடுகளும் கோணங்களும்")


def test_english_edit_rules():
    src = "The angle is 30 degrees and $x+y=180$."
    assert validate_english_edit(src, "The angle measures 30 degrees, and $x+y=180$.")
    with pytest.raises(GuardViolation):
        validate_english_edit(src, "The angle is 40 degrees and $x+y=180$.")      # number
    with pytest.raises(GuardViolation):
        validate_english_edit(src, "The angle is 30 degrees and $x+y=90$.")       # latex
    with pytest.raises(GuardViolation):
        validate_english_edit("कोण 30 है", "कोण 30 है।")                          # non-English source
    with pytest.raises(GuardViolation):
        validate_english_edit(src, "कोण 30 degrees and $x+y=180$.")               # non-English output
