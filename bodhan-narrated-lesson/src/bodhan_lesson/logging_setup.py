"""Structured JSON logs to out/logs/run.jsonl plus a terse console line per stage."""
from __future__ import annotations

import json
import logging
from pathlib import Path

_STD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        d = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname,
             "logger": record.name, "event": record.getMessage()}
        d.update({k: v for k, v in record.__dict__.items() if k not in _STD})
        return json.dumps(d, ensure_ascii=False, default=str)


def setup(out_dir: Path, verbose: bool = False) -> None:
    log_dir = Path(out_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger("bodhan_lesson")
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_dir / "run.jsonl", encoding="utf-8")
    fh.setFormatter(JsonFormatter())
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO if verbose else logging.WARNING)
    ch.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(fh)
    root.addHandler(ch)
