"""Lecture video and transcript ingestion.

Three entry points, all producing the same list of timed segments:

* ``transcribe_media``: local speech-to-text with faster-whisper on CPU (video or audio files).
* ``parse_caption_file``: an existing .srt / .vtt caption file.
* ``fetch_youtube_transcript``: captions published on YouTube (no video download).

Segments are then grouped into ~60 second windows (``window_segments``) so every knowledge
unit carries a start/end timestamp that the UI can seek to.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

from ..config import settings


@dataclass
class Segment:
    start: float
    end: float
    text: str


def _file_fingerprint(path: Path) -> str:
    h = hashlib.sha1()
    size = path.stat().st_size
    h.update(str(size).encode())
    with path.open("rb") as f:
        h.update(f.read(1 << 20))
        if size > (2 << 20):
            f.seek(-(1 << 20), 2)
            h.update(f.read(1 << 20))
    return h.hexdigest()[:16]


def transcribe_media(
    path: Path,
    model_size: str | None = None,
    progress: Callable[[float, str], None] | None = None,
) -> tuple[list[Segment], dict]:
    """Transcribe a video/audio file with faster-whisper (CPU, int8). Results are cached on disk."""
    model_size = model_size or settings.whisper_model
    cache_dir = settings.cache_dir / "transcripts"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{_file_fingerprint(path)}_{model_size}.json"
    if cache_file.exists():
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        if progress:
            progress(1.0, "Loaded cached transcript")
        return [Segment(**s) for s in data["segments"]], data["meta"]

    from faster_whisper import WhisperModel  # heavy import, only when needed

    if progress:
        progress(0.02, f"Loading Whisper '{model_size}' (CPU, int8)")
    t0 = time.perf_counter()
    model = WhisperModel(model_size, device=settings.whisper_device, compute_type="int8")
    seg_iter, info = model.transcribe(
        str(path), language="en", vad_filter=True, beam_size=1, condition_on_previous_text=False
    )
    duration = float(info.duration or 0.0)
    segments: list[Segment] = []
    for s in seg_iter:
        segments.append(Segment(float(s.start), float(s.end), s.text.strip()))
        if progress and duration:
            progress(min(0.98, s.end / duration), f"Transcribed {int(s.end)//60}:{int(s.end)%60:02d} of {int(duration)//60}:{int(duration)%60:02d}")
    meta = {
        "engine": "faster-whisper",
        "model": model_size,
        "language": info.language,
        "duration_s": round(duration, 1),
        "wall_time_s": round(time.perf_counter() - t0, 1),
    }
    cache_file.write_text(
        json.dumps({"meta": meta, "segments": [asdict(s) for s in segments]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return segments, meta


_TS = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")


def _ts_to_s(ts: str) -> float:
    m = _TS.search(ts)
    if not m:
        raise ValueError(f"bad timestamp {ts!r}")
    h, mi, s, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def parse_caption_file(path: Path) -> list[Segment]:
    """Parse SRT or WebVTT captions into segments."""
    raw = path.read_text(encoding="utf-8", errors="replace").replace("\r", "")
    blocks = re.split(r"\n\s*\n", raw)
    out: list[Segment] = []
    for b in blocks:
        lines = [ln.strip() for ln in b.strip().split("\n") if ln.strip()]
        arrow = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if arrow is None:
            continue
        a, b2 = lines[arrow].split("-->")
        text = " ".join(lines[arrow + 1 :])
        text = re.sub(r"<[^>]+>", "", text).strip()
        if text:
            out.append(Segment(_ts_to_s(a), _ts_to_s(b2), text))
    return out


_YT_ID = re.compile(r"(?:v=|youtu\.be/|embed/|shorts/)([A-Za-z0-9_-]{11})")


def youtube_id(url: str) -> str | None:
    m = _YT_ID.search(url)
    if m:
        return m.group(1)
    return url if re.fullmatch(r"[A-Za-z0-9_-]{11}", url) else None


def fetch_youtube_transcript(video_id: str) -> list[Segment]:
    """Fetch published captions for a YouTube video (no media download)."""
    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi()
    fetched = api.fetch(video_id, languages=["en", "en-US", "en-GB", "hi"])
    return [Segment(float(s.start), float(s.start + s.duration), s.text.replace("\n", " ")) for s in fetched]


def window_segments(segments: Iterable[Segment], target_s: float = 60.0, max_s: float = 90.0) -> list[Segment]:
    """Group short caption segments into ~1 minute windows that end on sentence boundaries."""
    windows: list[Segment] = []
    cur: list[Segment] = []
    for s in segments:
        cur.append(s)
        span = cur[-1].end - cur[0].start
        ends_sentence = bool(re.search(r"[.?!][\"')\]]?$", s.text.strip()))
        if (span >= target_s and ends_sentence) or span >= max_s:
            windows.append(Segment(cur[0].start, cur[-1].end, " ".join(x.text for x in cur).strip()))
            cur = []
    if cur:
        windows.append(Segment(cur[0].start, cur[-1].end, " ".join(x.text for x in cur).strip()))
    return windows


def fmt_ts(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
