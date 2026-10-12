"""Source-grounded tutor.

question -> hybrid retrieval -> support gate (decline if the material does not cover it)
         -> LLMSlim context budget -> LLM answer with [S#] citations + verbatim quotes
         -> post-validation (invalid citations dropped, quotes checked against the original
            unit text, uncited sentences counted) -> learner-model soft update.

Outside knowledge is never mixed into the answer: it is returned separately and flagged.
"""

from __future__ import annotations

import os
import re
import time
from collections import Counter
from typing import Any

from . import learner, llm, store
from .config import settings
from .context import build_context
from .retrieval import Hit, get_index

MIN_SUPPORT = float(os.getenv("STUDYTWIN_MIN_SUPPORT", "0.55"))

SYSTEM = """You are StudyTwin, a tutor that answers ONLY from the student's course material.
Rules:
1. Use only the numbered sources [S1]..[S{n}]. Every sentence that states a fact, formula or number must end
   with at least one citation written exactly like [S2] (ASCII square brackets). Never cite a source that does
   not support the sentence.
2. If the sources do not contain the answer, set "status" to "not_covered" and say briefly that the course
   material does not cover it. Do not answer from memory in "answer".
3. If the sources only partly answer, set "status" to "partial", answer the covered part with citations and
   name what is missing.
4. {outside_rule}
5. For calculations, show the steps; every input number must come from a cited source.
6. "quotes": for each source you cite, copy one short phrase (5-20 words) VERBATIM from that source.
7. "student_signal": judge the STUDENT'S MESSAGE (not your answer): "misconception" if it states something
   false about the topic, "confusion" if it shows the student is lost on a basic idea, "understanding" if it
   correctly explains or applies an idea, otherwise "neutral".
{lang_rule}
Return JSON only:
{{"status": "answered|partial|not_covered", "answer": "markdown with [S#] citations",
  "quotes": [{{"source": "S1", "text": "verbatim phrase"}}], "outside_knowledge": "",
  "student_signal": "neutral|misconception|confusion|understanding", "followups": ["...", "..."]}}"""

OUTSIDE_ALLOWED = ('The student allowed general knowledge. If the sources do not fully answer the question, also give a '
                   'brief general answer (1-3 sentences, no citations) ONLY in "outside_knowledge"; it is shown with a '
                   "warning label. Never put uncited general knowledge in \"answer\".")
OUTSIDE_FORBIDDEN = 'Leave "outside_knowledge" empty.'
LANG_HI = ('8. Write "answer" in simple Hindi in Devanagari script (even if the student writes in Latin script), '
           "with English technical terms in brackets; keep math notation, numbers and the [S#] citations unchanged. "
           "Quotes stay verbatim in English.")
OUTSIDE_ONLY = ("The student's course material does not cover this question. Give a brief general-knowledge answer in "
                "2-3 sentences, without claiming it comes from their course. {lang}")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def verify_quote(quote: str, original: str) -> str:
    """'exact' if the quote occurs verbatim (modulo spacing/punctuation), 'approx' if >=80% of its
    words occur in order-insensitive form, otherwise 'unverified'."""
    q, o = _norm(quote), _norm(original)
    if not q:
        return "unverified"
    if q in o:
        return "exact"
    qw = q.split()
    ow = set(o.split())
    return "approx" if qw and sum(w in ow for w in qw) / len(qw) >= 0.8 else "unverified"


def normalize_citations(text: str) -> str:
    """Canonicalize citation styles models produce (【S1】, [S1, S2], (S1), [S1†L3]) to [S1][S2]."""
    text = re.sub("[​‌‍⁠﻿]", "", text)  # zero-width characters some models emit
    text = re.sub(r"\[\s*(?:source\s*)?S\s*(\d+)\s*\]", r"[S\1]", text, flags=re.I)
    text = re.sub(r"【\s*(S\d+)[^】]*】", r"[\1]", text)
    text = re.sub(r"\[(S\d+)[†:][^\]]*\]", r"[\1]", text)
    text = re.sub(r"\[\s*(S\d+(?:\s*[,;]\s*S\d+)+)\s*\]",
                  lambda m: "".join(f"[{x.strip()}]" for x in re.split(r"[,;]", m.group(1))), text)
    text = re.sub(r"\((S\d+)\)", r"[\1]", text)
    return text


