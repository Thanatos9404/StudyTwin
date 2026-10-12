"""Download the openly licensed demo course material into data/raw and data/demo.

Sources and licenses are documented in DATA.md. Run:  python scripts/fetch_demo_data.py
The small PDFs used by the demo are already committed in data/demo; this script is needed only
for the lecture video (118 MB) or to rebuild the textbook-chapter extract from the full book.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DEMO = ROOT / "data" / "demo"

OCW = "https://ocw.mit.edu/courses/6-041-probabilistic-systems-analysis-and-applied-probability-fall-2010"
FILES = {
    # MIT OCW 6.041 Fall 2010 (CC BY-NC-SA): lecture slides and the Lecture 2 video + captions
    "MIT6_041F10_L01.pdf": f"{OCW}/fee036e2e13527166fb7f8bcd0647844_MIT6_041F10_L01.pdf",
    "MIT6_041F10_L02.pdf": f"{OCW}/1d1520a08a59780bd49a9f0f12bf9af8_MIT6_041F10_L02.pdf",
    "MIT6_041F10_L03.pdf": f"{OCW}/b200b6217af1cd5dbea8c659ebbf046a_MIT6_041F10_L03.pdf",
    "MIT6_041F11_lec02_300k.mp4": "https://archive.org/download/MIT6.041F10/MIT6_041F11_lec02_300k.mp4",
    "MIT6_041F11_lec02_300k.srt": "https://archive.org/download/MIT6.041F10/MIT6_041F11_lec02_300k.srt",
    # Lecture 3 captions: a small file for demonstrating live upload in the Library
    "MIT6_041F11_lec03_300k.srt": "https://archive.org/download/MIT6.041F10/MIT6_041F11_lec03_300k.srt",
    # OpenStax Introductory Statistics (CC BY 4.0): full book, chapter 3 is extracted below
    "openstax_introstats_full.pdf": "https://assets.openstax.org/oscms-prodcms/media/documents/IntroductoryStatistics-OP_i6tAI7e.pdf",
}

# Chapter 3 "Probability Topics" = PDF pages 183-221 (printed pages 175-213).
CHAPTER_FIRST, CHAPTER_LAST = 183, 221


def download(name: str, url: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / name
    if out.exists() and out.stat().st_size > 0:
        print(f"ok   {name}")
        return out
    print(f"get  {name} <- {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "StudyTwin demo fetcher"})
    with urllib.request.urlopen(req, timeout=120) as r, out.open("wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    return out


def extract_chapter(full: Path) -> Path:
    from pypdf import PdfReader, PdfWriter

    out = DEMO / "openstax_introstats_ch3_probability_topics.pdf"
    if out.exists():
        print(f"ok   {out.name}")
        return out
    r = PdfReader(str(full))
    w = PdfWriter()
    for i in range(CHAPTER_FIRST - 1, CHAPTER_LAST):
        w.add_page(r.pages[i])
    w.add_metadata({
        "/Title": "Introductory Statistics (OpenStax), Chapter 3: Probability Topics",
        "/Author": "Barbara Illowsky, Susan Dean (OpenStax)",
        "/Subject": "CC BY 4.0. Download for free at https://openstax.org/details/books/introductory-statistics",
    })
    DEMO.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as f:
        w.write(f)
    print(f"made {out.name} ({out.stat().st_size // 1024} KB)")
    return out


def main(argv: list[str]) -> None:
    want_video = "--no-video" not in argv
    for name, url in FILES.items():
        if name.endswith(".mp4") and not want_video:
            continue
        p = download(name, url)
        if name.endswith(".pdf") and name.startswith("MIT"):
            DEMO.mkdir(parents=True, exist_ok=True)
            dst = DEMO / name
            if not dst.exists():
                dst.write_bytes(p.read_bytes())
        if name.endswith(".srt"):
            dst = DEMO / name if "lec02" in name else DEMO / "upload_examples" / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            if not dst.exists():
                dst.write_bytes(p.read_bytes())
    extract_chapter(RAW / "openstax_introstats_full.pdf")


if __name__ == "__main__":
    main(sys.argv[1:])
