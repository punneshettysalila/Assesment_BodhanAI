# Design notes

## LLM rules enforced in code (`layout/validators.py`)
Reorder output must be an exact permutation of block ids; flags must be known; OCR text hashes
must be unchanged after every LLM step; English edits must keep numbers and LaTeX and may not
touch non-English text. A violation triggers one retry, then a deterministic fallback.

## Why not LangGraph
Stages are fixed and must be resumable and deterministic for a stranger's clean clone. A small
asyncio state machine with a content-hash cache gives resumability and fewer moving parts. Agentic
behaviour lives where judgment is needed: reading-order adjudication, quality-triggered re-OCR,
verified-or-retry speech, glossary building, and honest degradation reporting.

## Tricky inputs
Two-column pages and boxed notes: XY-cut + LLM adjudication. Doubtful OCR: flagged, re-OCRed at 2x,
withheld from translation if still bad. Tables/equations/figures: never translated as prose;
equations are copied, tables translated cell-by-cell, narration goes through English then Indic-Translate.
Cross-page paragraphs/tables: deterministic joiner. Running headers/footers: repetition in the edge band
on >=40% of pages (no site-specific rules). Indian-language source: English pivot built once, with round-trip scoring.

## Optional: case memory (retrieval-augmented, training-free)
`--case-memory` stores verifier-approved, non-trivial layout decisions (structure only, never page text)
and retrieves similar ones as few-shot hints for later pages. It is an inference-time analogue of
retrieval-augmented reinforcement fine-tuning: the verifier is the reward, retrieval supplies analogous solved
cases, but no weights are updated. Treat it as an ablation, off by default.

## Cost
Hosted prices: OCR 0.20/image, Translate 0.20 per 10K output tokens, Speak 6.00 per 10K chars,
Transcribe 0.10/min. Speak dominates; caching prevents any repeated spend. See `report.json -> usage`.
