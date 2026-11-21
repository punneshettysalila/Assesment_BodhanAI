"""Language registry. Unknown codes are passed through (we are told a language
outside the demo set will be tested), only script checks are skipped for them."""
from __future__ import annotations

LANGS = {
    "en": ("English", "Latin"), "hi": ("Hindi", "Devanagari"), "bn": ("Bengali", "Bengali"),
    "ta": ("Tamil", "Tamil"), "te": ("Telugu", "Telugu"), "mr": ("Marathi", "Devanagari"),
    "gu": ("Gujarati", "Gujarati"), "kn": ("Kannada", "Kannada"), "ml": ("Malayalam", "Malayalam"),
    "pa": ("Punjabi", "Gurmukhi"), "or": ("Odia", "Odia"), "as": ("Assamese", "Bengali"),
    "ur": ("Urdu", "Arabic"), "ne": ("Nepali", "Devanagari"), "sa": ("Sanskrit", "Devanagari"),
}
SCRIPT_RANGES = {
    "Devanagari": (0x0900, 0x097F), "Bengali": (0x0980, 0x09FF), "Gurmukhi": (0x0A00, 0x0A7F),
    "Gujarati": (0x0A80, 0x0AFF), "Odia": (0x0B00, 0x0B7F), "Tamil": (0x0B80, 0x0BFF),
    "Telugu": (0x0C00, 0x0C7F), "Kannada": (0x0C80, 0x0CFF), "Malayalam": (0x0D00, 0x0D7F),
    "Arabic": (0x0600, 0x06FF),
}


def lang_name(code: str) -> str:
    return LANGS.get(code, (code, ""))[0]


def script_of(code: str) -> str | None:
    return LANGS.get(code, ("", None))[1]


def script_ratio(text: str, code: str) -> float | None:
    """Share of letters in the language's native script (None if unknown/Latin)."""
    script = script_of(code)
    if not script or script == "Latin" or script not in SCRIPT_RANGES:
        return None
    lo, hi = SCRIPT_RANGES[script]
    letters = [c for c in text if c.isalpha() or "\u0900" <= c <= "\u0d7f"]
    if not letters:
        return 1.0
    return sum(1 for c in letters if lo <= ord(c) <= hi) / len(letters)


def detect_script_lang(text: str) -> str:
    """Cheap source-language guess from OCR text (script only). Defaults to en."""
    best, best_n = "en", sum(1 for c in text if "a" <= c.lower() <= "z")
    first_by_script = {"Devanagari": "hi", "Bengali": "bn", "Gurmukhi": "pa", "Gujarati": "gu",
                       "Odia": "or", "Tamil": "ta", "Telugu": "te", "Kannada": "kn",
                       "Malayalam": "ml", "Arabic": "ur"}
    for script, (lo, hi) in SCRIPT_RANGES.items():
        n = sum(1 for c in text if lo <= ord(c) <= hi)
        if n > best_n:
            best, best_n = first_by_script[script], n
    return best