def citation(unit: dict[str, Any], tag: str = "", quote: str = "", status: str = "") -> dict[str, Any]:
    src = store.one("SELECT id, kind, title, meta, remote_url FROM sources WHERE id=?", (unit["source_id"],)) or {}
    return {
        "tag": tag, "unit_id": unit["id"], "label": unit["label"], "kind": unit["kind"], "section": unit.get("section") or "",
        "source_kind": src.get("kind"), "source_title": src.get("title"), "loc": unit["loc"],
        "image": unit.get("image"), "page_image": unit.get("page_image"),
        "excerpt": unit["text"][:420], "quote": quote, "quote_status": status,
    }


def retrieve(query: str, k: int | None = None, topic_ids: list[str] | None = None) -> list[Hit]:
    return get_index().search(query, k=k or settings.top_k, topic_ids=topic_ids)


def _to_english(message: str) -> str:
    """The embedder and course material are English: translate Devanagari questions for retrieval only."""
    if not re.search("[ऀ-ॿ]", message) or not llm.available():
        return message
    try:
        out = llm.chat(settings.fast_model, [
            {"role": "system", "content": "Translate the student's question into English for searching course material. Reply with only the translation."},
            {"role": "user", "content": message},
        ], max_tokens=600, temperature=0.0).strip()
        return out or message
    except Exception:  # noqa: BLE001
        return message


def _rewrite_followup(message: str, history: list[dict[str, str]]) -> str:
    """Cheap follow-up resolution: short or pronoun-led questions borrow the previous question."""
    prev = [h["content"] for h in history if h.get("role") == "user"]
    if prev and (len(message.split()) <= 7 or re.match(r"^(and|but|so|what about|why|how about|it|this|that)\b", message.lower())):
        return f"{prev[-1]} {message}"
    return message


