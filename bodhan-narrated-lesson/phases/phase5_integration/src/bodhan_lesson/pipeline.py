"""End-to-end orchestration. A plain asyncio state machine: fixed stages, LLM only at explicit
decision points (reading order, glossary terms, table/figure narration), disk-cached and
resumable. One language failing never stops the others."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .assemble.headers_footers import CHROME, content_blocks, strip_running
from .assemble.joiner import join_across_pages
from .assemble.sections import Section, build_sections, render_markdown, structure_signature
from .audio import mix
from .cache import DiskCache
from .glossary.terms import build_glossary, coverage, extract_terms, load_user_glossary
from .ingest.render import render_input
from .languages import detect_script_lang
from .layout.llm_order import repair_order
from .memory.cases import CaseMemory
from .models import Block, BlockType, Flag
from .narrate.chunker import split_chunks
from .narrate.planner import PlanContext, plan_section
from .ocr.stage import ocr_pages, write_page_json
from .report.collector import Report
from .speak.verified import synth_verified
from .translate.engine import BLOCKING, Translator
from .translate.pivot import build_pivot

log = logging.getLogger("bodhan_lesson.pipeline")


@dataclass
class RunOptions:
    input: Path
    out: Path
    langs: list[str]
    source_lang: str | None = None
    voices: dict[str, str] = field(default_factory=dict)
    glossary_path: Path | None = None
    code_mixed: bool = False
    max_chars: int = 220
    no_audio: bool = False
    verify_audio: bool = True
    use_case_memory: bool = False
    dpi: int = 150
    max_cost_inr: float | None = None


def _clone(b: Block, text: str | None = None) -> Block:
    return Block(id=b.id, page=b.page, type=b.type, text=text if text is not None else b.text,
                 flags=list(b.flags), meta=dict(b.meta), order=b.order, bbox=b.bbox)


def _sections_with(sections: list[Section], texts: dict[str, str | None]) -> list[Section]:
    out = []
    for s in sections:
        blocks = [_clone(b, texts[b.id]) for b in s.blocks if texts.get(b.id) is not None]
        out.append(s.model_copy(update={"blocks": blocks}))
    return out


def cached_translate(fn, cache: DiskCache):
    """Same cache namespace/key as Translator, so narration + glossary calls are never paid twice."""
    async def f(text: str, src: str, tgt: str) -> str:
        script = getattr(getattr(fn, "__self__", None), "translation_script", "native")
        namespace = f"tr-v1-{script}"
        key = DiskCache.key(text, src, tgt, namespace)
        hit = cache.get("translate", key)
        if hit is None:
            hit = await fn(text, src, tgt)
            cache.set("translate", key, hit)
        return hit
    f.cache_namespace = f"tr-v1-{getattr(getattr(fn, '__self__', None), 'translation_script', 'native')}"
    return f


async def run_pipeline(opts: RunOptions, bodhan, llm, cfg: dict, report: Report) -> int:
    out = Path(opts.out)
    (out / "source" / "pages").mkdir(parents=True, exist_ok=True)
    cache = DiskCache(out / ".cache")
    if hasattr(bodhan, "translation_script"):
        bodhan.translation_script = "codemix" if opts.code_mixed else "native"
    translate = cached_translate(bodhan.translate, cache)
    memory = CaseMemory(out / ".cache" / "cases.jsonl") if opts.use_case_memory else None
    report.data["input"] = {"path": str(opts.input), "langs": opts.langs}

    # ---- 1. ingest + OCR ---------------------------------------------------------------
    with report.stage("ingest"):
        pages = render_input(opts.input, out / "work", opts.dpi)
    with report.stage("ocr"):
        pages = await ocr_pages(pages, bodhan.ocr, cache, cfg, out)
    report.data["pages"] = {str(p.number): {
        "image": Path(p.image_path).name, "ocr_attempts": p.ocr_attempts,
        "block_count": len(p.blocks), "doubtful_blocks": p.quality.get("doubtful_blocks", 0),
        "quality": {k: v for k, v in p.quality.items() if not k.startswith("_")},
        "flags": {f.value: sum(f in b.flags for b in p.blocks) for f in Flag},
    } for p in pages}
    failed = [p.number for p in pages if p.quality.get("error") or not p.blocks]
    if len(failed) == len(pages):
        report.warn("all pages failed OCR")
        return 2
    for n in failed:
        report.warn("page produced no text", page=n)

    # ---- 2. layout: running chrome, reading order, cross-page joins ---------------------
    with report.stage("layout"):
        removed = strip_running(pages, cfg)
        for p in pages:
            content = [b for b in p.blocks if b.type not in CHROME]
            chrome = [b for b in p.blocks if b.type in CHROME]
            examples = memory.examples(content) if memory else ""
            ordered, rec = await repair_order(content, llm, examples)
            if memory and rec["method"] in ("llm", "xycut"):
                memory.record(content, [b.id for b in ordered], rec["method"])
            for i, b in enumerate(ordered + chrome):
                b.order = i
            p.blocks = ordered + chrome
            p.quality["layout_decision"] = rec
            page_report = report.data["pages"][str(p.number)]
            page_report["layout_decision"] = rec
            page_report["flags"] = {f.value: sum(f in b.flags for b in p.blocks) for f in Flag}
            write_page_json(p, out / "source" / "pages")
        blocks = join_across_pages(content_blocks(pages))
    if not blocks:
        report.warn("no content blocks after layout")
        return 2

    text_for_lang = " ".join(b.text for b in blocks if b.type in (BlockType.PARAGRAPH, BlockType.HEADING))
    src_lang = opts.source_lang or detect_script_lang(text_for_lang)
    sections = build_sections(blocks)
    src_md = render_markdown(sections)
    (out / "source" / "lesson.src.md").write_text(src_md, encoding="utf-8")
    flagged = [{"id": b.id, "page": b.page, "flags": [f.value for f in b.flags], "text": b.text[:120]}
               for b in blocks if set(b.flags) & BLOCKING]
    (out / "source" / "flagged.json").write_text(json.dumps({"flagged_blocks": flagged, "removed_chrome": removed},
                                                            ensure_ascii=False, indent=2), encoding="utf-8")
    report.data["source"] = {"language": src_lang, "pages": len(pages), "blocks": len(blocks),
                             "sections": len(sections), "flagged_blocks": len(flagged),
                             "removed_chrome": len(removed), "failed_pages": failed}

    # ---- 3. English pivot (built once, reused by every target) ------------------------
    with report.stage("pivot"):
        if src_lang == "en":
            en_blocks = blocks
        else:
            tr_en = Translator(translate, cache, src_lang, "en")
            tr_back = Translator(translate, cache, "en", src_lang)
            pivot, weak = await build_pivot(blocks, tr_en, tr_back)
            en_blocks = [_clone(b, pivot.get(b.id)) if pivot.get(b.id) else b for b in blocks]
            report.data["source"]["pivot_weak_blocks"] = weak
            report.data["source"]["pivot_issues"] = tr_en.issues
    en_sections = build_sections(en_blocks)
    for es, s in zip(en_sections, sections):
        s.slug = es.slug          # filenames always come from the English title
    if src_lang != "en":
        (out / "source" / "lesson.en.md").write_text(render_markdown(en_sections), encoding="utf-8")
    en_text = {b.id: b.text for b in en_blocks}

    # ---- 4. glossary terms (English, LLM-extracted, validated) ---------------------------
    terms = await extract_terms(llm, "\n".join(b.text for b in en_blocks
                                               if b.type in (BlockType.PARAGRAPH, BlockType.HEADING, BlockType.LIST)))
    user_gl = load_user_glossary(opts.glossary_path)
    terms = list(dict.fromkeys(terms + list(user_gl)))

    page_images = {p.number: p.image_path for p in pages}
    speech_cfg = dict(cfg.get("speech", {}))
    speech_cfg.setdefault("max_audio_seconds", 28)

    # ---- 5. per-language: translate -> narrate -> verify -> package -------------------------
    async def process_language(lang: str) -> None:
        L = report.lang(lang)
        ldir = out / lang
        ldir.mkdir(parents=True, exist_ok=True)
        L["status"] = "running"
        if lang == src_lang:
            issues_by_block = {}
            texts = {b.id: (None if set(b.flags) & BLOCKING else b.text) for b in blocks}
            L["skipped_blocks"] = [{"block": k, "reason": "ocr_doubtful"} for k, v in texts.items() if v is None]
            narr_blocks = blocks
        else:
            with report.stage("translate", lang):
                glossary = await build_glossary(terms, translate, lang, user_gl) if terms else {}
                if opts.code_mixed:
                    glossary = {t: t for t in terms}
                tr = Translator(translate, cache, "en", lang, locked=glossary)
                texts = await tr.blocks(en_blocks)
            L["skipped_blocks"], L["translation_issues"] = tr.skipped, tr.issues
            issues_by_block = {issue["block"]: issue["issues"] for issue in tr.issues}
            L["glossary"] = {**coverage(en_text, texts, glossary), "terms": len(glossary),
                             "lock_fallbacks": tr.lock_fallbacks, "code_mixed": opts.code_mixed}
            narr_blocks = en_blocks
        tgt_sections = _sections_with(sections, texts)
        md = render_markdown(tgt_sections)
        (ldir / f"lesson.{lang}.md").write_text(md, encoding="utf-8")
        expected = structure_signature(render_markdown(_sections_with(sections, {k: (v if v is None else en_text[k])
                                                                               for k, v in texts.items()})))
        L["structure_ok"] = structure_signature(md) == expected
        if not L["structure_ok"]:
            report.warn("structure mismatch", lang=lang)
        if opts.no_audio:
            L["status"] = "ok" if not L["skipped_blocks"] else "partial"
            return

        # narration + verified TTS
        with report.stage("narrate", lang):
            ctx = PlanContext(lang, translate, llm, page_images)
            voice = opts.voices.get(lang)
            tfn = bodhan.transcribe if opts.verify_audio else None
            by_id = {b.id: b for b in narr_blocks}
            (ldir / "narration").mkdir(exist_ok=True)
            raw_sections: list[tuple[str, bytes]] = []
            script_sections = []
            budget_reached = False
            for sec in sections:
                cost_now = sum(float(v.get("cost_inr", 0.0)) for v in bodhan.stats.values())
                if opts.max_cost_inr is not None and cost_now >= opts.max_cost_inr:
                    budget_reached = True
                    report.warn("audio stopped: INR cost budget reached", lang=lang,
                                cost_inr=round(cost_now, 3), max_cost_inr=opts.max_cost_inr)
                    break
                pairs = [(by_id[b.id], texts.get(b.id)) for b in sec.blocks]
                items, skipped = await plan_section(pairs, ctx)
                flat = [(it, c) for it in items for c in split_chunks(it.text, opts.max_chars)]
                results = await asyncio.gather(*[synth_verified(c, lang, voice, bodhan.speak, tfn, speech_cfg)
                                                 for _, c in flat])
                good = [r for r in results if r.wav]
                cers = [r.cer for r in results if r.cer is not None]
                rec = {"index": sec.index, "title": sec.title, "slug": sec.slug, "chunks": len(results),
                       "failed_chunks": len(results) - len(good),
                       "degraded_chunks": sum(r.status == "degraded" for r in results),
                       "retried_chunks": sum(r.attempts > 1 for r in results),
                       "unverified_chunks": sum(r.status == "unverified" for r in results),
                       "mean_cer": round(sum(cers) / len(cers), 4) if cers else None,
                       "translation_issues": [{"block": b.id, "issues": issues_by_block[b.id]}
                                               for b in sec.blocks if b.id in issues_by_block],
                       "skipped_blocks": skipped, "seconds": None, "lufs": None, "file": None}
                script_section = {
                    "index": sec.index, "title": sec.title, "slug": sec.slug,
                    "translation_ok": not any(b.id in issues_by_block for b in sec.blocks),
                    "items": [{"kind": it.kind, "block_ids": it.block_ids, "notes": it.notes, "text": it.text}
                              for it in items],
                    "chunks": [{"text": r.text, "cer": r.cer, "attempts": r.attempts, "status": r.status,
                                "flags": r.flags, "duration_s": r.seconds} for r in results],
                    "checks": {"mean_cer": round(sum(cers) / len(cers), 4) if cers else None,
                               "failed_chunks": len(results) - len(good),
                               "degraded_chunks": sum(r.status == "degraded" for r in results),
                               "skipped_blocks": skipped},
                }
                script_sections.append(script_section)
                log.info("section_narration", extra={"lang": lang, "section": sec.index,
                                                     "title": sec.title, "chunks": len(results),
                                                     "mean_cer": script_section["checks"]["mean_cer"]})
                if good:
                    wav = mix.concat_wavs([r.wav for r in good], 0.3)
                    rec["seconds"] = round(mix.wav_info(wav)[1], 2)
                    raw_sections.append((sec.title, wav))
                    ext = "mp3" if mix.have_ffmpeg() else "wav"
                    path = ldir / "narration" / f"{sec.index:02d}-{sec.slug}.{lang}.{ext}"
                    if ext == "mp3":
                        rawp = ldir / "work.wav"
                        rawp.write_bytes(wav)
                        rec["lufs"] = await asyncio.to_thread(
                            mix.normalise, rawp, path, cfg.get("speech", {}).get("loudness_lufs", -16.0), "128k",
                            {"title": sec.title, "comment": "AI-generated narration (Bodhan Indic-Speak)"})
                        rawp.unlink(missing_ok=True)
                    else:
                        path.write_bytes(wav)
                        report.warn("ffmpeg missing: wrote WAV, no loudness normalisation", lang=lang)
                    rec["file"] = str(path.relative_to(out))
                else:
                    report.warn("section has no audio", lang=lang, section=sec.title)
                L["sections"].append(rec)

            (ldir / f"narration_script.{lang}.json").write_text(json.dumps({
                "ai_generated": True, "language": lang, "sections": script_sections,
            }, ensure_ascii=False, indent=2), encoding="utf-8")

            # full lesson with chapter markers
            if raw_sections and mix.have_ffmpeg():
                wavs = [w for _, w in raw_sections]
                full = mix.concat_wavs(wavs, 1.0)
                durations = [(t, mix.wav_info(w)[1] + 1.0) for t, w in raw_sections]
                fp = ldir / "full.wav"
                fp.write_bytes(full)
                chapters = mix.write_chapters(durations, ldir / "chapters.ffmeta", ldir / f"chapters.{lang}.json")
                L["full_lufs"] = await asyncio.to_thread(
                    mix.normalise, fp, ldir / f"lesson.{lang}.mp3", cfg.get("speech", {}).get("loudness_lufs", -16.0),
                    "128k", {"title": f"Lesson ({lang})", "comment": "AI-generated narration (Bodhan Indic-Speak)"},
                    ldir / "chapters.ffmeta")
                fp.unlink(missing_ok=True)
                (ldir / "chapters.ffmeta").unlink(missing_ok=True)
                L["chapters"] = len(chapters)
        complete = not budget_reached and L["sections"] and all(s["file"] for s in L["sections"])
        clean = complete and not L["skipped_blocks"] and not any(s["degraded_chunks"] or s["failed_chunks"]
                                                                 for s in L["sections"])
        L["status"] = ("ok" if clean else "partial" if budget_reached or complete or any(s["file"] for s in L["sections"]) else "failed")

    results = await asyncio.gather(*[process_language(l) for l in opts.langs], return_exceptions=True)
    for lang, r in zip(opts.langs, results):
        if isinstance(r, Exception):
            L = report.lang(lang)
            L["status"], L["error"] = "failed", f"{type(r).__name__}: {r}"
            log.error("language_failed", extra={"lang": lang, "err": str(r)})
    report.data["usage"] = bodhan.stats
    report.data["cache"] = {"hits": cache.hits, "misses": cache.misses}
    report.data["usage"]["total_cost_inr"] = round(sum(v["cost_inr"] for v in bodhan.stats.values()), 3)
    statuses = [report.lang(l)["status"] for l in opts.langs]
    return 1 if "failed" in statuses else 0
