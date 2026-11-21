"""Case memory: retrieve similar, VERIFIED past layout decisions as few-shot examples.

Training-free analogue of retrieval-augmented RFT: instead of updating model weights, the
pipeline stores (situation -> action) cases whose outcome passed the programmatic verifier
(permutation + intact-text guards) and retrieves the nearest ones for new pages. Only
structure (block types, column count) is stored - never page text."""
from __future__ import annotations

import json
from pathlib import Path

from ..models import Block


def signature(blocks: list[Block]) -> list[str]:
    bs = sorted(blocks, key=lambda b: b.order)
    xs = sorted({round(((b.bbox[0] + b.bbox[2]) / 2) * 4) for b in bs if b.bbox and (b.bbox[2] - b.bbox[0]) < 0.6})
    toks = [f"t:{b.type.value}" for b in bs]
    toks += [f"cols:{len(xs)}", f"n:{min(len(bs), 12) // 3}"]
    toks += [f"wide:{sum(1 for b in bs if b.bbox and (b.bbox[2] - b.bbox[0]) >= 0.6)}"]
    return toks


def _sim(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb) if sa | sb else 0.0


class CaseMemory:
    def __init__(self, path: Path | None, max_cases: int = 200):
        self.path, self.max_cases = (Path(path) if path else None), max_cases
        self.cases: list[dict] = []
        if self.path and self.path.exists():
            self.cases = [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()][-max_cases:]

    def record(self, blocks: list[Block], ordered_ids: list[str], method: str) -> None:
        """Store a decision ONLY if it was verifier-approved (method llm / xycut agreement)."""
        if method not in ("llm", "xycut"):
            return
        base = [b.id for b in sorted(blocks, key=lambda b: b.order)]
        perm = [base.index(i) for i in ordered_ids]
        if perm == sorted(perm):                     # identity decisions carry no signal
            return
        case = {"sig": signature(blocks), "perm": perm, "types": [b.type.value for b in sorted(blocks, key=lambda b: b.order)]}
        self.cases.append(case)
        self.cases = self.cases[-self.max_cases:]
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(json.dumps(case) + "\n")

    def examples(self, blocks: list[Block], k: int = 2, min_sim: float = 0.5) -> str:
        sig = signature(blocks)
        scored = sorted(((_sim(sig, c["sig"]), c) for c in self.cases if len(c["perm"]) == len(blocks)),
                        key=lambda x: -x[0])
        picks = [c for s, c in scored[:k] if s >= min_sim]
        if not picks:
            return ""
        lines = [f"- block types in OCR order {c['types']} -> correct reading order as OCR indexes {c['perm']}"
                 for c in picks]
        return "\nSimilar pages already solved (verified):\n" + "\n".join(lines) + \
               "\nUse them only as a hint about layout patterns; answer with block ids."
