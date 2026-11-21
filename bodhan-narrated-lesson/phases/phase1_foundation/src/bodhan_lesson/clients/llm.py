"""Thin OpenAI-compatible LLM wrapper. Only chat completions - no provider-only
features - so any endpoint works (LLM_BASE_URL / LLM_MODEL / LLM_API_KEY)."""
from __future__ import annotations

import json
import re

from openai import AsyncOpenAI

from ..config import ConfigError, Settings

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def extract_json(raw: str):
    """Parse JSON from an LLM reply, tolerating markdown fences and prose."""
    cleaned = _FENCE.sub("", raw.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
        if not m:
            raise ValueError("no JSON found in LLM reply")
        return json.loads(m.group(1))


class LLM:
    def __init__(self, settings: Settings):
        if not (settings.llm_base_url and settings.llm_model):
            raise ConfigError("LLM_BASE_URL and LLM_MODEL must be set")
        self._client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key or "none")
        self._model = settings.llm_model

    async def complete(self, system: str, user: str, temperature: float = 0.0) -> str:
        resp = await self._client.chat.completions.create(
            model=self._model,
            temperature=temperature,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content or ""

    async def complete_json(self, system: str, user: str):
        return extract_json(await self.complete(system, user))


async def describe_image(llm: "LLM", system: str, user: str, image_path: str) -> str:
    """Multimodal call (OpenAI chat vision format). Used ONLY to describe figures in English."""
    import base64
    from pathlib import Path
    uri = "data:image/png;base64," + base64.b64encode(Path(image_path).read_bytes()).decode()
    resp = await llm._client.chat.completions.create(
        model=llm._model, temperature=0,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": [{"type": "text", "text": user},
                                               {"type": "image_url", "image_url": {"url": uri}}]}])
    return resp.choices[0].message.content or ""
