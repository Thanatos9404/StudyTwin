"""Offline, deterministic test setup: no network, no API keys, hashing embedder, temp workspace."""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_TMP = Path(tempfile.mkdtemp(prefix="studytwin_test_"))
os.environ.update({
    "STUDYTWIN_OFFLINE": "1",
    "STUDYTWIN_EMBEDDER": "hash",
    "STUDYTWIN_WORKSPACE": str(_TMP / "ws"),
    "STUDYTWIN_ENV_FILE": "",
    "NEBIUS_API_KEY": "",
})
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

DEMO = ROOT / "data" / "demo"


@pytest.fixture(scope="session")
def kb():
    """Ingest the committed demo files once (offline) and build the fallback topic map + template bank."""
    from studytwin import assessment, store, topics
    from studytwin.ingest.pipeline import ingest_source

    ids = {
        "textbook": ingest_source(DEMO / "openstax_introstats_ch3_probability_topics.pdf", kind="textbook",
                                  short_title="OpenStax Ch.3", page_offset=174),
        "slides": ingest_source(DEMO / "MIT6_041F10_L02.pdf", short_title="6.041 L2 slides"),
        "video": ingest_source(DEMO / "MIT6_041F11_lec02_300k.srt", short_title="6.041 Lecture 2"),
    }
    stats = topics.build_topics()
    bank = assessment.generate_bank(per_topic=3, workers=1)
    return {"ids": ids, "topics": stats, "bank": bank, "store": store}
