# Phase 4 - Narration, verified speech, audio and report

## Goal
What a listener hears and proof that it is right: narration rules per block type, deterministic LaTeX-to-speech, short TTS chunks, Indic-Transcribe verification with CER and repeat/omission detection, a retry ladder, loudness normalisation, chapter markers, report.json and report.html.

## Files introduced in this phase

- `src/bodhan_lesson/narrate/__init__.py`
- `src/bodhan_lesson/narrate/latex_speech.py`
- `src/bodhan_lesson/narrate/chunker.py`
- `src/bodhan_lesson/narrate/planner.py`
- `src/bodhan_lesson/speak/__init__.py`
- `src/bodhan_lesson/speak/verified.py`
- `src/bodhan_lesson/audio/__init__.py`
- `src/bodhan_lesson/audio/mix.py`
- `src/bodhan_lesson/report/__init__.py`
- `src/bodhan_lesson/report/collector.py`
- `src/bodhan_lesson/report/html.py`
- `tests/unit/test_phase4.py`

## How to verify

Copy phases 1..N over each other (or run `python scripts/verify_phases.py`), then:

```bash
pip install -r requirements-dev.txt
PYTHONPATH=src pytest -q
```

Cumulative tests at the end of this phase: **45 passing**.

## Outcome
Key result: every audio chunk is transcribed back and scored; omissions and repeats trigger targeted retries; the best attempt ships with an honest flag if all attempts fail.
