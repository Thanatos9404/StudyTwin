"""PDF ingestion for textbooks and slide decks (pypdfium2: Apache-2.0/BSD).

Textbook PDFs  -> one text unit per paragraph group (page-linked, section-tagged) plus one figure
                  unit per embedded image (cropped from the rendered page).
Slide PDFs     -> one unit per slide. Handouts with several slides per page are split by
                  detecting the slide frames, so citations point at a single slide.
Every unit keeps the rendered page image so the UI can open the exact page or slide.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

RENDER_SCALE = 1.6  # 72 dpi * 1.6 ~ 115 dpi: crisp enough for the viewer, small on disk

_BOILER = [
    re.compile(r"^This OpenStax book is available for free at .*$", re.I),
    re.compile(r"^Chapter \d+ \| .*\d+\s*$"),
    re.compile(r"^\d+\s+Chapter \d+ \| .*$"),
    re.compile(r"^MIT OpenCourseWare\s*$", re.I),
    re.compile(r"^https?://ocw\.mit\.edu\s*$", re.I),
    re.compile(r"^For information about citing these materials.*$", re.I),
]
_SECTION = re.compile(r"^(\d{1,2}\.\d{1,2})\s*\|\s*(.{3,90})$")
_SECTION_GENERIC = re.compile(r"^(\d{1,2}\.\d{1,2})\s+([A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+|and|of|the|for|to|in|with|&))*)$")
_USE_GENERIC = {"on": True}  # switched off for books that use explicit "3.2 | Title" headings
_FIG_CAPTION = re.compile(r"(Figure\s+\d+\.\d+[^\n]{0,300})")


@dataclass
class RawUnit:
    kind: str  # text | slide | figure
    text: str
    loc: dict[str, Any]
    label: str
    section: str = ""
    image: str | None = None  # media-relative path of a crop (slide / figure)
    page_image: str | None = None  # media-relative path of the full rendered page
    extra: dict[str, Any] = field(default_factory=dict)


def _clean_lines(text: str) -> list[str]:
    lines = [ln.strip() for ln in text.replace("\r", "").split("\n")]
    out = []
    for ln in lines:
        if not ln:
            out.append("")
            continue
        if any(p.match(ln) for p in _BOILER):
            continue
        out.append(ln)
    return out


def _paragraphs(lines: list[str]) -> list[str]:
    """Rebuild paragraphs from PDF lines (lines ending without punctuation are joined)."""
    paras: list[str] = []
    cur: list[str] = []
    for ln in lines:
        if not ln:
            if cur:
                paras.append(" ".join(cur))
                cur = []
            continue
        if _heading(ln):
            if cur:
                paras.append(" ".join(cur))
                cur = []
            paras.append(ln)
            continue
        starts_new = bool(re.match(r"^(•|–|-|\d+\.\s|[a-z]\.\s|Example \d|Solution \d|Try It|Figure \d|Table \d|NOTE)", ln))
        if starts_new and cur:
            paras.append(" ".join(cur))
            cur = []
        cur.append(ln)
    if cur:
        paras.append(" ".join(cur))
    return [re.sub(r"\s+", " ", p).strip() for p in paras if p.strip()]


def _group(paras: list[str], target_words: int = 170, max_words: int = 260) -> list[str]:
    chunks: list[str] = []
    cur: list[str] = []
    n = 0
    for p in paras:
        w = len(p.split())
        if cur and n + w > max_words:
            chunks.append(" ".join(cur))
            cur, n = [], 0
        cur.append(p)
        n += w
        if n >= target_words:
            chunks.append(" ".join(cur))
            cur, n = [], 0
    if cur:
        if chunks and n < 40:
            chunks[-1] += " " + " ".join(cur)
        else:
            chunks.append(" ".join(cur))
    return chunks


def _heading(p: str) -> str | None:
    m = _SECTION.match(p) or (_SECTION_GENERIC.match(p) if _USE_GENERIC["on"] else None)
    return f"{m.group(1)} {m.group(2).strip()}" if m else None


def _sectioned_chunks(paras: list[str], section: str) -> list[tuple[str, str]]:
    """Group paragraphs into ~170-word chunks; a section heading always starts a new chunk."""
    out: list[tuple[str, str]] = []
    block: list[str] = []

    def flush() -> None:
        if block:
            out.extend((section, c) for c in _group(block))
            block.clear()

    for p in paras:
        h = _heading(p)
        if h:
            flush()
            section = h
        block.append(p)
    flush()
    return out


def _render(page, out: Path) -> tuple[int, int]:
    img = page.render(scale=RENDER_SCALE).to_pil()
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)
    return img.size


def _crop(page_png: Path, bounds: tuple[float, float, float, float], page_h: float, out: Path, pad: float = 4) -> None:
    from PIL import Image

    l, b, r, t = bounds
    s = RENDER_SCALE
    with Image.open(page_png) as im:
        box = (max(0, int((l - pad) * s)), max(0, int((page_h - t - pad) * s)),
               min(im.width, int((r + pad) * s)), min(im.height, int((page_h - b + pad) * s)))
        im.crop(box).save(out, optimize=True)


def _iou(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    l, bt, r, t = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, r - l) * max(0.0, t - bt)
    area = lambda x: (x[2] - x[0]) * (x[3] - x[1])  # noqa: E731
    return inter / (area(a) + area(b) - inter) if inter else 0.0


def _slide_frames(page) -> list[tuple[float, float, float, float]]:
    W, H = page.get_size()
    frames = []
    for o in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_PATH], max_depth=3):
        l, b, r, t = o.get_bounds()
        if (r - l) > 0.3 * W and (t - b) > 0.25 * H and (r - l) < 0.98 * W:
            if not any(_iou((l, b, r, t), f) > 0.75 for f in frames):
                frames.append((l, b, r, t))
    frames.sort(key=lambda f: (-round(f[3] / 40), f[0]))  # reading order: rows top->bottom, then left->right
    return frames


def is_slide_deck(pdf: pdfium.PdfDocument) -> bool:
    n = len(pdf)
    sample = [pdf[i] for i in range(min(n, 6))]
    landscape = sum(1 for p in sample if p.get_size()[0] > p.get_size()[1])
    framed = sum(1 for p in sample if len(_slide_frames(p)) >= 2)
    words = sum(len(p.get_textpage().get_text_range().split()) for p in sample) / max(1, len(sample))
    return framed >= 1 or (landscape >= len(sample) / 2 and words < 250)


def ingest_pdf(
    path: Path,
    media_dir: Path,
    media_prefix: str,
    kind: str | None = None,
    page_offset: int = 0,
    short_title: str = "",
) -> tuple[str, list[RawUnit]]:
    """Return (kind, units). ``media_prefix`` is the media-relative folder for rendered images."""
    pdf = pdfium.PdfDocument(str(path))
    if kind is None:
        kind = "slides" if is_slide_deck(pdf) else "textbook"
    out_dir = media_dir / media_prefix
    out_dir.mkdir(parents=True, exist_ok=True)
    units = ingest_slides(pdf, out_dir, media_prefix, short_title) if kind == "slides" else ingest_textbook(
        pdf, out_dir, media_prefix, page_offset, short_title
    )
    pdf.close()
    return kind, units


def ingest_textbook(pdf, out_dir: Path, prefix: str, page_offset: int, short_title: str) -> list[RawUnit]:
    units: list[RawUnit] = []
    section = "Introduction"
    pipe_style = any(
        _SECTION.match(ln.strip()) for i in range(len(pdf)) for ln in pdf[i].get_textpage().get_text_range().splitlines()
    )
    _USE_GENERIC["on"] = not pipe_style
    for i in range(len(pdf)):
        page = pdf[i]
        W, H = page.get_size()
        page_no = i + 1
        page_label = page_no + page_offset
        png = out_dir / f"page_{page_no:03d}.png"
        _render(page, png)
        rel_png = f"{prefix}/{png.name}"
        raw = page.get_textpage().get_text_range()
        lines = _clean_lines(raw)
        paras = _paragraphs(lines)
        start_section = section
        for sec, chunk in _sectioned_chunks(paras, section):
            units.append(RawUnit(
                kind="text", text=chunk,
                loc={"page": page_no, "page_label": page_label},
                label=f"{short_title or 'Textbook'} p. {page_label}",
                section=sec, page_image=rel_png,
            ))
            section = sec
        page_section = start_section or section
        # Figures: embedded raster images larger than ~3% of the page.
        captions = _FIG_CAPTION.findall(raw.replace("\r", "").replace("\n", " "))
        figs = []
        for o in page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=3):
            l, b, r, t = o.get_bounds()
            if (r - l) * (t - b) > 0.03 * W * H:
                figs.append((l, b, r, t))
        figs.sort(key=lambda f: -f[3])
        for fi, bounds in enumerate(figs):
            crop = out_dir / f"page_{page_no:03d}_fig{fi + 1}.png"
            _crop(png, bounds, H, crop)
            cap = captions[fi].strip() if fi < len(captions) else ""
            cap = re.split(r"(?<=[.!?])\s", cap, maxsplit=1)[0][:180] if cap else ""
            units.append(RawUnit(
                kind="figure",
                text=cap or f"Figure on page {page_label}",
                loc={"page": page_no, "page_label": page_label, "bbox": [round(x, 1) for x in bounds], "page_size": [W, H]},
                label=f"{short_title or 'Textbook'} p. {page_label} · figure",
                section=page_section, image=f"{prefix}/{crop.name}", page_image=rel_png,
                extra={"caption": cap},
            ))
    return units


def ingest_slides(pdf, out_dir: Path, prefix: str, short_title: str) -> list[RawUnit]:
    units: list[RawUnit] = []
    slide_no = 0
    for i in range(len(pdf)):
        page = pdf[i]
        W, H = page.get_size()
        page_no = i + 1
        png = out_dir / f"page_{page_no:03d}.png"
        _render(page, png)
        rel_png = f"{prefix}/{png.name}"
        tp = page.get_textpage()
        full = tp.get_text_range()
        if re.search(r"MIT OpenCourseWare", full) and len(full) < 400:
            continue  # license boilerplate page (recorded in DATA.md instead)
        frames = _slide_frames(page) or [(0.0, 0.0, W, H)]
        for f in frames:
            slide_no += 1
            text = tp.get_text_bounded(*f)
            lines = [ln for ln in _clean_lines(text) if ln]
            if not lines:
                continue
            title = lines[0][:90]
            crop = out_dir / f"slide_{slide_no:03d}.png"
            if len(frames) > 1:
                _crop(png, f, H, crop, pad=2)
            else:
                crop = png
            units.append(RawUnit(
                kind="slide",
                text=re.sub(r"[ \t]+", " ", "\n".join(lines)),
                loc={"page": page_no, "slide": slide_no, "bbox": [round(x, 1) for x in f], "page_size": [W, H]},
                label=f"{short_title or 'Slides'} · slide {slide_no}",
                section=title, image=f"{prefix}/{crop.name}", page_image=rel_png,
            ))
    return units


def find_highlight(pdf_path: Path, page_no: int, snippet: str) -> list[list[float]]:
    """Rectangles (PDF points, top-left origin) where ``snippet`` occurs on a page (for the viewer)."""
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page = pdf[page_no - 1]
        _, H = page.get_size()
        tp = page.get_textpage()
        rects: list[list[float]] = []
        words = snippet.split()
        for n in (12, 8, 5):
            if len(words) < 3:
                break
            probe = " ".join(words[:n])
            searcher = tp.search(probe, match_case=False)
            hit = searcher.get_next()
            if hit:
                idx, count = hit
                # extend to cover the whole snippet length (bounded)
                count = min(tp.count_chars() - idx, max(count, len(snippet)))
                nrect = tp.count_rects(idx, count)
                for r in range(min(nrect, 40)):
                    l, b, rr, t = tp.get_rect(r)
                    rects.append([l, H - t, rr - l, t - b])
                break
        return rects
    finally:
        pdf.close()
