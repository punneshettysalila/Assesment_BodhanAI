from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--lang", required=True)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()
    out = args.out
    without = out / "without-case-memory"
    with_mem = out / "with-case-memory"
    out.mkdir(parents=True, exist_ok=True)
    base = [sys.executable, "-m", "bodhan_lesson", "--input", str(args.input),
            "--langs", args.lang, "--no-audio"]
    subprocess.run(base + ["--out", str(without)], check=True)
    src_cache = without / ".cache"
    with_mem.mkdir(parents=True, exist_ok=True)
    if src_cache.exists():
        dst = with_mem / ".cache"
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src_cache, dst)
    subprocess.run(base + ["--out", str(with_mem), "--case-memory"], check=True)

    counts = Counter()
    llm_calls = 0
    pages = sorted(with_mem.glob("source/pages/page-*.json"))
    adjudication_pages = 0
    for page in pages:
        data = json.loads(page.read_text(encoding="utf-8"))
        rec = data.get("quality", {}).get("layout_decision")
        if rec:
            method = rec.get("method")
            if method in ("ocr_order", "xycut", "llm", "xycut_fallback"):
                counts[method] += 1
            llm_calls += int(rec.get("llm_calls", 0))
            if rec.get("llm_calls", 0) or method == "xycut_fallback":
                adjudication_pages += 1

    lines = ["# Case-memory ablation", "",
             "| Method | Count |",
             "|---|---:|"]
    for method in ("ocr_order", "xycut", "llm", "xycut_fallback"):
        lines.append(f"| {method} | {counts[method]} |")
    lines += ["", f"total llm_calls: {llm_calls}",
              f"pages needing adjudication: {adjudication_pages}", ""]
    if adjudication_pages == 0:
        lines.append("No page needed adjudication.")
    (out / "ablation.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"ocr_order={counts['ocr_order']} xycut={counts['xycut']} llm={counts['llm']} "
          f"xycut_fallback={counts['xycut_fallback']} total_llm_calls={llm_calls}")
    if adjudication_pages == 0:
        print("No page needed adjudication.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
