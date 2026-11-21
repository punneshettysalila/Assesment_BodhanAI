"""Environment + yaml configuration. Secrets come from env only."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

BODHAN_DEFAULT_BASE = "https://api.bodhan.ai"

# Hosted prices from the assignment (INR); used for the cost report.
PRICES = {
    "ocr": ("per_image", 0.20),
    "translate": ("per_10k_output_tokens", 0.20),
    "speak": ("per_10k_input_chars", 6.0),
    "transcribe": ("per_audio_minute", 0.10),
}


class ConfigError(RuntimeError):
    pass


@dataclass
class Settings:
    bodhan_base_url: str
    keys: dict[str, str]
    llm_base_url: str
    llm_model: str
    llm_api_key: str
    max_concurrency: int = 4
    max_retries: int = 4
    thresholds: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, thresholds_path: Path | None = None, require: tuple[str, ...] = ()) -> "Settings":
        keys = {
            "ocr": os.getenv("BODHAN_OCR_KEY", ""),
            "translate": os.getenv("BODHAN_TRANSLATE_KEY", ""),
            "speak": os.getenv("BODHAN_SPEAK_KEY", ""),
            "transcribe": os.getenv("BODHAN_TRANSCRIBE_KEY", ""),
        }
        missing = [m for m in require if not keys.get(m)]
        if missing:
            raise ConfigError(f"Missing Bodhan key(s) for: {', '.join(missing)} (see .env.example)")
        thresholds = {}
        if thresholds_path and thresholds_path.exists():
            thresholds = yaml.safe_load(thresholds_path.read_text()) or {}
        return cls(
            bodhan_base_url=os.getenv("BODHAN_BASE_URL", BODHAN_DEFAULT_BASE),
            keys=keys,
            llm_base_url=os.getenv("LLM_BASE_URL", ""),
            llm_model=os.getenv("LLM_MODEL", ""),
            llm_api_key=os.getenv("LLM_API_KEY", ""),
            thresholds=thresholds,
        )
