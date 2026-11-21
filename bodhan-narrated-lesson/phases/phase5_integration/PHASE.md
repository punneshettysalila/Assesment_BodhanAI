# Phase 5 - Orchestration, CLI, memory, packaging

## Goal
Wire everything: the asyncio pipeline with per-language isolation and a content-hash cache, the CLI and exit codes, structured logs, the optional verified-case memory, Docker/Make, and the offline demo tool.

## Files introduced in this phase

- `src/bodhan_lesson/pipeline.py`
- `src/bodhan_lesson/cli.py`
- `src/bodhan_lesson/__main__.py`
- `src/bodhan_lesson/logging_setup.py`
- `src/bodhan_lesson/memory/__init__.py`
- `src/bodhan_lesson/memory/cases.py`
- `tests/e2e/__init__.py`
- `tests/e2e/test_smoke.py`
- `Makefile`
- `Dockerfile`
- `configs/glossary.example.yaml`
- `configs/voices.example.yaml`
- `tools/offline_demo.py`

## How to verify

Copy phases 1..N over each other (or run `python scripts/verify_phases.py`), then:

```bash
pip install -r requirements-dev.txt
PYTHONPATH=src pytest -q && python tools/offline_demo.py --out out/offline_demo
```

Cumulative tests at the end of this phase: **51 passing**.

## Outcome
Key result: one language failing never stops the others; reruns repeat no paid calls; exit codes 0/1/2.
