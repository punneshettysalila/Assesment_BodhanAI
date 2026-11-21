# Draft Pull Request Description

> Before opening the PR, add the recipe under the Cookbook `examples/` folder, run it with the assessment demo inputs, and replace every pending evidence field below with the actual output or link. Do not submit simulated outputs as Bodhan results.

## Summary

This recipe converts scanned textbook pages into a structured source lesson, translated Markdown, and section-by-section narrated audio. It uses Bodhan Indic models for OCR, translation, speech synthesis, and speech recognition, with checks and retries recorded in a machine-readable report.

## How to run

Install Python 3.12, Poppler, and ffmpeg. Run `pip install -e ".[dev]" -c requirements-tested.txt` for a pinned editable install. Copy `.env.example` to `.env` and configure the four Bodhan keys. Then run:

```bash
python -m bodhan_lesson \
  --input path/to/scans-or-chapter.pdf \
  --langs hi,ta,bn \
  --out ./out \
  --voices voices.yaml
```

## Architecture

See [`docs/architecture.md`](architecture.md). Stages: image rendering and quality checks; Bodhan OCR; block parsing and doubt scoring; header/footer removal and reading-order repair; cross-page assembly; optional English pivot; protected translation; narration planning; Bodhan speech and transcription checks; audio packaging and report generation.

## Workflow

See [`docs/workflow.md`](workflow.md) for the flow chart, retries, thresholds, and failure handling. A page can be re-OCRed when enough blocks are doubtful. Speech chunks are transcribed and retried when they miss the CER or repeat/omission checks.

## Where the LLM is used, and why

The configurable OpenAI-compatible LLM may help adjudicate ambiguous reading order, extract glossary candidates, verbalize tables, or describe a figure. Validators constrain layout output to block IDs and protect OCR text. Table narration is checked against OCR numbers; figure descriptions use the OCR-detected figure crop. Deterministic fallbacks are used when LLM output is absent or rejected. The LLM is not used for OCR, translation, TTS, ASR, or Indian-language text generation.

## How tables, equations, and figures are narrated

Tables are converted into spoken English with numeric checks, then translated with Indic-Translate. Equations are copied as LaTeX in lessons and rendered with a deterministic math-to-speech mapping. Figures are described from the OCR-detected image crop and nearby OCR context; if no safe crop or LLM is available, a generic description is used.

## Bodhan models used

| Model | Use | Configuration |
|---|---|---|
| Indic-OCR | Page text and layout | `configs/endpoints.yaml` |
| Indic-Translate | Translation and narration localization | `configs/endpoints.yaml` |
| Indic-Speak | Audio synthesis | `configs/endpoints.yaml`, `--voices` |
| Indic-Transcribe | Speech verification | `configs/endpoints.yaml` |

Hosted routes follow the [Bodhan API reference](https://console.bodhan.ai/api-docs/). No live model call has been made in this workspace.

## Results

Offline verification: **51 tests passed**. This covers faked or mocked models and does not measure Bodhan output quality.

Live demo results: **pending**. Add links to the actual NCERT run outputs and include the quality-target values from its `report.json` after processing.

## Demo video

**Pending.** Add a public link to a recording of five minutes or less showing a full live run and its outputs.

## Trade-offs and known limitations

The pipeline favors deterministic checks and explicit partial results over silently passing doubtful text. English pivoting for Indic-source material can compound translation errors, so weak round-trip blocks are flagged. Real model accuracy, runtime, and costs have not yet been measured on the demo or hidden chapters. MP3 and loudness processing depend on ffmpeg.

## Cost and runtime

Report actual per-page and per-language estimates from the live run here: **pending**. Current documented hosted rates are configured for accounting in the application; verify the report against the Bodhan console after the run.

## AI assistance

OpenAI Codex was used in this work session to inspect the repository and take-home brief, implement and adjust application code, add/update tests, and revise documentation. The applicant should review the changes and be prepared to explain the implementation in the assessment debrief.
