"""Content-hash disk cache so reruns never repeat paid calls (resumable runs)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class DiskCache:
    def __init__(self, root: Path | None):
        self.root = Path(root) if root else None
        if self.root:
            self.root.mkdir(parents=True, exist_ok=True)
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(*parts: Any) -> str:
        h = hashlib.sha256()
        for p in parts:
            h.update(p if isinstance(p, bytes) else json.dumps(p, sort_keys=True, ensure_ascii=False).encode())
            h.update(b"\x00")
        return h.hexdigest()

    def _path(self, ns: str, key: str, ext: str) -> Path | None:
        return self.root / ns / f"{key}.{ext}" if self.root else None

    def get(self, ns: str, key: str, ext: str = "json") -> Any | None:
        p = self._path(ns, key, ext)
        if p and p.exists():
            self.hits += 1
            data = p.read_bytes()
            return data if ext == "bin" else json.loads(data)
        self.misses += 1
        return None

    def set(self, ns: str, key: str, value: Any, ext: str = "json") -> None:
        p = self._path(ns, key, ext)
        if not p:
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(value if ext == "bin" else json.dumps(value, ensure_ascii=False).encode())
