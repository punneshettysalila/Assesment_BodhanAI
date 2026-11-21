"""Self-contained report.html generated from report.json (no external assets)."""
from __future__ import annotations

import html
import json
from pathlib import Path

CSS = """body{font:15px/1.5 system-ui,sans-serif;margin:2rem auto;max-width:980px;color:#222;padding:0 1rem}
h1{font-size:1.5rem}h2{font-size:1.1rem;margin-top:2rem;border-bottom:1px solid #ddd;padding-bottom:.3rem}
table{border-collapse:collapse;width:100%;margin:.5rem 0}td,th{border:1px solid #ddd;padding:.35rem .6rem;text-align:left;font-size:.9rem}
th{background:#f5f5f5}.ok{color:#0a7d33;font-weight:600}.partial{color:#b26a00;font-weight:600}.failed{color:#b00020;font-weight:600}
.card{display:inline-block;border:1px solid #ddd;border-radius:8px;padding:.6rem 1rem;margin:.2rem .4rem .2rem 0}
.card b{display:block;font-size:1.3rem}code{background:#f3f3f3;padding:0 .25rem;border-radius:3px}"""


def _e(x) -> str:
    return html.escape(str(x))


def render(data: dict) -> str:
    src, usage = data.get("source", {}), data.get("usage", {})
    parts = [f"<!doctype html><meta charset=utf-8><title>Narrated lesson report</title><style>{CSS}</style>",
             "<h1>Narrated lesson - run report</h1>"]
    cards = [("Pages", src.get("pages", "-")), ("Blocks", src.get("blocks", "-")),
             ("Sections", src.get("sections", "-")), ("Flagged blocks", src.get("flagged_blocks", "-")),
             ("Chrome removed", src.get("removed_chrome", "-")),
             ("Total cost (INR)", usage.get("total_cost_inr", "-")), ("Runtime (s)", data.get("total_runtime_s", "-"))]
    parts.append("".join(f"<div class=card>{_e(k)}<b>{_e(v)}</b></div>" for k, v in cards))
    parts.append("<h2>Languages</h2><table><tr><th>Lang<th>Status<th>Structure<th>Mean CER<th>Worst CER<th>Loudness (LUFS)<th>Skipped blocks<th>Glossary consistency</tr>")
    for code, L in data.get("languages", {}).items():
        t = L.get("targets", {})
        lufs = t.get("loudness_lufs_range")
        parts.append(
            f"<tr><td>{_e(code)}<td class={_e(L.get('status'))}>{_e(L.get('status'))}"
            f"<td>{_e('OK' if L.get('structure_ok') else 'check')}<td>{_e(t.get('section_mean_cer', '-'))}"
            f"<td>{_e(t.get('worst_section_cer', '-'))}<td>{_e(lufs if lufs else '-')}"
            f"<td>{len(L.get('skipped_blocks', []))}<td>{_e((L.get('glossary') or {}).get('consistency', '-'))}</tr>")
    parts.append("</table>")
    for code, L in data.get("languages", {}).items():
        if L.get("sections"):
            parts.append(f"<h2>Sections - {_e(code)}</h2><table><tr><th>#<th>Title<th>Chunks<th>Retried<th>Degraded<th>Failed<th>Mean CER<th>Seconds<th>LUFS</tr>")
            for s in L["sections"]:
                parts.append(f"<tr><td>{s['index']}<td>{_e(s['title'])}<td>{s['chunks']}<td>{s['retried_chunks']}"
                             f"<td>{s['degraded_chunks']}<td>{s['failed_chunks']}<td>{_e(s['mean_cer'])}"
                             f"<td>{_e(s['seconds'])}<td>{_e(s['lufs'])}</tr>")
            parts.append("</table>")
    parts.append("<h2>Model usage</h2><table><tr><th>Model<th>Calls<th>Retries<th>Failures<th>Latency (s)<th>Cost (INR)</tr>")
    for name, u in usage.items():
        if isinstance(u, dict):
            parts.append(f"<tr><td>{_e(name)}<td>{u['calls']}<td>{u['retries']}<td>{u['failures']}"
                         f"<td>{round(u['latency_s'], 2)}<td>{round(u['cost_inr'], 3)}</tr>")
    parts.append("</table><h2>Stage timings (s)</h2><table>")
    for k, v in data.get("timings_s", {}).items():
        parts.append(f"<tr><td><code>{_e(k)}</code><td>{_e(v)}</tr>")
    parts.append("</table>")
    if data.get("warnings"):
        parts.append("<h2>Warnings</h2><ul>" + "".join(f"<li>{_e(json.dumps(w, ensure_ascii=False))}</li>" for w in data["warnings"]) + "</ul>")
    return "\n".join(parts)


def write_html(data: dict, path: Path) -> None:
    Path(path).write_text(render(data), encoding="utf-8")
