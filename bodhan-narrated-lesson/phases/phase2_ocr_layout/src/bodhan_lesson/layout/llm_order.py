"""Reading-order repair. Heuristic XY-cut first; the LLM adjudicates only when the
heuristic disagrees with Indic-OCR's order. The LLM sees ids/snippets and returns ids only;
validators guarantee a pure permutation and untouched OCR text."""
from __future__ import annotations

import logging

from ..clients.llm import LLM
from ..models import Block
from .validators import GuardViolation, assert_text_intact, validate_flags, validate_reorder
from .xycut import xy_cut_order

log = logging.getLogger("bodhan_lesson.layout")

SYSTEM = (
    "You repair the reading order of OCR blocks from ONE textbook page. Columns read top-to-bottom, "
    "left column before right; full-width titles first; sidebars/boxed notes after the passage they "
    "annotate; captions directly after their figure. You NEVER write or change text: reply with JSON "
    'only: {"order": [block ids, every id exactly once], "flags": {"<id>": ["garbled"|"low_confidence"]}}.'
    "{examples}"
)


def disagrees(blocks: list[Block], heuristic: list[Block]) -> bool:
    return [b.id for b in sorted(blocks, key=lambda b: b.order)] != [b.id for b in heuristic]


def _payload(blocks: list[Block]) -> str:
    rows = []
    for b in sorted(blocks, key=lambda b: b.order):
        bb = [round(v, 2) for v in b.bbox] if b.bbox else None
        rows.append({"id": b.id, "type": b.type.value, "bbox": bb, "snippet": b.text[:80]})
    return str(rows)


async def repair_order(blocks: list[Block], llm: LLM | None, examples: str = "",
                       max_tries: int = 2) -> tuple[list[Block], dict]:
    """Returns (ordered_blocks, decision_record)."""
    record = {"method": "ocr_order", "llm_calls": 0}
    base = sorted(blocks, key=lambda b: b.order)
    if len(base) < 2 or not all(b.bbox for b in base):
        return base, record
    heur = xy_cut_order(base)
    if not disagrees(base, heur):
        return base, record
    record["method"] = "xycut"
    if llm is None:
        return validate_reorder(base, [b.id for b in heur]), record
    prompt, err = _payload(base), ""
    for attempt in range(max_tries):
        try:
            record["llm_calls"] += 1
            data = await llm.complete_json(SYSTEM.replace("{examples}", examples), prompt + err)
            ordered = validate_reorder(base, list(data["order"]))
            for bid, fl in validate_flags(base, data.get("flags", {})).items():
                blk = next(b for b in base if b.id == bid)
                blk.flags += [f for f in fl if f not in blk.flags]
            assert_text_intact(base)
            record["method"] = "llm"
            record["order"] = [b.id for b in ordered]
            return ordered, record
        except (GuardViolation, ValueError, KeyError, TypeError) as e:
            err = f"\nYour previous answer was rejected: {e}. Return a valid permutation of the ids."
            log.warning("order_rejected", extra={"attempt": attempt, "err": str(e)})
    record["method"] = "xycut_fallback"
    return validate_reorder(base, [b.id for b in heur]), record
