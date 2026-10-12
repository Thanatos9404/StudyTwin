"""Vision enrichment: turn figures and slide images into searchable, citable text.

A vision-language model on Nebius (default GLM-5.3-Flash) transcribes the text and equations
on a slide and describes diagrams (trees, Venn diagrams, tables, plots) including every number
and label, so questions like "what is P(B|A) in the radar tree?" can be answered from a figure.
Without an LLM the figure keeps its printed caption / slide text only.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .. import llm
from ..config import settings

PROMPT = """You are indexing course material for a study assistant. The image is {what}.
Context (may be partial or garbled): {hint}

Return a JSON object with exactly these keys:
- "has_diagram": true if the image contains a diagram, figure, chart, table or drawing (not only text/bullets).
- "description": 2-4 sentences describing the diagram and the concept it illustrates. Include EVERY number,
  probability, label and axis value shown, exactly as printed. Empty string if has_diagram is false.
- "text": a faithful transcription of the text and equations in the image, using plain-text math
  (e.g. P(A|B) = P(A ∩ B) / P(B)). Do not add facts that are not visible."""


def describe(image_path: Path, what: str, hint: str) -> dict[str, Any] | None:
    if not llm.available():
        return None
    try:
        out = llm.chat_json(
            settings.vision_model,
            "You transcribe and describe educational images precisely. Reply with JSON only.",
            [
                {"type": "text", "text": PROMPT.format(what=what, hint=hint[:600] or "none")},
                llm.image_part(image_path),
            ],
            max_tokens=1400,
            temperature=0.0,
        )
        if not isinstance(out, dict):
            return None
        return {
            "has_diagram": bool(out.get("has_diagram")),
            "description": str(out.get("description") or "").strip(),
            "text": str(out.get("text") or "").strip(),
        }
    except Exception as e:  # noqa: BLE001 - enrichment is best-effort
        return {"error": str(e)[:200]}


def describe_many(jobs: list[tuple[Path, str, str]], workers: int = 4) -> list[dict[str, Any] | None]:
    if not jobs or not llm.available():
        return [None] * len(jobs)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(lambda j: describe(*j), jobs))
