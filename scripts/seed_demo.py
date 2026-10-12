"""Build the demo knowledge base from the openly licensed course material in data/demo.

    python scripts/seed_demo.py            # ingest everything, build topic map + question bank
    python scripts/seed_demo.py --fresh    # wipe data/workspace first
    python scripts/seed_demo.py --no-bank  # skip question generation

Works offline too (STUDYTWIN_OFFLINE=1): headings-based topics and template questions.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studytwin import assessment, llm, store, topics  # noqa: E402
from studytwin.config import settings  # noqa: E402
from studytwin.ingest.pipeline import ingest_source  # noqa: E402

DEMO = ROOT / "data" / "demo"
RAW = ROOT / "data" / "raw"
OCW_ATTR = ("MIT OpenCourseWare, 6.041 Probabilistic Systems Analysis and Applied Probability, Fall 2010, "
            "John Tsitsiklis. https://ocw.mit.edu")
SOURCES = [
    dict(path=DEMO / "openstax_introstats_ch3_probability_topics.pdf", kind="textbook",
         title="Introductory Statistics (OpenStax), Ch. 3 Probability Topics", short_title="OpenStax Ch.3",
         page_offset=174, license="CC BY 4.0",
         attribution="Illowsky & Dean, Introductory Statistics, OpenStax. https://openstax.org/details/books/introductory-statistics"),
    dict(path=DEMO / "MIT6_041F10_L01.pdf", kind="slides", title="MIT 6.041 Lecture 1 slides: Probability models and axioms",
         short_title="6.041 L1 slides", license="CC BY-NC-SA", attribution=OCW_ATTR),
    dict(path=DEMO / "MIT6_041F10_L02.pdf", kind="slides", title="MIT 6.041 Lecture 2 slides: Conditioning and Bayes' rule",
         short_title="6.041 L2 slides", license="CC BY-NC-SA", attribution=OCW_ATTR),
    dict(path=DEMO / "MIT6_041F10_L03.pdf", kind="slides", title="MIT 6.041 Lecture 3 slides: Independence",
         short_title="6.041 L3 slides", license="CC BY-NC-SA", attribution=OCW_ATTR),
]
VIDEO = RAW / "MIT6_041F11_lec02_300k.mp4"
VIDEO_URL = "https://archive.org/download/MIT6.041F10/MIT6_041F11_lec02_300k.mp4"
CAPTIONS = DEMO / "MIT6_041F11_lec02_300k.srt"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main(argv: list[str]) -> None:
    if "--fresh" in argv and settings.workspace.exists():
        keep = settings.cache_dir  # keep transcripts + LLM cache
        for p in settings.workspace.iterdir():
            if p != keep:
                shutil.rmtree(p) if p.is_dir() else p.unlink()
        store.reset_connections()
    settings.ensure_dirs()
    log(f"LLM: {'Nebius Token Factory' if llm.available() else 'OFFLINE fallback'} | embedder: {settings.embedder}")
    if store.one("SELECT id FROM sources LIMIT 1"):
        log("Workspace already has sources; use --fresh to rebuild.")
    else:
        for spec in SOURCES:
            t0 = time.time()
            sid = ingest_source(**spec, progress=lambda f, m: None)
            n = store.one("SELECT COUNT(*) n FROM units WHERE source_id=?", (sid,))["n"]
            log(f"ingested {spec['short_title']}: {n} units in {time.time() - t0:.1f}s")
        t0 = time.time()
        if VIDEO.exists() and "--captions" not in argv:
            sid = ingest_source(VIDEO, title="MIT 6.041 Lecture 2 video: Conditioning and Bayes' rule", short_title="6.041 Lecture 2",
                                license="CC BY-NC-SA", attribution=OCW_ATTR, remote_url=VIDEO_URL, copy_file=False,
                                progress=lambda f, m: None)
        else:
            sid = ingest_source(CAPTIONS, title="MIT 6.041 Lecture 2 video: Conditioning and Bayes' rule", short_title="6.041 Lecture 2",
                                license="CC BY-NC-SA", attribution=OCW_ATTR, remote_url=VIDEO_URL, progress=lambda f, m: None)
        n = store.one("SELECT COUNT(*) n FROM units WHERE source_id=?", (sid,))["n"]
        log(f"ingested lecture video: {n} units in {time.time() - t0:.1f}s")
    if not topics.has_topics() or "--topics" in argv:
        t0 = time.time()
        stats = topics.build_topics()
        log(f"topic map: {json.dumps(stats)} in {time.time() - t0:.1f}s")
    for t in topics.topic_tree():
        log(f"  {t['id']} {t['name']} <- {t['prerequisites']} | coverage {t['coverage']}")
    if "--no-bank" not in argv:
        have = store.one("SELECT COUNT(*) n FROM questions WHERE verified=1")["n"]
        if have < 10 or "--bank" in argv:
            t0 = time.time()
            res = assessment.generate_bank(per_topic=int(settings_per_topic(argv)),
                                           progress=lambda t, s: log(f"  bank {t}: {s}"))
            log(f"question bank done in {time.time() - t0:.1f}s: {json.dumps(res)}")
    q = store.one("SELECT COUNT(*) n, SUM(verified) v FROM questions")
    log(f"questions: {q['n']} generated, {q['v']} verified")
    log(f"LLM usage: {json.dumps(llm.meter.snapshot())}")


def settings_per_topic(argv: list[str]) -> int:
    for a in argv:
        if a.startswith("--per-topic="):
            return int(a.split("=", 1)[1])
    return 8


if __name__ == "__main__":
    main(sys.argv[1:])
