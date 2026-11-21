"""Automatic-fail guard: no non-Bodhan OCR / MT / TTS / ASR anywhere in src."""
import re
from pathlib import Path

FORBIDDEN = [
    "pytesseract", "tesseract", "easyocr", "paddleocr", "google.cloud", "googletrans",
    "deep_translator", "indictrans", "IndicTrans", "gtts", "pyttsx3", "elevenlabs",
    "whisper", "azure.cognitiveservices", "boto3", "transformers", "argostranslate",
]
SRC = Path(__file__).resolve().parents[2] / "src"


def test_no_forbidden_imports_or_strings():
    pattern = re.compile(r"^\s*(?:import|from)\s+(" + "|".join(map(re.escape, FORBIDDEN)) + r")", re.M)
    offenders = []
    for f in SRC.rglob("*.py"):
        if pattern.search(f.read_text(encoding="utf-8")):
            offenders.append(str(f))
    assert not offenders, f"forbidden model libraries imported: {offenders}"


def test_pyproject_has_no_forbidden_deps():
    text = (SRC.parent / "pyproject.toml").read_text(encoding="utf-8").lower()
    assert not [d for d in ("pytesseract", "easyocr", "googletrans", "gtts", "openai-whisper") if d in text]
