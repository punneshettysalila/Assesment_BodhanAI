# Bodhan Narrated Lesson - Application Report

**Report type:** Technical architecture and implementation summary  
**Application:** Scanned textbook chapter to translated, narrated lesson  
**Package:** `bodhan-lesson` (`bodhan_lesson`)  
**Model policy:** Bodhan models for OCR, translation, speech synthesis and transcription; only a fenced LLM may assist layout and English narration decisions

---

## 1. Executive summary

Bodhan Narrated Lesson converts PDF or page-image input into:

- A clean source lesson in Markdown.
- One translated Markdown lesson per target language.
- Section MP3/WAV audio and a full lesson MP3.
- Chapter metadata and JSON narration records.
- `report.json` and `report.html` containing status, timings, QA metrics, warnings and estimated cost.

The implementation is primarily an asynchronous pipeline. It uses deterministic rendering, validation and joining before and after model calls. An external LLM is optional and is constrained to English/ID-only decisions. Indian-language text is generated through Indic-Translate or copied source text; the LLM is not allowed to rewrite it.

Automated tests use fake models and do not prove live Bodhan output quality. The published API request formats are used; a bounded live run is still needed for service validation.

---

## 2. Purpose and scope

### 2.1 User problem

Scanned textbook chapters often have:

- Headers and footers repeated on every page.
- Multiple columns.
- Cross-page paragraphs and tables.
- Equations and numbers.
- Poor scan quality.
- Garbled OCR.
- No accessible narration.

### 2.2 Intended users

- Teachers producing multilingual lessons.
- Students using text and audio study material.
- Reviewers auditing model calls, costs and quality.
- Developers running offline demonstrations or live Bodhan jobs.

### 2.3 Supported inputs

- PDF files.
- Folders or lists of page images.
- Source text in English or an Indian language.

### 2.4 Supported target flow

The CLI accepts comma-separated language codes, for example `hi,ta,bn`. Translation and narration isolate failures per language.

---

## 3. Application architecture

```mermaid
flowchart LR
  A[PDF or page images] --> B[Render and assess input]
  B --> C[Indic-OCR]
  C --> D[Typed OCR blocks and doubt flags]
  D --> E[Remove repeated chrome]
  E --> F[Reading-order repair]
  F --> G[Cross-page join and section assembly]
  G --> H[Source lesson and page evidence]
  H --> I[English pivot]
  I --> J[English glossary and translation]
  J --> K[Indic Markdown]
  K --> L[Section narration planning]
  L --> M[Indic-Speak]
  M --> N[Indic-Transcribe and CER check]
  N --> O[Retry or degrade honestly]
  O --> P[MP3, chapters and reports]
```

### 3.1 Core stages

| Stage | Responsibility |
|---|---|
| Ingest | Render PDF/images, assess blur/skew/contrast and prepare page images |
| OCR | Call Indic-OCR, parse output blocks and score OCR doubt |
| Layout | Remove running headers/footers, determine reading order and join page content |
| Pivot | Build an English pivot once for cross-language reuse |
| Translation | Translate blocks while masking numbers, LaTeX and tables |
| Glossary | Extract terminology and preserve it consistently |
| Narration | Convert text, tables, equations and figures into English narration plans |
| Speech | Generate WAV chunks and verify them with transcription |
| Assembly | Merge section audio, create chapters and MP3 files |
| Reporting | Record state, metrics, warnings, timings and costs |

---

## 4. Detailed pipeline

### 4.1 Ingest

The ingest package:

- Resolves PDF or image input.
- Renders PDF pages to page images.
- Measures blur, skew and contrast.
- Produces a page image path and page quality metadata.
- Optionally deskews poor pages.

The input is represented in a `Page` model with page number, image path, quality values and OCR blocks.

### 4.2 OCR

OCR is handled by `Bodhan.ocr()`. Page output is parsed into typed `Block` objects:

