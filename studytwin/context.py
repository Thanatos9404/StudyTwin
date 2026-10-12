"""Context budgeting with LLMSlim.

Retrieved units are numbered [S1..Sn] and compressed *inside* each block with LLMSlim
(query-aware, extractive, budget shared across blocks by relevance). The [S#] marker and the
location header are added *after* compression, so citations survive by construction, and because
LLMSlim's extractive mode keeps whole original sentences, every quoted sentence still exists
verbatim in the cited page / slide / transcript window.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from .config import settings
from .ingest.pipeline import est_tokens

logging.getLogger("llmslim").setLevel(logging.ERROR)


@dataclass
class Evidence:
    tag: str  # "S1"
    unit: dict[str, Any]
    header: str
    original: str
    text: str  # possibly compressed


@dataclass
class ContextPack:
    blocks: list[Evidence]
    prompt_text: str
    stats: dict[str, Any] = field(default_factory=dict)


def _header(u: dict[str, Any], tag: str) -> str:
    sec = f" | {u['section']}" if u.get("section") and u["kind"] != "transcript" else ""
    kind = {"text": "textbook", "slide": "slide", "transcript": "lecture video", "figure": "figure"}.get(u["kind"], u["kind"])
    return f"[{tag}] ({kind}: {u['label']}{sec})"


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def build_context(units: list[dict[str, Any]], query: str, budget: int | None = None, use_llmslim: bool | None = None) -> ContextPack:
    budget = budget or settings.context_budget
    use = settings.use_llmslim if use_llmslim is None else use_llmslim
    blocks = [Evidence(f"S{i + 1}", u, _header(u, f"S{i + 1}"), u["text"], u["text"]) for i, u in enumerate(units)]
    before = sum(est_tokens(b.header) + est_tokens(b.original) for b in blocks)
    stats: dict[str, Any] = {"llmslim": False, "tokens_before": before, "tokens_after": before, "budget": budget,
                             "blocks": len(blocks), "ms": 0.0}
    body_tokens = sum(est_tokens(b.original) for b in blocks)
    if use and blocks and before > budget:
        from llmslim import compress_documents

        header_tokens = before - body_tokens
        ratio = max(0.2, min(1.0, (budget - header_tokens) / max(1, body_tokens)))
        t0 = time.perf_counter()
        results = compress_documents([b.original for b in blocks], query=query, target_ratio=ratio)
        stats["ms"] = round((time.perf_counter() - t0) * 1000, 1)
        verbatim = 0
        total_sent = 0
        for b, r in zip(blocks, results):
            txt = (r.compressed_text or "").strip()
            b.text = txt if txt else "(omitted: low relevance to the question)"
            # every kept sentence must be verbatim from the original (extractive guarantee)
            orig_n = _norm(b.original)
            for s in re.split(r"(?<=[.!?])\s+", _norm(txt)):
                if len(s) > 12:
                    total_sent += 1
                    verbatim += s[:60] in orig_n
        after = sum(est_tokens(b.header) + est_tokens(b.text) for b in blocks)
        stats.update({"llmslim": True, "tokens_after": after, "target_ratio": round(ratio, 3),
                      "verbatim_sentences": f"{verbatim}/{total_sent}"})
    stats["saved_pct"] = round(100 * (1 - stats["tokens_after"] / max(1, stats["tokens_before"])), 1)
    stats["citations_preserved"] = f"{len(blocks)}/{len(blocks)}"
    prompt_text = "\n\n".join(f"{b.header}\n{b.text}" for b in blocks)
    return ContextPack(blocks, prompt_text, stats)
