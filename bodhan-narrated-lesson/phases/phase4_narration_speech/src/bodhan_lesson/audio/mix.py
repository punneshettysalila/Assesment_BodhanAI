"""WAV assembly, EBU R128 loudness normalisation (two-pass ffmpeg), MP3 export, chapter markers."""
from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import wave
from pathlib import Path


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def wav_info(data: bytes) -> tuple[tuple[int, int, int], float]:
    with wave.open(io.BytesIO(data)) as w:
        return (w.getnchannels(), w.getsampwidth(), w.getframerate()), w.getnframes() / w.getframerate()


def silence(params: tuple[int, int, int], seconds: float) -> bytes:
    ch, sw, sr = params
    return b"\x00" * (int(sr * seconds) * ch * sw)


def concat_wavs(wavs: list[bytes], gap_s: float = 0.3) -> bytes:
    if not wavs:
        raise ValueError("nothing to concatenate")
    params = wav_info(wavs[0])[0]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(params[0]); out.setsampwidth(params[1]); out.setframerate(params[2])
        for i, w in enumerate(wavs):
            if wav_info(w)[0] != params:
                raise ValueError("WAV parameters differ between chunks")
            with wave.open(io.BytesIO(w)) as r:
                out.writeframes(r.readframes(r.getnframes()))
            if i < len(wavs) - 1 and gap_s > 0:
                out.writeframes(silence(params, gap_s))
    return buf.getvalue()


def split_wav(data: bytes, max_s: float) -> list[bytes]:
    """Slice a WAV into <= max_s pieces (Indic-Transcribe accepts short clips only)."""
    params, dur = wav_info(data)
    if dur <= max_s:
        return [data]
    ch, sw, sr = params
    with wave.open(io.BytesIO(data)) as r:
        frames = r.readframes(r.getnframes())
    step = int(max_s * sr) * ch * sw
    pieces = []
    for i in range(0, len(frames), step):
        b = io.BytesIO()
        with wave.open(b, "wb") as o:
            o.setnchannels(ch); o.setsampwidth(sw); o.setframerate(sr)
            o.writeframes(frames[i:i + step])
        pieces.append(b.getvalue())
    return pieces


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def measure_lufs(path: Path) -> float | None:
    r = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af",
              "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    return float(json.loads(m.group(0))["input_i"]) if m else None


def normalise(src_wav: Path, dst: Path, target: float = -16.0, bitrate: str = "128k",
              metadata: dict[str, str] | None = None, chapters_file: Path | None = None) -> float | None:
    """Two-pass loudnorm to `target` LUFS; writes MP3 (or WAV if dst suffix is .wav). Returns measured LUFS."""
    r1 = _run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src_wav), "-af",
               f"loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r1.stderr, re.S)
    af = f"loudnorm=I={target}:TP=-1.5:LRA=11"
    if m:
        s = json.loads(m.group(0))
        if s.get("input_i") not in ("-inf", None):
            af += (f":measured_I={s['input_i']}:measured_TP={s['input_tp']}:measured_LRA={s['input_lra']}"
                   f":measured_thresh={s['input_thresh']}:offset={s['target_offset']}:linear=true")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src_wav)]
    if chapters_file:
        cmd += ["-i", str(chapters_file), "-map_metadata", "1", "-map_chapters", "1"]
    cmd += ["-af", af, "-ar", "24000"]
    if dst.suffix == ".mp3":
        cmd += ["-codec:a", "libmp3lame", "-b:a", bitrate]
    for k, v in (metadata or {}).items():
        cmd += ["-metadata", f"{k}={v}"]
    cmd.append(str(dst))
    r = _run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr[-300:]}")
    return measure_lufs(dst)


def write_chapters(sections: list[tuple[str, float]], meta_path: Path, json_path: Path) -> list[dict]:
    """sections = [(title, duration_s)] -> ffmetadata chapters + JSON for the HTML/ report."""
    chapters, t = [], 0.0
    lines = [";FFMETADATA1"]
    for title, dur in sections:
        start, end = int(t * 1000), int((t + dur) * 1000)
        chapters.append({"title": title, "start_s": round(t, 3), "end_s": round(t + dur, 3)})
        safe = title.replace("=", "-").replace(";", ",").replace("#", "").replace("\\", "")
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={start}", f"END={end}", f"title={safe}"]
        t += dur
    meta_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(chapters, ensure_ascii=False, indent=2), encoding="utf-8")
    return chapters