- Heading
- Paragraph
- List
- Table
- Equation
- Figure
- Caption
- Header/footer/page number
- Handwritten
- Other

Each block tracks:

- Stable block ID.
- Page number.
- Text.
- Normalised bounding box.
- Confidence.
- Flags.
- Reading-order position.
- Text hash for mutation protection.

OCR doubt is configured by:

- Minimum confidence.
- Garbled-symbol ratio.
- Retry fraction.
- High-scale recrop scale.
- Maximum recrop count.

Where enough blocks are doubtful, the page may be recropped and OCR run again at 2x scale. Doubtful blocks that remain are withheld rather than translated or narrated confidently.

### 4.3 Layout

Layout processing has four parts:

1. Remove repeated edge text as running chrome.
2. Calculate XY-cut reading order from bounding boxes.
3. Compare XY-cut with Indic-OCR order.
4. Use an optional LLM only when the orders disagree.

An OCR page needs at least two blocks and valid bounding boxes for meaningful reading-order analysis. If no LLM is configured, XY-cut is used. If the LLM rejects or fails validation, the system falls back to XY-cut.

The LLM receives block IDs and snippets and must return a pure permutation plus block flags. Validators ensure:

- Every ID appears exactly once.
- No text was changed.
- Text hashes remain intact.
- Validation flags are from the allowed set.

The layout decision is written into `source/pages/page-*.json`.

### 4.4 Cross-page assembly

The joiner:

- Combines paragraphs across page breaks.
- Handles split sentences.
- Removes repeated table headers.
- Preserves headings, tables and equations.
- Builds the lesson sections.

The source Markdown includes block trace comments, allowing generated content to be traced back to source blocks.

### 4.5 Translation and pivot

For Indian-language sources, the pipeline can build an English pivot once and reuse it across target languages. For English sources, the blocks are used directly.

Translation protections include:

- Number masking and checking.
- LaTeX masking and verbatim preservation.
- Table structure preservation.
- Placeholder locking.
- Per-chapter glossary locking.
- Translation round-trip checks for weak pivots.

Numbers and LaTeX are checked rather than relying on generated text alone.

### 4.6 Narration planning

Narration is planned by block type:

- Paragraph text becomes speech prose.
- Headings become spoken headings.
- Lists are verbalised.
- Equations use deterministic LaTeX-to-speech conversion.
- Tables are verbalised with guards.
- Figures receive guarded descriptions.
- Captions follow their figure or table context.

The LLM can assist table/figure descriptions, but narration ultimately passes through translation and speech safeguards.

### 4.7 Speech synthesis and verification

The narration is split into chunks with a configurable character limit, default 220 characters. Each chunk is synthesised with Indic-Speak, then transcribed with Indic-Transcribe.

Verification uses:

- Character Error Rate (CER).
- Repeat/insertions detection.
- Omission/deletion detection.
- Chunk duration sanity.
- Retry ladder.

Default retry stages:

1. Synthesise as-is.
2. Simplify punctuation.
3. Split text and concatenate chunks.

Speech is shipped only with honest status and metrics. Degraded or failed chunks are not silently reported as successful.

### 4.8 Audio assembly

Section WAVs are concatenated and optionally converted to MP3 with ffmpeg. Audio is loudness-normalised to approximately `-16 LUFS`, with a tolerance of `1 LUFS`.

A full lesson is also assembled with:

- Chapter metadata.
- Per-section timing.
- Full-duration MP3.
- Chapter JSON/FFmpeg metadata.

If ffmpeg is unavailable, WAV output remains possible.

---

## 5. External integrations

### 5.1 Bodhan model facade

`src/bodhan_lesson/clients/bodhan.py` exposes one façade:

- `ocr()`
- `translate()`
- `speak()`
- `transcribe()`
- `stats`
- `aclose()`

Routes and model IDs come from `configs/endpoints.yaml`. The values currently include:

