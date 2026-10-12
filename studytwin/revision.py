"""Revision material for weak topics: cited flashcards and a forgetting-curve study schedule."""

from __future__ import annotations

import datetime as dt
from typing import Any

from . import learner, llm, store
from .config import settings
from .tutor import citation, retrieve

CARD_PROMPT = """Make {n} flashcards for the topic "{topic}" from the sources below. Each card tests one idea
(definition, formula, or a worked mini-example) and must be supported by one source.
Return JSON: {{"cards": [{{"front": "question or cue", "back": "concise answer", "source": "S1"}}]}}
SOURCES:
{sources}"""


def flashcards(topic_id: str, n: int = 6) -> list[dict[str, Any]]:
    topic = store.one("SELECT * FROM topics WHERE id=?", (topic_id,))
    if not topic:
        return []
    hits = retrieve(f"{topic['name']}: {topic['description']} {' '.join(topic.get('key_concepts') or [])}", k=5, topic_ids=[topic_id])
    units = [h.unit for h in hits]
    if llm.available() and units:
        src = "\n\n".join(f"[S{i + 1}] ({u['label']}) {u['text'][:1000]}" for i, u in enumerate(units))
        try:
            data = llm.chat_json(settings.fast_model, "You write accurate study flashcards. Reply with JSON only.",
                                 CARD_PROMPT.format(n=n, topic=topic["name"], sources=src), max_tokens=2500, temperature=0.2)
            cards = []
            for c in (data.get("cards") or [])[:n]:
                tag = str(c.get("source", "S1"))
                idx = int(tag[1:]) - 1 if tag[1:].isdigit() else 0
                u = units[idx] if 0 <= idx < len(units) else units[0]
                cards.append({"front": c.get("front", ""), "back": c.get("back", ""), "citation": citation(u)})
            if cards:
                return cards
        except Exception:  # noqa: BLE001
            pass
    # offline: cards from verified bank questions
    qs = store.many("SELECT * FROM questions WHERE topic_id=? AND verified=1 LIMIT ?", (topic_id, n))
    out = []
    for q in qs:
        u = store.one("SELECT * FROM units WHERE id=?", ((q.get("unit_ids") or [""])[0],))
        back = q["answer"]
        if q["type"] == "mcq" and q.get("options"):
            back = q["options"]["ABCD".index(q["answer"])]
        out.append({"front": q["stem"], "back": f"{back}. {q.get('explanation', '')[:240]}", "citation": citation(u) if u else None})
    return out


def _topo(topics: list[dict[str, Any]]) -> list[str]:
    order, seen = [], set()
    by = {t["id"]: t for t in topics}

    def visit(tid: str) -> None:
        if tid in seen or tid not in by:
            return
        seen.add(tid)
        for p in by[tid].get("prerequisites") or []:
            visit(p)
        order.append(tid)

    for t in topics:
        visit(t["id"])
    return order


def schedule(student_id: str, exam_date: str | None = None, minutes_per_day: int = 45, today: dt.date | None = None) -> dict[str, Any]:
    """Day-by-day plan until the exam: weakest topics first (respecting prerequisites), then
    spaced reviews when predicted retention falls below 80%, and a mock exam on the last day."""
    today = today or dt.date.today()
    exam = dt.date.fromisoformat(exam_date) if exam_date else today + dt.timedelta(days=7)
    days = max(1, (exam - today).days)
    topics = store.many("SELECT * FROM topics WHERE parent_id IS NULL ORDER BY ord")
    state = learner.get_state(student_id)
    order = _topo(topics)
    names = {t["id"]: t["name"] for t in topics}
    # simulated memory state for planning
    sim = {t: {"p": float(state[t]["p"]), "half_life": float(state[t].get("half_life") or 1.0), "last": 0 if state[t].get("last_ts") else None}
           for t in order if t in state}
    weak_queue = [t for t in sorted(order, key=lambda t: (sim[t]["p"] >= 0.8, order.index(t))) if sim[t]["p"] < 0.8]
    plan = []
    for d in range(days):
        date = today + dt.timedelta(days=d)
        tasks: list[dict[str, Any]] = []
        budget = minutes_per_day
        if d == days - 1 and days > 1:
            tasks.append({"topic": "All topics", "activity": "Mock exam (timed) + review the report", "minutes": min(budget, 45)})
            plan.append({"date": date.isoformat(), "tasks": tasks})
            continue
        # spaced reviews first
        for t, s in sim.items():
            if s["last"] is not None and budget >= 10:
                ret = 2 ** (-(d - s["last"]) / max(s["half_life"], 0.25))
                if ret < 0.8 and s["p"] >= 0.5:
                    tasks.append({"topic": names[t], "topic_id": t, "activity": "Spaced review: flashcards + 3 questions",
                                  "minutes": 10, "why": f"predicted retention {ret:.0%}"})
                    s["last"], s["half_life"] = d, s["half_life"] * 2
                    budget -= 10
        # then new/weak material
        while budget >= 20 and weak_queue:
            t = weak_queue.pop(0)
            hits = retrieve(names[t], k=2, topic_ids=[t])
            tasks.append({"topic": names[t], "topic_id": t, "activity": "Study the sources, ask the tutor, then a 5-question adaptive quiz",
                          "minutes": 25 if budget >= 25 else budget, "sources": [h.unit["label"] for h in hits],
                          "why": f"mastery {sim[t]['p']:.0%}"})
            sim[t]["last"], sim[t]["p"] = d, min(0.95, sim[t]["p"] + 0.25)
            budget -= 25
        if not tasks:
            tasks.append({"topic": "Mixed", "activity": "Adaptive quiz across all topics", "minutes": min(20, minutes_per_day)})
        plan.append({"date": date.isoformat(), "tasks": tasks})
    return {"exam_date": exam.isoformat(), "minutes_per_day": minutes_per_day, "days": plan}