def answer(
    message: str,
    student_id: str | None = None,
    history: list[dict[str, str]] | None = None,
    lang: str = "en",
    allow_outside: bool = False,
    use_llmslim: bool | None = None,
    k: int | None = None,
    record: bool = True,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    history = history or []
    query = _rewrite_followup(_to_english(message), history)
    hits = retrieve(query, k=k)
    support = max((h.dense for h in hits), default=0.0)
    out: dict[str, Any] = {"question": message, "retrieval_query": query, "support": round(support, 3),
                           "retrieved": [h.unit["id"] for h in hits]}
    pack = build_context([h.unit for h in hits], query, use_llmslim=use_llmslim)
    out["context_stats"] = pack.stats
    out["contexts"] = [b.text for b in pack.blocks]

    if not hits or support < MIN_SUPPORT:
        out.update(_declined(hits, support))
        if allow_outside and llm.available():
            try:
                lang_note = "Answer in Hindi (Devanagari script)." if lang == "hi" else ""
                out["outside_knowledge"] = llm.chat(
                    settings.fast_model,
                    [{"role": "system", "content": OUTSIDE_ONLY.format(lang=lang_note)}, {"role": "user", "content": message}],
                    max_tokens=800, temperature=0.2,
                ).strip()
            except Exception:  # noqa: BLE001 - outside knowledge is optional
                pass
    elif llm.available():
        out.update(_llm_answer(message, query, pack, lang, allow_outside))
    else:
        out.update(_offline_answer(query, pack))

    # learner model: soft evidence from the conversation
    topic = _topic_of(out.get("citations") or [], hits)
    out["topic_id"] = topic
    if student_id and record:
        upd = learner.observe_conversation(student_id, topic, out.get("student_signal", "neutral"), ref=message[:80])
        out["mastery_update"] = upd
        store.insert("chat", {"student_id": student_id, "role": "user", "content": message, "meta": {"lang": lang}, "ts": time.time()})
        store.insert("chat", {"student_id": student_id, "role": "assistant", "content": out.get("answer", ""),
                              "meta": {k2: out.get(k2) for k2 in ("status", "citations", "outside_knowledge", "context_stats", "topic_id")},
                              "ts": time.time()})
    out["latency_s"] = round(time.perf_counter() - t0, 2)
    return out


def _declined(hits: list[Hit], support: float) -> dict[str, Any]:
    near = [h.unit["label"] for h in hits[:3]]
    msg = ("I couldn't find this in your course material, so I won't answer it as if it were course content. "
           + (f"The closest material is {', '.join(near)}, but it does not appear to cover your question." if near else ""))
    return {"status": "not_covered", "answer": msg, "citations": [], "outside_knowledge": "", "student_signal": "neutral",
            "followups": [], "gate": "retrieval_support_below_threshold", "model": None}


def _llm_answer(message: str, query: str, pack, lang: str, allow_outside: bool) -> dict[str, Any]:
    system = SYSTEM.format(n=len(pack.blocks), outside_rule=OUTSIDE_ALLOWED if allow_outside else OUTSIDE_FORBIDDEN,
                           lang_rule=LANG_HI if lang == "hi" else "")
    user = f"SOURCES:\n{pack.prompt_text}\n\nSTUDENT: {message}"
    try:
        data = llm.chat_json(settings.tutor_model, system, user, max_tokens=2500, temperature=0.1)
        usage = llm.last_usage()
    except Exception as e:  # noqa: BLE001
        res = _offline_answer(query, pack)
        res["error"] = f"LLM unavailable, showing extractive answer: {str(e)[:160]}"
        return res
    if not isinstance(data, dict):
        data = {}
    status = str(data.get("status") or "answered")
    ans = normalize_citations(str(data.get("answer") or "").strip())
    tags = {b.tag: b for b in pack.blocks}
    quotes = {}
    for q in data.get("quotes") or []:
        if isinstance(q, dict) and q.get("source") in tags:
            quotes.setdefault(q["source"], str(q.get("text") or ""))
    used = []
    for m in re.finditer(r"\[S(\d+)\]", ans):
        tag = f"S{m.group(1)}"
        if tag in tags and tag not in used:
            used.append(tag)
    # strip citations to non-existent sources
    ans = re.sub(r"\[S(\d+)\]", lambda m: m.group(0) if f"S{m.group(1)}" in tags else "", ans)
    cites = []
    for tag in used:
        b = tags[tag]
        q = quotes.get(tag, "")
        cites.append(citation(b.unit, tag, q, verify_quote(q, b.original) if q else ""))
    sentences = [s for s in re.split(r"(?<=[.!?])\s+|\n+", ans) if len(re.sub(r"\[S\d+\]", "", s).strip()) > 25]
    uncited = [s for s in sentences if not re.search(r"\[S\d+\]", s) and not re.search(r"[:]$", s.strip())]
    if status == "not_covered":
        cites = []
        if not re.sub(r"\[S\d+\]", "", ans).strip():
            ans = "Your course material does not cover this question, so I won't answer it as if it were course content."
    signal = str(data.get("student_signal") or "neutral").lower()
    return {
        "status": status if status in ("answered", "partial", "not_covered") else "answered",
        "answer": ans, "citations": cites,
        "outside_knowledge": str(data.get("outside_knowledge") or "").strip() if allow_outside else "",
        "student_signal": signal if signal in ("misconception", "confusion", "understanding") else "neutral",
        "followups": [str(f) for f in (data.get("followups") or [])][:3],
        "uncited_sentences": len(uncited), "model": settings.tutor_model.id, "usage": usage,
    }


def _offline_answer(query: str, pack) -> dict[str, Any]:
    """Deterministic extractive answer (no LLM): best sentences from the top sources, cited."""
    from llmslim import compress

    parts, cites = [], []
    for b in pack.blocks[:2]:
        r = compress(b.original, target_ratio=0.35, query=query)
        txt = (r.compressed_text or b.original).strip()
        sent = " ".join(re.split(r"(?<=[.!?])\s+", txt)[:2])
        parts.append(f"{sent} [{b.tag}]")
        cites.append(citation(b.unit, b.tag, sent[:160], "exact" if _norm(sent[:160]) in _norm(b.original) else "approx"))
    return {"status": "answered", "answer": "From your course material: " + " ".join(parts), "citations": cites,
            "outside_knowledge": "", "student_signal": "neutral", "followups": [], "uncited_sentences": 0,
            "model": "offline-extractive (LLMSlim)"}


def _topic_of(cites: list[dict[str, Any]], hits: list[Hit]) -> str | None:
    ids = [c["unit_id"] for c in cites] or [h.unit["id"] for h in hits[:3]]
    if not ids:
        return None
    qs = ",".join("?" for _ in ids)
    rows = store.many(f"SELECT topic_id FROM units WHERE id IN ({qs})", tuple(ids))
    c = Counter(r["topic_id"] for r in rows if r["topic_id"])
    return c.most_common(1)[0][0] if c else None