| Model role | Route | Model |
|---|---|---|
| OCR | `/v1/chat/completions` | `indic-ocr` |
| Translation | `/translate` | `indic-translate` |
| Speech | `/v1/audio/speech` | `indic-speak` |
| Transcription | `/v1/audio/transcriptions` | `indic-transcribe` |

The endpoint file follows the published Bodhan API reference. Service behavior and real output quality still require a bounded live run.

### 5.2 Optional LLM

The optional LLM is configured with:

- `LLM_BASE_URL`
- `LLM_MODEL`
- `LLM_API_KEY`

It is used for four tightly fenced decisions:

- Reading-order adjudication.
- Glossary term extraction.
- Table verbalisation.
- Figure description.

It is not used for the translation engine or direct Indian-language prose generation.

---

## 6. Configuration

### 6.1 Bodhan secrets

Keys are loaded from environment variables or an ignored `.env` file:

| Variable | Purpose |
|---|---|
| `BODHAN_BASE_URL` | Bodhan API base URL |
| `BODHAN_OCR_KEY` | OCR key |
| `BODHAN_TRANSLATE_KEY` | Translation key |
| `BODHAN_SPEAK_KEY` | Speech key |
| `BODHAN_TRANSCRIBE_KEY` | Transcription key |

No secret is written into report files or source control.

### 6.2 Threshold configuration

`configs/thresholds.yaml` controls OCR, layout and speech thresholds:

- OCR confidence and garbage ratio.
- OCR retry fraction and recrop scale.
- Repeated chrome fraction.
- CER threshold.
- Retry count.
- Repeat/omission ratios.
- Chunk duration limits.
- Maximum Transcribe audio duration.
- Loudness target and tolerance.

### 6.3 Endpoint configuration

`configs/endpoints.yaml` controls routes, model IDs and prompt templates.

### 6.4 Voices and glossary

Optional configuration examples are present for:

- Voices per language.
- User-approved glossary terms.

---

## 7. Command-line interface

Primary invocation:

```powershell
python -m bodhan_lesson --input <PDF_OR_FOLDER> --langs hi,ta,bn --out <OUT_DIR>
```

### 7.1 Important options

| Option | Purpose |
|---|---|
| `--input` | PDF or folder of page images |
| `--out` | Output directory |
| `--langs` | Comma-separated target language codes |
| `--source-lang` | Optional source-language hint |
| `--voices PATH` | YAML mapping language codes to Bodhan voice names |
| `--glossary` | Human glossary YAML |
| `--code-mixed` | Keep English technical terms |
| `--max-chars` | Maximum TTS chunk size |
| `--no-audio` | Stop after translated Markdown |
| `--no-verify` | Skip audio back-transcription |
| `--case-memory` | Reuse verified layout decisions |
| `--max-cost-inr FLOAT` | Stop remaining section synthesis after the accumulated cost reaches the budget |
| `--env-file` | Environment file path |
| `--verbose` | Verbose logging |

### 7.2 Exit codes

| Code | Meaning |
|---|---|
| `0` | Languages produced output; partial issues may remain |
| `1` | At least one language failed |
| `2` | Fatal input/configuration failure |

---

## 8. Cost control

The reporting model uses:

| Model | Rate |
|---|---|
| OCR | 0.20 INR per image |
| Translation | 0.20 INR per 10,000 output tokens |
| Speech | 6.00 INR per 10,000 input characters |
| Transcription | 0.10 INR per audio minute |

The `--max-cost-inr` flag checks accumulated `bodhan.stats` cost before synthesising each section. Reaching the budget:

- Stops audio for remaining sections.
- Keeps completed sections and translated Markdown.
- Adds a report warning.
- Marks the language as partial.

The cache is designed to reuse OCR and translation results across reruns, so live work should use cache/resume and `--no-audio` during iteration.

---

## 9. Cache and case memory

### 9.1 Disk cache

`DiskCache` stores content-addressed model results under the output `.cache` directory. It is shared by OCR and translation paths.

