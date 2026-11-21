"""Recursive XY-cut reading order from normalised bounding boxes."""
from __future__ import annotations

from ..models import Block


def _best_cut(blocks: list[Block], axis: int, min_gap: float):
    """Largest empty gap along axis (0=x, 1=y). Returns (gap, left_group, right_group)."""
    s = sorted(blocks, key=lambda b: b.bbox[axis])
    best = (0.0, None)
    run_end = s[0].bbox[axis + 2]
    for i in range(1, len(s)):
        gap = s[i].bbox[axis] - run_end
        if gap > best[0]:
            best = (gap, i)
        run_end = max(run_end, s[i].bbox[axis + 2])
    gap, i = best
    if i is None or gap < min_gap:
        return 0.0, None, None
    return gap, s[:i], s[i:]


def xy_cut_order(blocks: list[Block], min_gap_x: float = 0.02, min_gap_y: float = 0.008) -> list[Block]:
    if not blocks or not all(b.bbox for b in blocks):
        return list(blocks)

    def cut(bs: list[Block]) -> list[Block]:
        if len(bs) <= 1:
            return list(bs)
        gx, lx, rx = _best_cut(bs, 0, min_gap_x)
        gy, ly, ry = _best_cut(bs, 1, min_gap_y)
        if gx == 0 and gy == 0:
            return sorted(bs, key=lambda b: (b.bbox[1], b.bbox[0]))
        if gx > gy:
            return cut(lx) + cut(rx)
        return cut(ly) + cut(ry)

    return cut(blocks)
