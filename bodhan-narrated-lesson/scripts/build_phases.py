#!/usr/bin/env python
"""Generate phases/phaseN_*/ from the repo (single source of truth = the repo itself).
Each phase folder holds ONLY the files introduced in that phase, same relative paths,
plus a PHASE.md. Copy phases 1..N over each other to get a runnable snapshot
(scripts/verify_phases.py does exactly that and runs the tests)."""
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
P = "src/bodhan_lesson"

PHASES = [
    ("phase1_foundation", "Phase 1 - Foundation, contracts and guardrails",
     "Everything every later phase stands on: data models, config, API client with retry/cost accounting, "
     "the LLM wrapper, and the validators that make the assignment's LLM rules enforceable in code.",
     ["pyproject.toml", "requirements.txt", "requirements-dev.txt", "requirements-tested.txt", ".env.example", ".gitignore",
      f"{P}/__init__.py", f"{P}/models.py", f"{P}/config.py", f"{P}/languages.py", f"{P}/cache.py",
      f"{P}/clients/__init__.py", f"{P}/clients/base.py", f"{P}/clients/llm.py",
      f"{P}/layout/__init__.py", f"{P}/layout/validators.py",
      "configs/thresholds.yaml", "configs/endpoints.yaml",
      "tests/unit/test_validators.py", "tests/unit/test_client_base.py", "tests/guards/test_no_foreign_models.py"],
     "pytest -q", "Key result: an LLM response that is not a pure permutation of block ids, or that changes OCR text, "
     "is rejected by code, not by prompt wording. A guard test fails the build if any non-Bodhan model library appears."),
    ("phase2_ocr_layout", "Phase 2 - Ingest, OCR, layout and assembly",
     "Scan to a clean, ordered, de-chromed source lesson: render and deskew, Indic-OCR, parse into typed blocks, "
     "score doubt, re-OCR when needed, remove running headers/footers generically, repair reading order, join "
     "paragraphs/tables across pages, group into sections.",
     [f"{P}/clients/bodhan.py", f"{P}/ingest/__init__.py", f"{P}/ingest/render.py", f"{P}/ingest/quality.py",
      f"{P}/ocr/__init__.py", f"{P}/ocr/parse.py", f"{P}/ocr/doubt.py", f"{P}/ocr/stage.py",
      f"{P}/assemble/__init__.py", f"{P}/assemble/headers_footers.py", f"{P}/assemble/joiner.py",
      f"{P}/assemble/sections.py", f"{P}/layout/xycut.py", f"{P}/layout/llm_order.py",
      "tests/unit/test_phase2.py", "tests/unit/test_bodhan_api_contract.py"],
     "pytest -q", "Key result: XY-cut orders two-column pages, the LLM only adjudicates disagreements and is "
     "validator-fenced, and footers like a website banner disappear by a repetition rule, not a URL rule."),
    ("phase3_translation", "Phase 3 - Translation, glossary and English pivot",
     "Structure-safe translation: LaTeX and glossary terms are masked, numbers and scripts are verified, "
     "doubtful blocks are withheld, tables are translated cell by cell, and an English pivot (built once) "
     "serves Indian-language sources with a round-trip quality check.",
     [f"{P}/translate/__init__.py", f"{P}/translate/mask.py", f"{P}/translate/check.py",
      f"{P}/translate/engine.py", f"{P}/translate/pivot.py",
      f"{P}/glossary/__init__.py", f"{P}/glossary/terms.py", "tests/unit/test_phase3.py"],
     "pytest -q", "Key result: changed numbers, LaTeX or lost placeholders are detected, retried once, and "
     "reported, never hidden."),
    ("phase4_narration_speech", "Phase 4 - Narration, verified speech, audio and report",
     "What a listener hears and proof that it is right: narration rules per block type, deterministic "
     "LaTeX-to-speech, short TTS chunks, Indic-Transcribe verification with CER and repeat/omission "
     "detection, a retry ladder, loudness normalisation, chapter markers, report.json and report.html.",
     [f"{P}/narrate/__init__.py", f"{P}/narrate/latex_speech.py", f"{P}/narrate/chunker.py", f"{P}/narrate/planner.py",
      f"{P}/speak/__init__.py", f"{P}/speak/verified.py", f"{P}/audio/__init__.py", f"{P}/audio/mix.py",
      f"{P}/report/__init__.py", f"{P}/report/collector.py", f"{P}/report/html.py", "tests/unit/test_phase4.py"],
     "pytest -q", "Key result: every audio chunk is transcribed back and scored; omissions and repeats trigger "
     "targeted retries; the best attempt ships with an honest flag if all attempts fail."),
    ("phase5_integration", "Phase 5 - Orchestration, CLI, memory, packaging",
     "Wire everything: the asyncio pipeline with per-language isolation and a content-hash cache, the CLI and "
     "exit codes, structured logs, the optional verified-case memory, Docker/Make, and the offline demo tool.",
     [f"{P}/pipeline.py", f"{P}/cli.py", f"{P}/__main__.py", f"{P}/logging_setup.py", f"{P}/memory/__init__.py",
      f"{P}/memory/cases.py", "tests/e2e/__init__.py", "tests/e2e/test_smoke.py", "Makefile", "Dockerfile",
      "configs/glossary.example.yaml", "configs/voices.example.yaml", "tools/offline_demo.py"],
     "pytest -q && python tools/offline_demo.py --out out/offline_demo",
     "Key result: one language failing never stops the others; reruns repeat no paid calls; exit codes 0/1/2."),
    ("phase6_docs_delivery", "Phase 6 - Documentation and delivery",
     "The README report (architecture, algorithms, evidence checklist), design notes, workflow diagrams, PR text, "
     "and a sample offline-demo output.",
     ["README.md", "docs/architecture.md", "docs/workflow.md", "docs/design-notes.md", "docs/pr_description.md",
      "scripts/build_phases.py", "scripts/verify_phases.py", "scripts/ablate_case_memory.py",
      "scripts/collect_evidence.py", "scripts/probe_bodhan.py", "docs/application_report.md", "docs/video_script.md"],
     "python scripts/verify_phases.py", "Key result: a reviewer can understand, run and audit the whole system "
     "from the README alone."),
]

