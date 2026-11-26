# Bodhan Narrated Lessons

A lightweight, browser-based reader for exploring narrated lesson runs made by the Bodhan pipeline. Read translated Markdown, switch to the source lesson, listen to section audio, follow narration scripts, and inspect quality checks, model usage, timings, and estimated costs.

The included lesson is an **offline simulation**. Its translations, timings, and costs are illustrative, and its audio files are test tones rather than speech, so sample playback is disabled. To hear narration, open a completed Bodhan run with real audio. The reader itself makes no model calls and requires no API keys.

## Run locally

From the repository root:

```bash
python scripts/build_web.py
python -m http.server 8000 --directory dist
```

Open `http://localhost:8000`. To inspect your own completed run, select its output folder with **Open your run**. The browser reads the selected files locally; it does not upload them.

## Deploy

- **Git:** commit and push the repository to GitHub. The web reader has no runtime package dependencies or secrets.
- **GitHub Pages:** set the repository Pages source to **GitHub Actions**. Push to `main` or `master` to trigger `.github/workflows/deploy-pages.yml`, or start it manually with **Run workflow**.
- **Render:** in the Render dashboard, choose **New → Blueprint**, connect this GitHub repository, and apply the `render.yaml` Blueprint. Render builds the static site into `dist` and serves it without installing or running the model pipeline. Future pushes to the selected branch trigger a redeploy.

## Existing processing pipeline

The Python CLI and its architecture, setup, and verification details are in [`bodhan-narrated-lesson/README.md`](bodhan-narrated-lesson/README.md). The web reader presents completed outputs; it does not replace or invoke that pipeline.
