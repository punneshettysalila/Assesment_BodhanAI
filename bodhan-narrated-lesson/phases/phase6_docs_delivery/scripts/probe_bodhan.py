from __future__ import annotations

import argparse
import base64
import io
import os
import sys
import wave
from pathlib import Path

import httpx
import yaml


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def valid_wav(data: bytes) -> bool:
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            return w.getnframes() > 0 and w.getframerate() > 0
    except Exception:
        return False


def base_url() -> str:
    return os.environ.get("BODHAN_BASE_URL", "").rstrip("/")


def print_result(route: str, status: int | None, body: bytes, latency: float,
                 ocr: bool = False, spoken: bool = False, content_type: str = "") -> None:
    text = body[:200].decode("utf-8", "replace")
    keys = ""
    if not spoken:
        try:
            import json
            js = json.loads(body)
            if isinstance(js, dict):
                keys = ", ".join(js.keys())
            else:
                keys = f"<{type(js).__name__}>"
        except Exception:
            keys = "<non-json>"
    print(f"{route} | status={status} | keys=[{keys}] | first200={text!r} | latency={latency:.3f}s")
    if ocr:
        try:
            import json
            js = json.loads(body)
            bbox = any("bbox" in str(k).lower() or "box" in str(k).lower() for k in js.keys()) if isinstance(js, dict) else False
        except Exception:
            bbox = False
        print(f"  OCR box-like field: {bbox}")
    if spoken:
        print(f"  content-type={content_type or '-'} | valid WAV={valid_wav(body)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True, type=Path)
    ap.add_argument("--env-file", type=Path, default=Path(".env"))
    args = ap.parse_args()
    load_env(args.env_file)
    root = Path(__file__).resolve().parents[1]
    eps = yaml.safe_load((root / "configs" / "endpoints.yaml").read_text(encoding="utf-8"))
    base = base_url()
    if not base:
        print("BODHAN_BASE_URL is not set", file=sys.stderr)
        return 2
    out = root / "out" / "probe"
    out.mkdir(parents=True, exist_ok=True)
    headers = lambda name: {"Authorization": f"Bearer {os.environ.get('BODHAN_' + name.upper() + '_KEY', '')}",
                            "Content-Type": "application/json"}
    table = []
    cost = 0.0
    with httpx.Client(timeout=120.0) as client:
        e = eps["ocr"]
        image = args.image.read_bytes()
        mime = "image/png" if args.image.suffix.lower() == ".png" else "image/jpeg"
        body = {"model": e["model"], "temperature": 0,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": "data:" + mime + ";base64," + base64.b64encode(image).decode()}},
                    {"type": "text", "text": e["prompt"]}]}]}
        r = client.post(base + e["path"], headers=headers("OCR"), json=body)
        (out / "ocr.json").write_bytes(r.content)
        print_result(e["path"], r.status_code, r.content, r.elapsed.total_seconds(), ocr=True)
        if r.status_code >= 300:
            print(r.text)
        table.append((e["path"], r.status_code, "OCR"))
        cost += 0.20

        e = eps["translate"]
        prompt = e["prompt"].format(src="English", tgt="Hindi",
                                    text="The sum of the angles is 180 degrees.")
        body = {"model": e["model"], "temperature": 0,
                "messages": [{"role": "user", "content": prompt}]}
        r = client.post(base + e["path"], headers=headers("TRANSLATE"), json=body)
        (out / "translate.json").write_bytes(r.content)
        print_result(e["path"], r.status_code, r.content, r.elapsed.total_seconds())
        if r.status_code >= 300:
            print(r.text)
        table.append((e["path"], r.status_code, "Translate"))

        e = eps["speak"]
        sentence = "कोणों का योग 180 है।"
        body = {"model": e["model"], "input": sentence, "language": "hi",
                "response_format": e.get("response_format", "wav")}
        r = client.post(base + e["path"], headers=headers("SPEAK"), json=body)
        (out / "speak.wav").write_bytes(r.content)
        print_result(e["path"], r.status_code, r.content, r.elapsed.total_seconds(),
                     spoken=True, content_type=r.headers.get("content-type", ""))
        if r.status_code >= 300:
            print(r.text)
        table.append((e["path"], r.status_code, "Speak"))
        cost += 6.0 * len(sentence) / 10000

        if r.status_code < 300:
            e = eps["transcribe"]
            r2 = client.post(base + e["path"], headers={"Authorization": headers("TRANSCRIBE")["Authorization"]},
                              data={"model": e["model"], "language": "hi"},
                              files={"file": ("returned.wav", (out / "speak.wav").read_bytes(), "audio/wav")})
            (out / "transcribe.json").write_bytes(r2.content)
            print_result(e["path"], r2.status_code, r2.content, r2.elapsed.total_seconds())
            if r2.status_code >= 300:
                print(r2.text)
            table.append((e["path"], r2.status_code, "Transcribe"))
            cost += 0.10 * (wave_seconds((out / "speak.wav").read_bytes()) / 60)
        else:
            table.append((eps["transcribe"]["path"], "-", "Transcribe skipped: speak failed"))

    print("\nendpoint | status | notes")
    for route, status, notes in table:
        print(f"{route} | {status} | {notes}")
    print(f"Estimated cost: INR {cost:.4f}")
    return 0


def wave_seconds(data: bytes) -> float:
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
