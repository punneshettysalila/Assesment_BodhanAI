"""CLI: python -m bodhan_lesson --input chapter.pdf --langs hi,ta --out ./out
Exit codes: 0 all languages produced output (partial issues are listed in report.json),
1 at least one language failed, 2 fatal (no usable input / config)."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

import yaml
from pathlib import Path

from .config import ConfigError, Settings
from .logging_setup import setup as setup_logging
from .report.collector import Report


def load_env_file(path: Path) -> None:
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="bodhan_lesson", description="Scanned chapter -> translated, narrated lesson")
    ap.add_argument("--input", required=True, type=Path, help="PDF or folder of page images")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--langs", required=True, help="comma-separated target languages, e.g. hi,ta,bn")
    ap.add_argument("--source-lang", default=None, help="source language code (default: auto-detect by script)")
    ap.add_argument("--voices", type=Path, default=None, help="YAML file mapping language codes to Bodhan voice names")
    ap.add_argument("--glossary", type=Path, default=None, help="glossary.yaml with human overrides")
    ap.add_argument("--code-mixed", action="store_true", help="keep English technical terms in narration")
    ap.add_argument("--max-chars", type=int, default=220, help="max characters per TTS chunk")
    ap.add_argument("--no-audio", action="store_true", help="stop after translated Markdown")
    ap.add_argument("--no-verify", action="store_true", help="skip Indic-Transcribe verification")
    ap.add_argument("--case-memory", action="store_true", help="reuse verified layout decisions as few-shot hints")
    ap.add_argument("--max-cost-inr", type=float, default=None, help="stop synthesising audio after this cost budget")
    ap.add_argument("--env-file", type=Path, default=Path(".env"))
    ap.add_argument("--verbose", "-v", action="store_true")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    a = parse_args(argv)
    load_env_file(a.env_file)
    a.out.mkdir(parents=True, exist_ok=True)
    setup_logging(a.out, a.verbose)
    need = ("ocr", "translate") + (() if a.no_audio else ("speak",) + (() if a.no_verify else ("transcribe",)))
    root = Path(__file__).resolve().parents[2]
    try:
        settings = Settings.from_env(root / "configs" / "thresholds.yaml", require=need)
    except ConfigError as e:
        print(f"config error: {e}", file=sys.stderr)
        return 2
    from .clients.bodhan import Bodhan
    from .clients.llm import LLM
    from .pipeline import RunOptions, run_pipeline
    llm = None
    if settings.llm_base_url and settings.llm_model:
        llm = LLM(settings)
    else:
        print("note: LLM_BASE_URL/LLM_MODEL not set -> heuristic layout, deterministic table/figure narration",
              file=sys.stderr)
    voices = {}
    if a.voices:
        try:
            voices = yaml.safe_load(a.voices.read_text(encoding="utf-8")) or {}
            if not isinstance(voices, dict) or any(not isinstance(k, str) or not isinstance(v, str) or not v.strip()
                                                   for k, v in voices.items()):
                raise ValueError("voices file must map language codes to non-empty voice names")
        except (OSError, yaml.YAMLError, ValueError) as e:
            print(f"voices configuration error: {e}", file=sys.stderr)
            return 2
    opts = RunOptions(input=a.input, out=a.out, langs=[l.strip() for l in a.langs.split(",") if l.strip()],
                      source_lang=a.source_lang, voices=voices, glossary_path=a.glossary, code_mixed=a.code_mixed,
                      max_chars=a.max_chars, no_audio=a.no_audio, verify_audio=not a.no_verify,
                      use_case_memory=a.case_memory, max_cost_inr=a.max_cost_inr)
    report = Report()

    async def go() -> int:
        bodhan = Bodhan(settings)
        try:
            return await run_pipeline(opts, bodhan, llm, settings.thresholds, report)
        finally:
            report.data["usage"] = report.data.get("usage") or bodhan.stats
            await bodhan.aclose()

    try:
        code = asyncio.run(go())
    except Exception as e:                         # last-resort guard: always leave a report behind
        report.warn("fatal", error=f"{type(e).__name__}: {e}")
        code = 2
    report.write(a.out / "report.json")
    print(f"report: {a.out / 'report.json'}  (exit {code})")
    return code
