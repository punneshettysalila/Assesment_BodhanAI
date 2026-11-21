# Phase 6 - Documentation and delivery

## Goal
The README report (architecture, algorithms, evidence checklist), design notes, workflow diagrams, PR text, and a sample offline-demo output.

## Files introduced in this phase

- `README.md`
- `docs/architecture.md`
- `docs/workflow.md`
- `docs/design-notes.md`
- `docs/pr_description.md`
- `scripts/build_phases.py`
- `scripts/verify_phases.py`
- `scripts/ablate_case_memory.py`
- `scripts/collect_evidence.py`
- `scripts/probe_bodhan.py`
- `docs/application_report.md`
- `docs/video_script.md`

## How to verify

Copy phases 1..N over each other (or run `python scripts/verify_phases.py`), then:

```bash
pip install -r requirements-dev.txt
PYTHONPATH=src python scripts/verify_phases.py
```

Cumulative tests at the end of this phase: **51 passing**.

## Outcome
Key result: a reviewer can understand, run and audit the whole system from the README alone.