TEST_COUNTS = {}   # filled by verify_phases (documented in PHASE.md as 'cumulative tests')


def all_assigned() -> set[str]:
    return {f for _, _, _, files, _, _ in PHASES for f in files}


def build(counts: dict[str, int] | None = None) -> None:
    out = ROOT / "phases"
    if out.exists():
        shutil.rmtree(out)
    for name, title, goal, files, verify, result in PHASES:
        d = out / name
        for rel in files:
            src = ROOT / rel
            if not src.exists():
                raise SystemExit(f"missing file for {name}: {rel}")
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, d / rel)
        n = (counts or {}).get(name)
        lines = [f"# {title}", "", "## Goal", goal, "", "## Files introduced in this phase", ""]
        lines += [f"- `{f}`" for f in files]
        lines += ["", "## How to verify", "", "Copy phases 1..N over each other (or run `python scripts/verify_phases.py`), then:",
                  "", "```bash", "pip install -r requirements-dev.txt", "PYTHONPATH=src " + verify, "```", ""]
        if n:
            lines += [f"Cumulative tests at the end of this phase: **{n} passing**.", ""]
        lines += ["## Outcome", result, ""]
        (d / "PHASE.md").write_text("\n".join(lines), encoding="utf-8")
    # completeness check: every repo file belongs to a phase (or is generated/ignored)
    ignored = ("phases/", "out/", ".git/", "examples/", "__pycache__", ".pytest_cache", "walkthrough", ".egg-info/")
    assigned = all_assigned()
    stray = []
    for f in ROOT.rglob("*"):
        rel = f.relative_to(ROOT).as_posix()
        if f.is_file() and not any(i in rel for i in ignored) and rel not in assigned and not rel.endswith(".pyc"):
            stray.append(rel)
    if stray:
        print("WARNING files not assigned to any phase:", *stray, sep="\n  ")
    print(f"built {len(PHASES)} phase folders in {out}")


if __name__ == "__main__":
    build()
