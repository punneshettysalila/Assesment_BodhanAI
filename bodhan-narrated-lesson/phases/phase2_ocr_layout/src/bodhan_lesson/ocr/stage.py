"""OCR stage: prepare image -> Indic-OCR -> parse -> flag -> (one 2x retry if doubtful)."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from ..cache import DiskCache
from ..ingest import quality
from ..models import Page
from .doubt import apply_flags
from .parse import parse_ocr_response

log = logging.getLogger("bodhan_lesson.ocr")


async def _ocr_once(ocr_fn, image: str, cache: DiskCache, page_no: int, cfg: dict):
    key = DiskCache.key(Path(image).read_bytes(), "ocr-v1")
    raw = cache.get("ocr", key)
    if raw is None:
        raw = await ocr_fn(image)
        cache.set("ocr", key, raw)
    blocks = parse_ocr_response(page_no, raw)
    doubtful = apply_flags(blocks, cfg)
    return raw, blocks, doubtful


async def ocr_page(page: Page, ocr_fn, cache: DiskCache, cfg: dict, work_dir: Path) -> Page:
    c = cfg.get("ocr", {})
    img, page.quality = quality.prepare(page.image_path, work_dir)
    raw, blocks, doubtful = await _ocr_once(ocr_fn, img, cache, page.number, cfg)
    page.ocr_attempts = 1
    frac = doubtful / max(len(blocks), 1)
    if doubtful and frac >= c.get("retry_fraction", 0.2) and c.get("max_recrops", 1) > 0:
        big = quality.upscale(img, c.get("recrop_scale", 2.0), str(Path(work_dir) / f"page-{page.number:03d}.x2.png"))
        raw2, blocks2, doubtful2 = await _ocr_once(ocr_fn, big, cache, page.number, cfg)
        page.ocr_attempts = 2
        if doubtful2 < doubtful:          # keep whichever attempt is cleaner
            raw, blocks, doubtful = raw2, blocks2, doubtful2
            page.quality["retry_used"] = True
    page.blocks = blocks
    page.quality["doubtful_blocks"] = doubtful
    log.info("page_ocr", extra={"page": page.number, "blocks": len(blocks), "doubtful": doubtful,
                                "attempts": page.ocr_attempts})
    page.quality["_raw"] = raw
    return page


async def ocr_pages(pages: list[Page], ocr_fn, cache: DiskCache, cfg: dict, out_dir: Path) -> list[Page]:
    work = Path(out_dir) / "work"
    work.mkdir(parents=True, exist_ok=True)
    results = await asyncio.gather(*(ocr_page(p, ocr_fn, cache, cfg, work) for p in pages), return_exceptions=True)
    done = []
    for p, r in zip(pages, results):
        if isinstance(r, Exception):
            log.error("page_failed", extra={"page": p.number, "err": str(r)})
            p.quality["error"] = str(r)
        done.append(p)
    return done


def write_page_json(page: Page, pages_dir: Path) -> None:
    pages_dir.mkdir(parents=True, exist_ok=True)
    raw = page.quality.pop("_raw", "")
    (pages_dir / f"page-{page.number:03d}.json").write_text(json.dumps({
        "page": page.number, "ocr_attempts": page.ocr_attempts, "quality": page.quality,
        "raw_ocr": raw, "blocks": [b.model_dump(mode="json") for b in page.blocks]}, ensure_ascii=False, indent=2),
        encoding="utf-8")
