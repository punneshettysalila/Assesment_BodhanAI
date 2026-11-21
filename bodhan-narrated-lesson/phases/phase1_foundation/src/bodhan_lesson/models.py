"""Core data models. Every downstream artifact traces back to a Block id."""
from __future__ import annotations

import hashlib
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    EQUATION = "equation"
    FIGURE = "figure"
    CAPTION = "caption"
    HEADER = "header"
    FOOTER = "footer"
    PAGE_NUMBER = "page_number"
    HANDWRITTEN = "handwritten"
    OTHER = "other"


class Flag(str, Enum):
    LOW_CONFIDENCE = "low_confidence"
    GARBLED = "garbled"
    BAD_LATEX = "bad_latex"
    REORDERED = "reordered"
    RECROPPED = "recropped"
    RUNNING_HEADER = "running_header"
    SPLIT_ACROSS_PAGE = "split_across_page"


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class Block(BaseModel):
    """One OCR block. `text` comes from Indic-OCR only and is never rewritten
    by the LLM; `text_sha` lets validators prove that."""

    id: str                      # e.g. "p03-b007"
    page: int
    type: BlockType = BlockType.PARAGRAPH
    text: str
    bbox: Optional[tuple[float, float, float, float]] = None  # x0,y0,x1,y1 normalised 0-1
    confidence: Optional[float] = None
    flags: list[Flag] = Field(default_factory=list)
    order: int = 0
    text_sha: str = ""
    meta: dict = Field(default_factory=dict)   # e.g. heading level, removed_reason

    def model_post_init(self, _ctx) -> None:
        if not self.text_sha:
            self.text_sha = text_hash(self.text)

    def intact(self) -> bool:
        return text_hash(self.text) == self.text_sha


class Page(BaseModel):
    number: int
    image_path: str
    quality: dict = Field(default_factory=dict)   # blur, skew, contrast
    blocks: list[Block] = Field(default_factory=list)
    ocr_attempts: int = 0


class CallStats(BaseModel):
    """Per-model usage, aggregated into report.json."""

    calls: int = 0
    retries: int = 0
    failures: int = 0
    latency_s: float = 0.0
    cost_inr: float = 0.0
    units: float = 0.0   # images / output tokens / input chars / audio minutes
