import asyncio
import io
import json
import wave

import httpx
from PIL import Image

from bodhan_lesson.clients.bodhan import Bodhan
from bodhan_lesson.config import Settings
from bodhan_lesson.models import BlockType
from bodhan_lesson.ocr.parse import parse_ocr_response


def make_wav():
    stream = io.BytesIO()
    with wave.open(stream, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 1600)
    return stream.getvalue()


async def test_documented_bodhan_routes_and_payloads(tmp_path):
    seen = []

    def handler(request):
        body = request.read()
        seen.append((request.url.path, request.headers.get("content-type", ""), body))
        if request.url.path == "/v1/chat/completions" and b"indic-translate" in body:
            return httpx.Response(200, json={"choices": [{"message": {"content": "अनुवाद"}}],
                                             "usage": {"completion_tokens": 2}})
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "# Chapter"}}],
                "blocks": [{"order": 0, "label": "Section-title", "type": "SectionHeader",
                            "bbox_xyxy": [10, 10, 90, 30], "conf": 0.93, "text": "Chapter"}],
            })
        if request.url.path == "/v1/audio/speech":
            return httpx.Response(200, content=make_wav(), headers={"content-type": "audio/wav"})
        if request.url.path == "/v1/audio/transcriptions":
            return httpx.Response(200, json={"text": "नमस्ते"})
        return httpx.Response(404)

    settings = Settings("https://api.test", {k: "key" for k in
                      ("ocr", "translate", "speak", "transcribe")}, "", "", "", max_concurrency=1)
    bodhan = Bodhan(settings, transport=httpx.MockTransport(handler))
    image_path = tmp_path / "page.png"
    Image.new("RGB", (100, 100), "white").save(image_path)
    try:
        parsed = parse_ocr_response(1, await bodhan.ocr(image_path))
        assert parsed[0].type == BlockType.HEADING
        assert parsed[0].bbox == (0.1, 0.1, 0.9, 0.3)
        assert parsed[0].confidence is None
        assert parsed[0].meta["layout_confidence"] == 0.93
        assert await bodhan.translate("Hello", "en", "hi") == "अनुवाद"
        assert await bodhan.translate("नमस्ते", "hi", "en") == "अनुवाद"
        assert (await bodhan.speak("नमस्ते", "hi", "Kavya"))[:4] == b"RIFF"
        assert await bodhan.transcribe(make_wav(), "hi") == "नमस्ते"
    finally:
        await bodhan.aclose()

    paths = [item[0] for item in seen]
    assert paths == ["/v1/chat/completions", "/v1/chat/completions", "/v1/chat/completions",
                    "/v1/audio/speech", "/v1/audio/transcriptions"]
    ocr_body = json.loads(seen[0][2])
    assert "text" not in ocr_body["messages"][0]["content"]
    translate_body = json.loads(seen[1][2])
    assert translate_body == {"model": "indic-translate", "messages": [{"role": "user", "content": "Hello"}],
                              "target_language_code": "hi", "script": "native"}
    english_translation_body = json.loads(seen[2][2])
    assert english_translation_body == {"model": "indic-translate", "messages": [{"role": "user", "content": "नमस्ते"}],
                                        "target_language_code": "en"}
    speak_body = json.loads(seen[3][2])
    assert speak_body["voice"] == "Kavya" and json.loads(speak_body["instructions"]) == {"lang": "hi"}
