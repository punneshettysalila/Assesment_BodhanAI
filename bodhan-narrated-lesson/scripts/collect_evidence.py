from __future__ import annotations

import argparse
import json
from pathlib import Path


def tree(path: Path, prefix: str = "", depth: int = 0, max_depth: int = 3) -> list[str]:
    if depth >= max_depth:
        return []
    lines = []
    entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    for i, entry in enumerate(entries):
        last = i == len(entries) - 1
        lines.append(prefix + ("`-- " if last else "|-- ") + entry.name)
        if entry.is_dir() and depth + 1 < max_depth:
            lines.extend(tree(entry, prefix + ("    " if last else "|   "), depth + 1, max_depth))
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("OUT_DIR", type=Path)
    ap.add_argument("--patch-readme", action="store_true")
    args = ap.parse_args()
    out = args.OUT_DIR
    report_path = out / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    evidence = out / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    lines = ["# Evidence Summary", "", "## Output tree (depth 3)", "", "```text", out.name]
    lines.extend(tree(out))
    lines += ["```", "", "## Language results", "",
              "| Language | Status | Structure | Mean CER | Worst CER | Loudness range | Skipped blocks | Retried chunks |",
              "|---|---|---|---|---|---|---|---|"]
    for lang, data in report.get("languages", {}).items():
        targets = data.get("targets", {})
        secs = data.get("sections", [])
        mean_cer = targets.get("section_mean_cer")
        worst_cer = targets.get("worst_section_cer")
        loud = targets.get("loudness_lufs_range")
        retried = sum(s.get("retried_chunks", 0) for s in secs)
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} |".format(
            lang, data.get("status", ""), data.get("structure_ok", ""),
            "" if mean_cer is None else mean_cer,
            "" if worst_cer is None else worst_cer,
            "" if loud is None else f"{loud[0]} to {loud[1]}",
            len(data.get("skipped_blocks", [])), retried))
    cost = report.get("usage", {}).get("total_cost_inr")
    if cost is None:
        cost = sum(float(v.get("cost_inr", 0)) for v in report.get("usage", {}).values()
                   if isinstance(v, dict))
    lines += ["", f"Total cost INR: {float(cost):.3f}",
              f"Runtime: {float(report.get('total_runtime_s', 0)):.2f} s", ""]
    table = "\n".join(lines)
    (evidence / "summary.md").write_text(table, encoding="utf-8")
    if args.patch_readme:
        readme = Path(__file__).resolve().parents[1] / "README.md"
        text = readme.read_text(encoding="utf-8")
        start, end = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
        if start in text and end in text:
            before = text.split(start, 1)[0]
            after = text.split(end, 1)[1]
            readme_table = [
                "| Language | Status | Structure | Mean CER | Worst CER | Loudness range | Skipped blocks | Retried chunks |",
                "|---|---|---|---|---|---|---|---|",
            ]
            readme_table.extend(lines[lines.index("| Language | Status | Structure | Mean CER | Worst CER | Loudness range | Skipped blocks | Retried chunks |") + 2:
                                      lines.index("", lines.index("| Language | Status | Structure | Mean CER | Worst CER | Loudness range | Skipped blocks | Retried chunks |"))])
            readme_text = before + start + "\n" + "\n".join(readme_table) + "\n" + end + after
            readme.write_text(readme_text, encoding="utf-8")
    print(evidence / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
