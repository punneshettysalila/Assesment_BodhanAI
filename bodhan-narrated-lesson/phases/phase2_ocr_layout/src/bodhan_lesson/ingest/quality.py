"""Scan quality metrics + deskew. Only OpenCV/numpy; no OCR here."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def _gray(path: str) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"cannot read image: {path}")
    return img


def estimate_skew(gray: np.ndarray, max_angle: float = 6.0, step: float = 0.25) -> float:
    """Projection-profile skew estimate in degrees (positive = needs counter-clockwise rotation)."""
    small = cv2.resize(gray, None, fx=0.4, fy=0.4, interpolation=cv2.INTER_AREA) if gray.shape[1] > 900 else gray
    _, bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = bw.shape
    best, best_score = 0.0, -1.0
    for a in np.arange(-max_angle, max_angle + step, step):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), float(a), 1.0)
        rot = cv2.warpAffine(bw, m, (w, h), flags=cv2.INTER_NEAREST)
        score = float(np.var(rot.sum(axis=1)))
        if score > best_score:
            best, best_score = float(a), score
    return best


def measure(image_path: str) -> dict:
    g = _gray(image_path)
    return {
        "blur": float(cv2.Laplacian(g, cv2.CV_64F).var()),     # low = blurry
        "contrast": float(g.std()),
        "skew_deg": estimate_skew(g),
        "width": int(g.shape[1]), "height": int(g.shape[0]),
    }


def deskew(image_path: str, angle: float, out_path: str) -> str:
    img = cv2.imread(str(image_path))
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    rot = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
    cv2.imwrite(str(out_path), rot)
    return str(out_path)


def upscale(image_path: str, scale: float, out_path: str) -> str:
    img = cv2.imread(str(image_path))
    big = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    cv2.imwrite(str(out_path), big)
    return str(out_path)


def prepare(image_path: str, work_dir: Path, min_skew: float = 0.75) -> tuple[str, dict]:
    """Measure, then deskew when the tilt matters. Returns (path_to_use, metrics)."""
    q = measure(image_path)
    q["deskewed"] = False
    if abs(q["skew_deg"]) >= min_skew:
        out = Path(work_dir) / (Path(image_path).stem + ".deskew.png")
        deskew(image_path, q["skew_deg"], str(out))
        q["deskewed"] = True
        return str(out), q
    return image_path, q
