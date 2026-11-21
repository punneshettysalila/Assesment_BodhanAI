"""report.json: per-stage timing, per-model usage/cost, QA metrics vs the quality targets."""
from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path

TARGETS = {
    "structure_survival": "heading/table/equation skeleton identical to source",
    "numbers_latex_issues": "0 changed numbers or LaTeX in translation",
    "section_mean_cer": "<= 0.12 mean CER per section",
    "loudness_lufs": "-16 LUFS +/- 1 per section and full lesson",
}


class Report:
    def __init__(self):
        self.data = {"input": {}, "pages": {}, "source": {}, "languages": {}, "usage": {}, "warnings": [],
                     "timings_s": {}}
        self._t0 = time.perf_counter()

    @contextmanager
    def stage(self, name: str, lang: str | None = None):
        t = time.perf_counter()
        try:
            yield
        finally:
            key = f"{lang}:{name}" if lang else name
            self.data["timings_s"][key] = round(self.data["timings_s"].get(key, 0) + time.perf_counter() - t, 3)

    def lang(self, code: str) -> dict:
        return self.data["languages"].setdefault(code, {"status": "pending", "skipped_blocks": [],
                                                       "translation_issues": [], "sections": []})

    def warn(self, msg: str, **extra) -> None:
        self.data["warnings"].append({"msg": msg, **extra})

    def evaluate(self) -> None:
        for code, L in self.data["languages"].items():
            secs = L.get("sections", [])
            cers = [s["mean_cer"] for s in secs if s.get("mean_cer") is not None]
            lufs = [s["lufs"] for s in secs if s.get("lufs") is not None]
            L["targets"] = {
                "structure_survival": L.get("structure_ok"),
                "numbers_latex_issues": len([i for i in L.get("translation_issues", [])
                                             if set(i["issues"]) & {"numbers_changed", "latex_changed"}]),
                "section_mean_cer": round(sum(cers) / len(cers), 4) if cers else None,
                "worst_section_cer": round(max(cers), 4) if cers else None,
                "loudness_lufs_range": [min(lufs), max(lufs)] if lufs else None,
                "loudness_ok": all(abs(x + 16) <= 1.0 for x in lufs) if lufs else None,
            }

    def write(self, path: Path) -> None:
        self.evaluate()
        self.data["total_runtime_s"] = round(time.perf_counter() - self._t0, 2)
        self.data["quality_targets"] = TARGETS
        Path(path).write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        from .html import write_html
        write_html(self.data, Path(path).with_suffix(".html"))