This:

- Reuses identical page OCR.
- Reuses repeated translations.
- Supports resumed/rerun jobs.
- Prevents accidental repeated paid calls.

### 9.2 Case memory

Verified, nontrivial LLM layout decisions can be recorded as structure-only few-shot examples. Page text is not stored in these cases.

The ablation tool runs without and with `--case-memory`, copying the first run's cache before the second run so paid calls are not repeated.

Identity decisions and unverified fallback decisions are not eligible for case-memory reuse.

---

## 10. Report artifacts

### 10.1 Per-run JSON

`report.json` contains:

- Input and source metadata.
- Language statuses.
- Page and block information.
- Sections and audio paths.
- Skipped/flagged blocks.
- Translation issues.
- Glossary data.
- Warnings.
- Per-stage timings.
- Per-model usage/cost.
- Cache hits/misses.
- Total runtime.
- Quality-target values.

### 10.2 HTML report

`report.html` renders the JSON report for human review.

### 10.3 Typical output tree

```text
out/<run>/
  report.json
  report.html
  .cache/
  work/
  source/
    pages/
      page-001.json
    lesson.src.md
    lesson.en.md (pivot when source is Indic)
    flagged.json
  hi/
    lesson.hi.md
    narration_script.<lang>.json
    narration/
    chapters.hi.json
    lesson.hi.mp3
  ta/
  bn/
```

---

## 11. Quality and guardrails

| Concern | Guard |
|---|---|
| LLM text rewriting | LLM layout responses contain block IDs only |
| LLM invalid permutations | Pure-permutation and text-hash validation |
| Indian-language LLM generation | Narration is English-first, then translated |
| Garbled OCR | Doubt scoring, re-OCR, withholding and flags |
| Running chrome | Generic repeated-edge-text rule |
| Numbers | Masking and number-set comparison |
| LaTeX | Verbatim masking and structure checks |
| Table structure | Skeleton and Markdown structure checks |
| Speech repeat/omission | Back-transcription, CER and retry ladder |
| Loudness | LUFS normalisation and report range |
| Cost | Accumulated cost budget gate |
| Model leakage | Guard tests block forbidden imports/models |
| Language isolation | Per-language tasks and failure capture |

---

## 12. Offline demonstration

`tools/offline_demo.py` runs the real pipeline with canned simulated models. It:

- Creates synthetic page scans.
- Uses no Bodhan API keys.
- Makes no network model calls.
- Produces sine-tone audio.
- Generates Markdown and report artifacts.
- Labels outputs as not real Bodhan results.

Offline run:

```powershell
python tools/offline_demo.py --out out/offline_demo
```

Offline outputs are suitable for:

- Demonstrating output structure.
- Testing orchestration.
- Capturing local screenshots.
- Developing and debugging cache/report behavior.

They are not evidence of Bodhan OCR, translation or speech quality.

---

## 13. Evidence and utility scripts

### 13.1 Probe Bodhan

`scripts/probe_bodhan.py` makes one call per configured model:

- OCR an image.
- Translate an English sentence to Hindi.
- Synthesise a short Hindi sentence.
- Transcribe the returned WAV.

It records raw responses under `out/probe/` and prints route, status, JSON keys, latency and estimated cost. It must not be run without a deliberate low-cost API test.

### 13.2 Evidence collection

`scripts/collect_evidence.py OUT_DIR [--patch-readme]`:

- Writes `OUT_DIR/evidence/summary.md`.
- Creates a depth-3 output tree.
- Builds a language result table.
- Adds total cost and runtime.
- Optionally replaces README result rows between result markers.

### 13.3 Case-memory ablation

`scripts/ablate_case_memory.py --input DIR --lang CODE --out OUT`:

- Runs CLI twice with `--no-audio`.
- Runs once without case memory.
- Copies the first `.cache` into the second run.
- Counts layout methods.
- Counts LLM calls.
- Writes `OUT/ablation.md`.
- Makes no claim of improvement.

