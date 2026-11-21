"""Deterministic LaTeX -> spoken English (no LLM, so numbers can never be invented)."""
from __future__ import annotations

import re

SYMBOLS = [
    (r"\\angle", " angle "), (r"\\measuredangle", " angle "), (r"\\triangle", " triangle "),
    (r"\\parallel", " is parallel to "), (r"\\nparallel", " is not parallel to "),
    (r"\\perp", " is perpendicular to "), (r"\\cong", " is congruent to "), (r"\\sim", " is similar to "),
    (r"\\therefore", " therefore "), (r"\\because", " because "),
    (r"\\Rightarrow|\\implies|\\to|\\rightarrow", " implies "), (r"\\Leftrightarrow|\\iff", " if and only if "),
    (r"\\neq|\\ne", " is not equal to "), (r"\\leq|\\le", " is less than or equal to "),
    (r"\\geq|\\ge", " is greater than or equal to "), (r"\\times|\\cdot", " times "), (r"\\div", " divided by "),
    (r"\\pm", " plus or minus "), (r"\\pi", " pi "), (r"\\infty", " infinity "),
    (r"\\circ|\\degree", " degrees "), (r"\\in", " belongs to "), (r"\\ldots|\\dots|\\cdots", " and so on "),
    (r"\\quad|\\qquad|\\,|\\;|\\!|\\ ", " "), (r"\\left|\\right", ""), (r"\\%", " percent "),
    (r"∠", " angle "), (r"△", " triangle "), (r"°", " degrees "), (r"∥", " is parallel to "),
    (r"⊥", " is perpendicular to "), (r"≅", " is congruent to "), (r"∴", " therefore "),
]
WRAP = [
    (r"\\overleftrightarrow\{([^{}]*)\}", r" line \1 "), (r"\\overrightarrow\{([^{}]*)\}", r" ray \1 "),
    (r"\\overline\{([^{}]*)\}", r" line segment \1 "), (r"\\(?:widehat|hat)\{([^{}]*)\}", r" angle \1 "),
    (r"\\sqrt\{([^{}]*)\}", r" square root of \1 "), (r"\\(?:text|mathrm|mathbf|textbf)\{([^{}]*)\}", r" \1 "),
]
_FRAC = re.compile(r"\\d?frac\{([^{}]*)\}\{([^{}]*)\}")


def _strip_delims(s: str) -> str:
    s = s.strip()
    for a, b in (("$$", "$$"), ("\\[", "\\]"), ("\\(", "\\)"), ("$", "$")):
        if s.startswith(a) and s.endswith(b) and len(s) >= len(a) + len(b):
            return s[len(a):len(s) - len(b)]
    return s


def latex_to_speech(latex: str) -> tuple[str, list[str]]:
    """Returns (spoken text, unknown commands). Unknown commands are dropped and reported."""
    s = _strip_delims(latex)
    for _ in range(4):                                  # nested wrappers / fractions
        s = _FRAC.sub(r" \1 over \2 ", s)
        for pat, rep in WRAP:
            s = re.sub(pat, rep, s)
    s = re.sub(r"\^\{?\\circ\}?", " degrees ", s)
    s = re.sub(r"\^\{?2\}?", " squared ", s)
    s = re.sub(r"\^\{?3\}?", " cubed ", s)
    s = re.sub(r"\^\{([^{}]*)\}|\^(\w)", lambda m: f" to the power {m.group(1) or m.group(2)} ", s)
    s = re.sub(r"_\{([^{}]*)\}|_(\w)", lambda m: f" sub {m.group(1) or m.group(2)} ", s)
    for pat, rep in SYMBOLS:
        s = re.sub(pat, rep, s)
    s = re.sub(r"(?<=\S)\s*=\s*(?=\S)|=", " equals ", s)
    s = re.sub(r"(?<=[\w)}\s])\s*\+\s*", " plus ", s)
    s = re.sub(r"(?<=[\w)}])\s*-\s*(?=[\w({])", " minus ", s)
    s = re.sub(r"(?<![\w])-\s*(?=[\w(])", " minus ", s)
    s = re.sub(r"\s*<\s*", " is less than ", s)
    s = re.sub(r"\s*>\s*", " is greater than ", s)
    unknown = sorted(set(re.findall(r"\\[a-zA-Z]+", s)))
    s = re.sub(r"\\[a-zA-Z]+", " ", s)
    s = re.sub(r"[{}]", " ", s)
    s = re.sub(r"\b([A-Z]{2,4})\b", lambda m: " ".join(m.group(1)), s)   # AB -> A B (geometry labels)
    return re.sub(r"\s+", " ", s).strip(), unknown


def inline_math_to_speech(text: str) -> tuple[str, list[str]]:
    """Replace $...$ spans in prose with spoken English."""
    from ..translate.mask import LATEX
    unknown: list[str] = []

    def sub(m: re.Match) -> str:
        spoken, unk = latex_to_speech(m.group(0))
        unknown.extend(unk)
        return f" {spoken} "

    return re.sub(r"\s+", " ", LATEX.sub(sub, text)).strip(), unknown
