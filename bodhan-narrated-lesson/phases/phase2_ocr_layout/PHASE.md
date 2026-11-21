# Phase 2 - Ingest, OCR, layout and assembly

## Goal
Scan to a clean, ordered, de-chromed source lesson: render and deskew, Indic-OCR, parse into typed blocks, score doubt, re-OCR when needed, remove running headers/footers generically, repair reading order, join paragraphs/tables across pages, group into sections.

## Files introduced in this phase

- `src/bodhan_lesson/clients/bodhan.py`
- `src/bodhan_lesson/ingest/__init__.py`
- `src/bodhan_lesson/ingest/render.py`
- `src/bodhan_lesson/ingest/quality.py`
- `src/bodhan_lesson/ocr/__init__.py`
- `src/bodhan_lesson/ocr/parse.py`
- `src/bodhan_lesson/ocr/doubt.py`
- `src/bodhan_lesson/ocr/stage.py`
- `src/bodhan_lesson/assemble/__init__.py`
- `src/bodhan_lesson/assemble/headers_footers.py`
- `src/bodhan_lesson/assemble/joiner.py`
- `src/bodhan_lesson/assemble/sections.py`
- `src/bodhan_lesson/layout/xycut.py`
- `src/bodhan_lesson/layout/llm_order.py`
- `tests/unit/test_phase2.py`
- `tests/unit/test_bodhan_api_contract.py`

## How to verify

Copy phases 1..N over each other (or run `python scripts/verify_phases.py`), then:

```bash
pip install -r requirements-dev.txt
PYTHONPATH=src pytest -q
```

Cumulative tests at the end of this phase: **24 passing**.

## Outcome
Key result: XY-cut orders two-column pages, the LLM only adjudicates disagreements and is validator-fenced, and footers like a website banner disappear by a repetition rule, not a URL rule.
