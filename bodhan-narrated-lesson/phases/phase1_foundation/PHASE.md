# Phase 1 - Foundation, contracts and guardrails

## Goal
Everything every later phase stands on: data models, config, API client with retry/cost accounting, the LLM wrapper, and the validators that make the assignment's LLM rules enforceable in code.

## Files introduced in this phase

- `pyproject.toml`
- `requirements.txt`
- `requirements-dev.txt`
- `requirements-tested.txt`
- `.env.example`
- `.gitignore`
- `src/bodhan_lesson/__init__.py`
- `src/bodhan_lesson/models.py`
- `src/bodhan_lesson/config.py`
- `src/bodhan_lesson/languages.py`
- `src/bodhan_lesson/cache.py`
- `src/bodhan_lesson/clients/__init__.py`
- `src/bodhan_lesson/clients/base.py`
- `src/bodhan_lesson/clients/llm.py`
- `src/bodhan_lesson/layout/__init__.py`
- `src/bodhan_lesson/layout/validators.py`
- `configs/thresholds.yaml`
- `configs/endpoints.yaml`
- `tests/unit/test_validators.py`
- `tests/unit/test_client_base.py`
- `tests/guards/test_no_foreign_models.py`

## How to verify

Copy phases 1..N over each other (or run `python scripts/verify_phases.py`), then:

```bash
pip install -r requirements-dev.txt
PYTHONPATH=src pytest -q
```

Cumulative tests at the end of this phase: **13 passing**.

## Outcome
Key result: an LLM response that is not a pure permutation of block ids, or that changes OCR text, is rejected by code, not by prompt wording. A guard test fails the build if any non-Bodhan model library appears.
