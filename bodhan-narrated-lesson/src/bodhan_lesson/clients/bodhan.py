"""The four Bodhan models behind one facade. Routes/prompts come from
configs/endpoints.yaml (published Bodhan API routes)."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import wave
from pathlib import Path
from typing import Any

import httpx
import yaml
from PIL import Image

from ..config import Settings
from .base import BodhanClient

DEFAULT_ENDPOINTS = Path(__file__).resolve().parents[3] / "configs" / "endpoints.yaml"


def wav_seconds(data: bytes) -> float:
    try:
        with wave.open(io.BytesIO(data)) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def _tokens_estimate(text: str) -> int:
    return max(1, len(text) // 3)


DEFAULT_VOICES = {
    "as": "Prastuti", "bn": "Ishita", "brx": "Gwrbw", "doi": "Preeti", "gu": "Dhara",
    "hi": "Kavya", "kn": "Deepika", "kok": "Anjali", "ks": "Zoon", "mai": "Vaidehi",
    "ml": "Lakshmi", "mni": "Thoibi", "mr": "Anagha", "ne": "Srijana", "or": "Itishree",
    "pa": "Kaur", "sa": "Bharati", "sat": "Phulmani", "sd": "Moomal", "ta": "Anitha",
    "te": "Sravani", "ur": "Saba", "en": "Amit",
}


class Bodhan:
    def __init__(self, settings: Settings, endpoints_path: Path = DEFAULT_ENDPOINTS,
                 transport: httpx.AsyncBaseTransport | None = None):
        self.ep = yaml.safe_load(Path(endpoints_path).read_text())
        self.translation_script = "native"
        sem = asyncio.Semaphore(settings.max_concurrency)

        def mk(name: str, cost_fn):
            return BodhanClient(
                self.ep[name]["model"], settings.bodhan_base_url, settings.keys.get(name, ""),
                sem, cost_fn=cost_fn, max_retries=settings.max_retries, transport=transport,
            )

        self.ocr_c = mk("ocr", lambda h: (1, 0.20))
        self.translate_c = mk("translate", lambda h: (h["tokens"], 0.20 * h["tokens"] / 10_000))
        self.speak_c = mk("speak", lambda h: (h["chars"], 6.0 * h["chars"] / 10_000))
        self.transcribe_c = mk("transcribe", lambda h: (h["seconds"] / 60, 0.10 * h["seconds"] / 60))

    @property
    def stats(self) -> dict[str, Any]:
        return {n: getattr(self, f"{n}_c").stats.model_dump()
                for n in ("ocr", "translate", "speak", "transcribe")}

    async def aclose(self) -> None:
        for n in ("ocr", "translate", "speak", "transcribe"):
            await getattr(self, f"{n}_c").aclose()

    # ---- Indic-OCR ----------------------------------------------------------
    async def ocr(self, image_path: str | Path) -> str:
        image_path = Path(image_path)
        data = image_path.read_bytes()
        mime = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        uri = f"data:{mime};base64," + base64.b64encode(data).decode()
        e = self.ep["ocr"]
        body = {"model": e["model"], "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": uri}}]}], "table_format": "markdown"}
        r = await self.ocr_c.request(e["path"], usage_hint={}, json=body)
        response = r.json()
        # Preserve Bodhan's detected blocks and normalize pixel boxes for XY-cut.
        try:
            width, height = Image.open(io.BytesIO(data)).size
        except Exception:
            width = height = 1
        blocks = []
        for b in response.get("blocks", []):
            box = b.get("bbox_xyxy")
            blocks.append({"type": b.get("label") or b.get("type", ""), "text": b.get("text", ""),
                           "bbox": [box[0] / width, box[1] / height, box[2] / width, box[3] / height]
                           if isinstance(box, list) and len(box) == 4 else None,
                           "layout_confidence": b.get("conf"), "order": b.get("order")})
        if blocks:
            return json.dumps({"blocks": blocks, "markdown": response["choices"][0]["message"]["content"]}, ensure_ascii=False)
        return response["choices"][0]["message"]["content"]

    # ---- Indic-Translate ----------------------------------------------------
    async def translate(self, text: str, src: str, tgt: str) -> str:
        e = self.ep["translate"]
        # Use Bodhan's OpenAI-compatible translation transport. The source
        # language is inferred; `src` remains for the internal cache contract.
        body = {"model": e["model"], "messages": [{"role": "user", "content": text}],
                "target_language_code": tgt}
        if tgt != "en":
            body["script"] = self.translation_script
        r = await self.translate_c.request(e["path"], usage_hint={"tokens": 0}, json=body)
        js = r.json()
        if js.get("error"):
            err = js["error"]
            raise RuntimeError(f"Bodhan Translate {err.get('code', 'error')}: {err.get('message', '')}")
        if js.get("truncated"):
            raise RuntimeError("Bodhan Translate returned a truncated result")
        out = js["choices"][0]["message"]["content"].strip()
        toks = (js.get("usage") or {}).get("completion_tokens") or _tokens_estimate(out)
        self.translate_c.stats.units += toks
        self.translate_c.stats.cost_inr += 0.20 * toks / 10_000
        return out

    # ---- Indic-Speak --------------------------------------------------------
    async def speak(self, text: str, lang: str, voice: str | None = None) -> bytes:
        e = self.ep["speak"]
        voice = voice or DEFAULT_VOICES.get(lang)
        if not voice:
            raise ValueError(f"No documented Indic-Speak voice is configured for language {lang!r}; use --voices")
        body = {"model": e["model"], "input": text, "voice": voice,
                "instructions": json.dumps({"lang": lang})}
        r = await self.speak_c.request(e["path"], usage_hint={"chars": len(text)}, json=body)
        return r.content

    # ---- Indic-Transcribe ---------------------------------------------------
    async def transcribe(self, wav_bytes: bytes, lang: str) -> str:
        e = self.ep["transcribe"]
        secs = wav_seconds(wav_bytes)
        r = await self.transcribe_c.request(
            e["path"], usage_hint={"seconds": secs},
            data={"model": e["model"], "language": lang},
            files={"file": ("chunk.wav", wav_bytes, "audio/wav")})
        return r.json().get("text", "")
