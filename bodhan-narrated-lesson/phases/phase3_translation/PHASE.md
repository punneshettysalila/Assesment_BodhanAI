# Phase 3 - Translation, glossary and English pivot

## Goal
Structure-safe translation: LaTeX and glossary terms are masked, numbers and scripts are verified, doubtful blocks are withheld, tables are translated cell by cell, and an English pivot (built once) serves Indian-language sources with a round-trip quality check.

## Files introduced in this phase

- `src/bodhan_lesson/translate/__init__.py`
- `src/bodhan_lesson/translate/mask.py`
- `src/bodhan_lesson/translate/check.py`
- `src/bodhan_lesson/translate/engine.py`
- `src/bodhan_lesson/translate/pivot.py`
- `src/bodhan_lesson/glossary/__init__.py`
- `src/bodhan_lesson/glossary/terms.py`
- `tests/unit/test_phase3.py`

## How to verify

Copy phases 1..N over each other (or run `python scripts/verify_phases.py`), then:

```bash
pip install -r requirements-dev.txt
PYTHONPATH=src pytest -q
```

Cumulative tests at the end of this phase: **35 passing**.

## Outcome
Key result: changed numbers, LaTeX or lost placeholders are detected, retried once, and reported, never hidden.
