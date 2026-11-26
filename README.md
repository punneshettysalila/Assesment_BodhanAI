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

## OUTPUT(when run locally)
<img width="1920" height="1020" alt="Screenshot 2026-11-27 010837" src="https://github.com/user-attachments/assets/ffa7f4ba-689b-4f6b-9e55-43e4a56d550a" />
<img width="1845" height="867" alt="Screenshot 2026-11-27 010856" src="https://github.com/user-attachments/assets/46a80cbb-9d64-45af-a3ed-97dcaf52ab65" />
<img width="1713" height="815" alt="Screenshot 2026-11-27 010912" src="https://github.com/user-attachments/assets/f6fc41c5-0ef4-424f-a2ff-d3736bb470eb" />
<img width="1712" height="862" alt="Screenshot 2026-11-27 010934" src="https://github.com/user-attachments/assets/1cad33ef-cfa8-4447-bc09-43ccccddc33b" />

## Existing processing pipeline

The Python CLI and its architecture, setup, and verification details are in [`bodhan-narrated-lesson/README.md`](bodhan-narrated-lesson/README.md). The web reader presents completed outputs; it does not replace or invoke that pipeline.