### 13.4 Live walkthrough notebook

`walkthrough.ipynb` has at most 12 cells and demonstrates:

- Pipeline explanation.
- Offline demo launch.
- `report.json` as a table.
- A translated lesson.
- IPython audio playback.
- Page 1 layout decision.

It runs with no API keys.

---

## 14. Testing

The test suite has unit, guard and end-to-end coverage.

| Layer | Coverage |
|---|---|
| Guard | Prevents forbidden/non-Bodhan model imports |
| Unit | Client retries/errors, layout parsing/validators, translation checks, speech/CER/audio |
| End to end | Full fake two-language run, language isolation, cache reuse, no-audio withholding, CLI exit codes, case memory |

Primary command:

```powershell
pytest -q
```

Verified result:

```text
51 passed
```

The test suite uses `FakeBodhan`/simulated implementations. It does not perform paid API calls.

---

## 15. Security and privacy

- Bodhan keys remain in environment variables or `.env`.
- `.env` must remain ignored by Git.
- Generated page images and OCR text may contain confidential teaching material.
- External LLM endpoints receive only layout snippets and English narration decisions unless the user's own configuration routes additional data.
- Report files should be reviewed for page text before publishing.
- No API secrets belong in Markdown, screenshots or source.

---

## 16. Reliability behavior

### 16.1 Partial output

A language may finish as `partial` when:

- Some blocks were withheld.
- Some chunks failed or were degraded.
- The cost budget stopped remaining audio.
- Translation or structure checks reported issues.

Partial does not mean a language run failed entirely.

### 16.2 Failure isolation

If one language fails, other languages continue. The report and exit code identify isolated failures.

### 16.3 Fatal errors

Fatal input/configuration errors return exit code 2 and produce a report warning when possible.

---

## 17. Known limitations and assumptions

1. Live service behavior and output quality still require a bounded run with Bodhan credentials.
2. Bounding-box support has not been confirmed from live Indic-OCR.
3. Live TTS voice names, language fields and chunk limits have not been confirmed.
4. Live translation request shape and usage-token reporting have not been confirmed.
5. Offline demo quality is not representative of real Bodhan quality.
6. Layout repair is dependent on accurate OCR bounding boxes.
7. ffmpeg is required for MP3 and loudness-normalised full audio; otherwise WAV is used.
8. A live English/Indic source test is still required.
9. This application does not create a separate authenticated web interface.
10. API service availability, latency and quotas remain external dependencies.

---

## 18. Operational runbook

### 18.1 Safe local run

```powershell
python tools/offline_demo.py --out out/offline_demo
python scripts/collect_evidence.py out/offline_demo --patch-readme
python -m jupyter lab walkthrough.ipynb
pytest -q
```

### 18.2 Low-cost/live validation

```powershell
python scripts/probe_bodhan.py --image <PAGE_IMAGE>
```

Confirm endpoints and credentials first. The probe makes paid API calls.

### 18.3 Live pipeline

```powershell
python -m bodhan_lesson --input <PDF_OR_FOLDER> --langs hi,ta,bn --out out/live --env-file .env --max-cost-inr <BUDGET>
```

### 18.4 Evidence report

```powershell
python scripts/collect_evidence.py out/live --patch-readme
```

---

## 19. Final technical assessment

The application is structurally complete:

- The core pipeline is implemented end to end.
- Bodhan model boundaries are isolated behind one client façade.
- The LLM is constrained and optional.
- Paid calls are cached.
- Per-language failures are isolated.
- Audio and translation include verification and honest degradation.
- Report and evidence utilities are present.
- An offline demonstration requires no keys or network model calls.
- Automated tests pass with simulated models.

The remaining unverified work is live quality measurement on real textbook scans, using the supplied Bodhan credentials. Synthetic outputs do not establish model accuracy or runtime.
