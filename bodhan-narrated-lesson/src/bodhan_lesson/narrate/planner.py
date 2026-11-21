"""Narration planner: decides what a listener hears for every block type.
 - prose/headings/captions: the translated text (inline math spoken as English words)
 - equations/tables/figures: English narration -> Indic-Translate -> target language
 - flagged OCR blocks: skipped with a logged reason (never narrated)"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from ..clients.llm import LLM, describe_image
from ..models import Block, BlockType
from ..translate.check import numbers
from .chunker import clean_for_speech
from .latex_speech import inline_math_to_speech, latex_to_speech

TranslateFn = Callable[[str, str, str], Awaitable[str]]


@dataclass
class Item:
    kind: str
    block_ids: list[str]
    text: str
    notes: list[str] = field(default_factory=list)


@dataclass
class PlanContext:
    lang: str
    translate_fn: TranslateFn
    llm: LLM | None = None
    page_images: dict[int, str] = field(default_factory=dict)


def table_to_english_deterministic(md: str) -> str:
    rows = [r for r in md.splitlines() if r.strip() and not re.fullmatch(r"\|?[\s:|-]+\|?", r)]
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    if not cells:
        return ""
    head, body = cells[0], cells[1:]
    out = [f"Table with {len(body)} rows and {len(head)} columns. Columns: {', '.join(head)}."]
    for i, row in enumerate(body, 1):
        pairs = [f"{h} is {v}" for h, v in zip(head, row) if v]
        out.append(f"Row {i}: {'; '.join(pairs)}.")
    return " ".join(out)


TABLE_SYS = ("You turn a table into spoken English for a listener who cannot see it. Say what the table is about, "
             "then each row naturally. Use EVERY number and header exactly as given; add nothing. Plain prose, no markdown.")


async def table_to_english(llm: LLM | None, md: str) -> tuple[str, list[str]]:
    det = table_to_english_deterministic(md)
    if llm is None:
        return det, ["deterministic"]
    try:
        spoken = (await llm.complete(TABLE_SYS, md)).strip()
        need = numbers(md)
        if numbers(spoken) == need and spoken:      # every number present, none invented
            return spoken, ["llm_verified"]
    except Exception:
        pass
    return det, ["deterministic_fallback"]


FIG_SYS = ("Describe the figure for a listener who cannot see it, in 1-3 plain sentences. Describe shapes, labels, "
           "and relationships only. Do NOT transcribe paragraphs of page text. Do not invent numbers.")


async def figure_to_english(llm: LLM | None, image_path: str | None, context: str,
                            bbox: tuple[float, float, float, float] | None = None) -> tuple[str, list[str]]:
    generic = "A figure is shown here."
    if llm is None or not image_path or bbox is None:
        return generic, ["no_vision_or_figure_box"]
    try:
        # Only the OCR-detected figure region is sent to the multimodal LLM,
        # never the full page containing unrelated textbook prose.
        from PIL import Image
        from tempfile import TemporaryDirectory
        from pathlib import Path
        with TemporaryDirectory() as temp_dir:
            with Image.open(image_path) as page:
                x0, y0, x1, y1 = bbox
                crop = page.crop((int(x0 * page.width), int(y0 * page.height),
                                  int(x1 * page.width), int(y1 * page.height)))
                if crop.width < 2 or crop.height < 2:
                    return generic, ["invalid_figure_box"]
                crop_path = Path(temp_dir) / "figure.png"
                crop.save(crop_path)
            desc = (await describe_image(llm, FIG_SYS,
                                         f"Describe only the figure. OCR context: {context[:400]}",
                                         str(crop_path))).strip()
    except Exception:
        return generic, ["vision_failed"]
    extra = set(numbers(desc)) - set(numbers(context))
    if extra or not desc:                      # numbers not backed by OCR text -> reject
        return generic, ["description_rejected"]
    return desc, ["llm_described"]


async def _en_to_lang(ctx: PlanContext, en: str) -> str:
    return en if ctx.lang == "en" else await ctx.translate_fn(en, "en", ctx.lang)


async def plan_section(pairs: list[tuple[Block, str | None]], ctx: PlanContext) -> tuple[list[Item], list[dict]]:
    """pairs = [(english_or_source_block, translated_text_or_None)] in reading order.
    Returns (items, skipped)."""
    items: list[Item] = []
    skipped: list[dict] = []
    for i, (b, tgt) in enumerate(pairs):
        if tgt is None:
            skipped.append({"block": b.id, "reason": "ocr_doubtful_or_untranslatable"})
            continue
        if b.type == BlockType.EQUATION:
            spoken, unknown = latex_to_speech(b.text)
            text = await _en_to_lang(ctx, f"Equation: {spoken}.")
            items.append(Item("equation", [b.id], text, [f"unknown_cmds:{unknown}"] if unknown else []))
        elif b.type == BlockType.TABLE:
            en, notes = await table_to_english(ctx.llm, b.text)
            items.append(Item("table", [b.id], await _en_to_lang(ctx, en), notes))
        elif b.type == BlockType.FIGURE:
            nxt = pairs[i + 1][0].text if i + 1 < len(pairs) else ""
            en, notes = await figure_to_english(ctx.llm, ctx.page_images.get(b.page), nxt, b.bbox)
            items.append(Item("figure", [b.id], await _en_to_lang(ctx, en), notes + ["ai_described"]))
        elif b.type == BlockType.LIST:
            body = [re.sub(r"^\s*(?:[-*•]|\(?\d+[.)]|\(?[a-z][.)])\s+", "", l) for l in tgt.splitlines() if l.strip()]
            spoken, _ = inline_math_to_speech(" ".join(x.rstrip(".") + "." for x in body))
            items.append(Item("list", [b.id], clean_for_speech(spoken)))
        else:
            spoken, unknown = inline_math_to_speech(tgt)
            kind = "heading" if b.type == BlockType.HEADING else "caption" if b.type == BlockType.CAPTION else "prose"
            items.append(Item(kind, [b.id], clean_for_speech(spoken), [f"unknown_cmds:{unknown}"] if unknown else []))
    return items, skipped
