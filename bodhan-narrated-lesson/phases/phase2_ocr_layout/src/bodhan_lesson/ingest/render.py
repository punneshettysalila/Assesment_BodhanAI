"""PDF/folder -> page images. Always renders to images: the PDF text layer is never used."""
from __future__ import annotations

import re
from pathlib import Path

from ..models import Page

IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}


def natural_key(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def render_input(input_path: Path, work_dir: Path, dpi: int = 150) -> list[Page]:
    input_path, work_dir = Path(input_path), Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    if input_path.is_dir():
        files = sorted((f for f in input_path.iterdir() if f.suffix.lower() in IMG_EXT), key=natural_key)
        if not files:
            raise FileNotFoundError(f"no page images in {input_path}")
        return [Page(number=i + 1, image_path=str(f)) for i, f in enumerate(files)]
    if input_path.suffix.lower() == ".pdf":
        from pdf2image import convert_from_path  # needs poppler
        out = []
        for i, img in enumerate(convert_from_path(str(input_path), dpi=dpi), start=1):
            p = work_dir / f"page-{i:03d}.png"
            img.save(p)
            out.append(Page(number=i, image_path=str(p)))
        return out
    raise ValueError(f"unsupported input: {input_path}")
