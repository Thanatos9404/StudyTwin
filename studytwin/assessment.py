"""Adaptive assessment: question generation, cross-model verification, quizzes, grading, reports.

Generation  : the generator model writes MCQ / short-answer / numerical questions from cited units of
              one topic; each question carries topic, subtopic, source units and difficulty (1-3).
Verification: a model from a *different family* solves each question blind (no answer key) from the
              same sources; only questions where both agree (MCQ letter / number within tolerance /
              key judged correct for short answers) enter the bank.
Novelty     : near-duplicate stems are rejected (embedding cosine >= 0.90) and a student never gets
              a question they have already attempted while unseen ones remain.
Feedback    : every graded answer returns an explanation with citations that open the exact
              page / slide / timestamp, plus the misconception behind a wrong MCQ option.
"""

from __future__ import annotations

import hashlib
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from typing import Any

import numpy as np

from . import learner, llm, store
from .config import settings
from .embed import get_embedder
from .tutor import citation

TYPES = ("mcq", "numerical", "short")
LETTERS = "ABCD"

GEN_PROMPT = """Write {n} exam questions on the topic "{topic}" ({topic_desc}) using ONLY the sources below.
Subtopics you may tag: {subtopics}.
Use this mix of types: {types}. Difficulty: 1 = recall, 2 = apply, 3 = multi-step reasoning.

Return JSON: {{"questions": [
 {{"type": "mcq|short|numerical", "difficulty": 1, "subtopic": "T1.1", "concept": "key concept tested",
   "stem": "self-contained question (give every number needed)",
   "options": ["...", "...", "...", "..."],          (mcq only: 4 options, exactly one correct, no letters)
   "answer": "B",                                    (mcq: letter | numerical: decimal number | short: 1-2 sentence model answer)
   "tolerance": 0.005,                               (numerical only: absolute tolerance)
   "explanation": "worked solution citing sources like [S1]",
   "misconceptions": {{"A": "the misconception that leads to option A"}},  (mcq: one per wrong option; others: list of 1-2 typical mistakes)
   "sources": ["S1"]}}
]}}
Rules: every answer must follow from the cited sources; numerical answers must be computable from the stem
alone; avoid "all/none of the above"; do not mention "the source" or "S1" inside the stem or options;
make wrong options plausible and tied to real misconceptions.

SOURCES:
{sources}"""

VERIFY_PROMPT = """Solve this exam question using the source excerpts (you may also use standard reasoning).
Do NOT guess what answer the author intended; solve it yourself.

QUESTION ({qtype}): {stem}
{options}
SOURCES:
{sources}

Return JSON: {{"answer": "{answer_fmt}", "answerable_from_sources": true, "issues": "ambiguity or errors, empty if none",
"confidence": 0.0}}"""

SHORT_KEY_PROMPT = """Check this exam question and its reference answer against the sources.
QUESTION: {stem}
REFERENCE ANSWER: {answer}
SOURCES:
{sources}
Return JSON: {{"key_correct": true, "answerable_from_sources": true, "issues": "empty if none"}}"""

GRADE_PROMPT = """Grade a student's short answer against the reference answer and sources.
QUESTION: {stem}
REFERENCE ANSWER: {answer}
SOURCES:
{sources}
STUDENT ANSWER: {response}
Return JSON: {{"score": 0 | 0.5 | 1, "feedback": "2-3 sentences, cite sources like [S1]",
"misconception": "the specific misconception shown, or empty"}}"""


def _norm_stem(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _hash(s: str) -> str:
    return hashlib.sha1(_norm_stem(s).encode()).hexdigest()[:16]


def parse_number(s: Any) -> float | None:
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).strip().replace(",", "").replace("−", "-")
    pct = t.endswith("%")
    t = t.rstrip("%").strip()
    m = re.search(r"-?\d+(?:\.\d+)?\s*/\s*-?\d+(?:\.\d+)?", t)
    try:
        if m:
            a, b = m.group(0).split("/")
            val = float(Fraction(a.strip()) / Fraction(b.strip())) if "." not in m.group(0) else float(a) / float(b)
        else:
            m2 = re.search(r"-?\d*\.?\d+(?:e-?\d+)?", t)
            if not m2:
                return None
            val = float(m2.group(0))
    except (ValueError, ZeroDivisionError):
        return None
    return val / 100 if pct else val


def numbers_match(a: Any, key: Any, tol: float | None) -> bool:
    x, y = parse_number(a), parse_number(key)
    if x is None or y is None:
        return False
    tol = max(float(tol or 0.0), 0.01 * abs(y), 1e-6)
    return abs(x - y) <= tol or (abs(y) <= 1 and abs(x / 100 - y) <= tol and x > 1)  # accept "34.3" for 0.343


def mcq_letter(resp: Any) -> str:
    m = re.match(r"\s*\(?([A-Da-d])\b", str(resp or ""))
    return m.group(1).upper() if m else str(resp or "").strip()[:1].upper()


def _sources_text(units: list[dict[str, Any]]) -> tuple[str, dict[str, dict[str, Any]]]:
    tags = {}
    parts = []
    for i, u in enumerate(units, start=1):
        tags[f"S{i}"] = u
        parts.append(f"[S{i}] ({u['label']}) {u['text'][:1400]}")
    return "\n\n".join(parts), tags


# ---- generation + verification ----------------------------------------------------------

def _pick_units(topic_id: str, k: int, rng: random.Random, exclude: set[str] | None = None) -> list[dict[str, Any]]:
    units = store.many("SELECT * FROM units WHERE topic_id=? ORDER BY source_id, ord", (topic_id,))
    units = [u for u in units if u["id"] not in (exclude or set()) and len(u["text"]) > 120]
    by_kind: dict[str, list] = {}
    for u in units:
        by_kind.setdefault(u["kind"], []).append(u)
    for v in by_kind.values():
        rng.shuffle(v)
    out: list[dict[str, Any]] = []
    while len(out) < k and any(by_kind.values()):
        for kind in ("figure", "slide", "text", "transcript"):
            if by_kind.get(kind) and len(out) < k:
                out.append(by_kind[kind].pop())
    return out


def generate_for_topic(topic_id: str, n: int = 5, types: tuple[str, ...] = TYPES, seed: int = 0,
                       exclude_units: set[str] | None = None, origin: str = "bank") -> dict[str, Any]:
    """Generate n questions for a topic, verify them cross-model, store the verified ones."""
    topic = store.one("SELECT * FROM topics WHERE id=?", (topic_id,))
    if not topic:
        raise ValueError(f"unknown topic {topic_id}")
    subs = store.many("SELECT id, name FROM topics WHERE parent_id=?", (topic_id,))
    rng = random.Random(f"{topic_id}-{seed}")
    units = _pick_units(topic_id, 4, rng, exclude_units)
    stats = {"topic": topic_id, "generated": 0, "verified": 0, "rejected": 0, "duplicates": 0, "unit_ids": [u["id"] for u in units]}
    if not units:
        return stats
    if not llm.available():
        qs = _offline_questions(topic, units, n)
    else:
        src_text, tags = _sources_text(units)
        mix = ", ".join(types[i % len(types)] for i in range(n))
        try:
            data = llm.chat_json(
                settings.generator_model, "You are an expert assessment writer for a university course. Reply with JSON only.",
                GEN_PROMPT.format(n=n, topic=topic["name"], topic_desc=topic["description"],
                                  subtopics=", ".join(f"{s['id']} {s['name']}" for s in subs) or topic_id,
                                  types=mix, sources=src_text),
                max_tokens=8000, temperature=0.5, cache_salt=f"seed{seed}",
            )
        except Exception as e:  # noqa: BLE001 - a failed batch should not stop the bank
            stats["error"] = str(e)[:200]
            data = {}
        qs = []
        for q in (data.get("questions") if isinstance(data, dict) else data) or []:
            nq = _normalize_question(q, topic_id, tags, {s["id"] for s in subs})
            if nq:
                qs.append(nq)
    stats["generated"] = len(qs)
    existing = store.many("SELECT id, stem FROM questions")
    emb = get_embedder()
    ex_vecs = emb.encode([e["stem"] for e in existing]) if existing else None
    accepted_vecs: list[np.ndarray] = []
    for q in qs:
        v = emb.encode([q["stem"]])[0]
        dup = (ex_vecs is not None and len(ex_vecs) and float(np.max(ex_vecs @ v)) >= 0.90) or any(float(a @ v) >= 0.90 for a in accepted_vecs)
        if dup:
            stats["duplicates"] += 1
            continue
        ver = verify_question(q) if llm.available() else {"verdict": True, "method": "offline-template"}
        q["verified"] = 1 if ver.get("verdict") else 0
        q["verification"] = ver
        q["origin"] = origin
        q["created_at"] = time.time()
        q["norm_hash"] = _hash(q["stem"])
        q["id"] = store.new_id("q_")
        q["generator"] = settings.generator_model.id if llm.available() else "offline-template"
        store.insert("questions", q)
        if q["verified"]:
            stats["verified"] += 1
            accepted_vecs.append(v)
        else:
            stats["rejected"] += 1
    return stats


def _normalize_question(q: dict[str, Any], topic_id: str, tags: dict[str, dict[str, Any]], sub_ids: set[str]) -> dict[str, Any] | None:
    try:
        qtype = str(q.get("type", "")).lower().strip()
        if qtype not in TYPES:
            qtype = "short" if "short" in qtype else "numerical" if "num" in qtype else "mcq" if "mc" in qtype else ""
        stem = str(q.get("stem", "")).strip()
        if not qtype or len(stem) < 15:
            return None
        src_tags = [s for s in (q.get("sources") or []) if s in tags] or list(tags)[:1]
        options = None
        answer = str(q.get("answer", "")).strip()
        mis = q.get("misconceptions") or ({} if qtype == "mcq" else [])
        if qtype == "mcq":
            options = [re.sub(r"^\s*\(?[A-Da-d][).:]\s*", "", str(o)).strip() for o in (q.get("options") or [])][:4]
            if len(options) != 4:
                return None
            answer = mcq_letter(answer)
            if answer not in LETTERS:
                return None
            mis = {k.strip()[:1].upper(): str(v) for k, v in (mis.items() if isinstance(mis, dict) else [])}
        elif qtype == "numerical":
            if parse_number(answer) is None:
                return None
        else:
            if isinstance(mis, dict):
                mis = list(mis.values())
        expl = str(q.get("explanation", "")).strip()
        for t in src_tags:  # rewrite [S1] into unit labels so explanations stay meaningful outside the batch
            expl = expl.replace(f"[{t}]", f"[{tags[t]['label']}]")
        sub = str(q.get("subtopic") or "")
        return {
            "topic_id": topic_id, "subtopic_id": sub if sub in sub_ids else None, "type": qtype,
            "difficulty": int(min(3, max(1, int(q.get("difficulty") or 2)))), "stem": stem, "options": options,
            "answer": answer, "tolerance": float(q.get("tolerance") or 0.0) if qtype == "numerical" else None,
            "explanation": expl, "misconceptions": mis, "unit_ids": [tags[t]["id"] for t in src_tags],
        }
    except (TypeError, ValueError):
        return None


def verify_question(q: dict[str, Any]) -> dict[str, Any]:
    """Cross-model check by the verifier model (different family from the generator)."""
    units = [store.one("SELECT * FROM units WHERE id=?", (u,)) for u in q["unit_ids"]]
    src_text, _ = _sources_text([u for u in units if u])
    spec = settings.verifier_model
    try:
        if q["type"] == "short":
            r = llm.chat_json(spec, "You are a careful exam checker. Reply with JSON only.",
                              SHORT_KEY_PROMPT.format(stem=q["stem"], answer=q["answer"], sources=src_text), max_tokens=1500, temperature=0.0)
            ok = bool(r.get("key_correct")) and bool(r.get("answerable_from_sources", True))
            return {"verdict": ok, "method": "key-check", "model": spec.id, "issues": r.get("issues", "")}
        opts = "\n".join(f"{LETTERS[i]}) {o}" for i, o in enumerate(q["options"] or []))
        fmt = "one letter A-D" if q["type"] == "mcq" else "a decimal number"
        r = llm.chat_json(spec, "You are a careful exam checker. Reply with JSON only.",
                          VERIFY_PROMPT.format(qtype=q["type"], stem=q["stem"], options=opts, sources=src_text, answer_fmt=fmt),
                          max_tokens=2500, temperature=0.0)
        got = r.get("answer")
        agree = mcq_letter(got) == q["answer"] if q["type"] == "mcq" else numbers_match(got, q["answer"], q.get("tolerance"))
        ok = agree and bool(r.get("answerable_from_sources", True))
        return {"verdict": ok, "method": "blind-solve", "model": spec.id, "verifier_answer": str(got)[:60],
                "agree": agree, "issues": str(r.get("issues", ""))[:300]}
    except Exception as e:  # noqa: BLE001
        return {"verdict": False, "method": "error", "issues": str(e)[:200]}


def _offline_questions(topic: dict[str, Any], units: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Deterministic template questions (cloze MCQ) for tests/offline mode."""
    out = []
    rng = random.Random(topic["id"])
    concepts = topic.get("key_concepts") or []
    for i, u in enumerate(units[:n]):
        sents = [s for s in re.split(r"(?<=[.!?])\s+", u["text"]) if 40 < len(s) < 260]
        if not sents:
            continue
        s = sents[0]
        words = [w for w in re.findall(r"[A-Za-z]{6,}", s)]
        if not words:
            continue
        target = max(words, key=len)
        distract = [w for w in {*re.findall(r"[A-Za-z]{6,}", " ".join(x["text"] for x in units))} if w.lower() != target.lower()]
        rng.shuffle(distract)
        opts = [target] + distract[:3]
        if len(opts) < 4:
            continue
        rng.shuffle(opts)
        out.append({
            "topic_id": topic["id"], "subtopic_id": None, "type": "mcq", "difficulty": 1,
            "stem": f"Fill in the blank ({u['label']}): " + s.replace(target, "_____", 1),
            "options": opts, "answer": LETTERS[opts.index(target)], "tolerance": None,
            "explanation": f"The source states: \"{s}\" [{u['label']}]", "misconceptions": {},
            "unit_ids": [u["id"]],
        })
        _ = concepts
    return out


def generate_bank(per_topic: int = 8, workers: int = 3, progress=None) -> list[dict[str, Any]]:
    topics = store.many("SELECT id FROM topics WHERE parent_id IS NULL ORDER BY ord")

    def run(t: dict[str, Any]) -> dict[str, Any]:
        total: dict[str, Any] = {"topic": t["id"], "generated": 0, "verified": 0, "rejected": 0, "duplicates": 0}
        have = (store.one("SELECT COUNT(*) n FROM questions WHERE topic_id=? AND verified=1", (t["id"],)) or {}).get("n", 0)
        used = {u for q in store.many("SELECT unit_ids FROM questions WHERE topic_id=?", (t["id"],)) for u in (q["unit_ids"] or [])}
        seed = have // 3  # new seed -> new generation (and cache key) when topping up an existing bank
        tries = 0
        while have + total["verified"] < per_topic and tries < 4:
            tries += 1
            s = generate_for_topic(t["id"], n=5, seed=seed, exclude_units=used)
            used.update(s.get("unit_ids", []))
            for k in ("generated", "verified", "rejected", "duplicates"):
                total[k] += s[k]
            seed += 1
            if not s.get("unit_ids"):
                used = set()  # all units used once: allow reuse with a new seed
        if progress:
            progress(t["id"], total)
        return total

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(run, topics))


# ---- assessments ---------------------------------------------------------------------------

def _public(q: dict[str, Any]) -> dict[str, Any]:
    t = store.one("SELECT name FROM topics WHERE id=?", (q["topic_id"],)) or {}
    srcs = []
    for uid in q.get("unit_ids") or []:
        u = store.one("SELECT label FROM units WHERE id=?", (uid,))
        if u:
            srcs.append(u["label"])
    return {"id": q["id"], "type": q["type"], "difficulty": q["difficulty"], "stem": q["stem"], "options": q["options"],
            "topic_id": q["topic_id"], "topic": t.get("name"), "subtopic_id": q.get("subtopic_id"), "sources": srcs}


def _seen(student_id: str) -> set[str]:
    return {r["question_id"] for r in store.many("SELECT DISTINCT question_id FROM attempts WHERE student_id=?", (student_id,))}


def _bank(topic_id: str) -> list[dict[str, Any]]:
    return store.many("SELECT * FROM questions WHERE topic_id=? AND verified=1 ORDER BY created_at", (topic_id,))


def choose_question(student_id: str, topic_id: str, qtype: str | None, difficulty: int, exclude: set[str],
                    rng: random.Random, allow_generate: bool = True) -> tuple[dict[str, Any] | None, bool]:
    """Pick an unseen verified question; relax type/difficulty; generate on demand; finally allow a repeat."""
    seen = _seen(student_id) | exclude
    bank = _bank(topic_id)
    tiers = [
        [q for q in bank if q["id"] not in seen and (not qtype or q["type"] == qtype) and q["difficulty"] == difficulty],
        [q for q in bank if q["id"] not in seen and (not qtype or q["type"] == qtype)],
        [q for q in bank if q["id"] not in seen],
    ]
    for tier in tiers:
        if tier:
            tier.sort(key=lambda q: abs(q["difficulty"] - difficulty))
            best = [q for q in tier if abs(q["difficulty"] - difficulty) == abs(tier[0]["difficulty"] - difficulty)]
            return rng.choice(best), False
    if allow_generate and llm.available():
        generate_for_topic(topic_id, n=3, seed=int(time.time()) % 10000, origin="on-demand")
        fresh = [q for q in _bank(topic_id) if q["id"] not in seen]
        if fresh:
            return rng.choice(fresh), False
    rep = [q for q in bank if q["id"] not in exclude]
    return (rng.choice(rep), True) if rep else (None, False)


def create_assessment(student_id: str, kind: str = "quiz", topic_ids: list[str] | None = None, n: int = 6,
                      types: list[str] | None = None, seed: int | None = None, allow_generate: bool = True) -> dict[str, Any]:
    rng = random.Random(seed if seed is not None else time.time())
    all_topics = learner.topic_ids()
    scope = [t for t in (topic_ids or all_topics) if t in all_topics] or all_topics
    types = [t for t in (types or list(TYPES)) if t in TYPES] or list(TYPES)
    state = learner.get_state(student_id)
    plan: list[tuple[str, str | None, int]] = []
    if kind == "diagnostic":
        plan = [(t, "mcq", 2) for t in all_topics]
    elif kind == "mock":
        for i in range(n):
            plan.append((scope[i % len(scope)], types[i % len(types)], (i % 3) + 1))
    else:
        slots = learner.allocate({t: state[t] for t in scope}, learner.prerequisites(), n, focus=min(3, len(scope)))
        for i, t in enumerate(slots):
            qt = types[i % len(types)]
            plan.append((t, qt, learner.pick_difficulty(state[t]["p"], qt)))
    chosen: list[dict[str, Any]] = []
    repeats = 0
    exclude: set[str] = set()
    for t, qt, d in plan:
        q, rep = choose_question(student_id, t, qt, d, exclude, rng, allow_generate=allow_generate)
        if q:
            chosen.append(q)
            exclude.add(q["id"])
            repeats += rep
    aid = store.new_id("as_")
    store.insert("assessments", {"id": aid, "student_id": student_id, "kind": kind,
                                 "scope": {"topics": scope, "types": types, "repeats": repeats},
                                 "question_ids": [q["id"] for q in chosen], "created_at": time.time(), "finished_at": None, "report": None})
    return {"id": aid, "kind": kind, "questions": [_public(q) for q in chosen], "repeats": repeats,
            "plan": [{"topic": t, "type": qt, "difficulty": d} for t, qt, d in plan]}


def grade(assessment_id: str, question_id: str, response: str, student_id: str | None = None, update_learner: bool = True) -> dict[str, Any]:
    a = store.one("SELECT * FROM assessments WHERE id=?", (assessment_id,))
    q = store.one("SELECT * FROM questions WHERE id=?", (question_id,))
    if not a or not q:
        raise ValueError("unknown assessment or question")
    student_id = student_id or a["student_id"]
    units = [u for u in (store.one("SELECT * FROM units WHERE id=?", (uid,)) for uid in q["unit_ids"] or []) if u]
    cites = [citation(u, f"S{i + 1}") for i, u in enumerate(units)]
    misconception = ""
    feedback = ""
    if q["type"] == "mcq":
        letter = mcq_letter(response)
        score = 1.0 if letter == q["answer"] else 0.0
        if not score:
            misconception = (q.get("misconceptions") or {}).get(letter, "") if isinstance(q.get("misconceptions"), dict) else ""
        correct_text = f"{q['answer']}) {q['options'][LETTERS.index(q['answer'])]}" if q.get("options") else q["answer"]
    elif q["type"] == "numerical":
        score = 1.0 if numbers_match(response, q["answer"], q.get("tolerance")) else 0.0
        if not score and isinstance(q.get("misconceptions"), list) and q["misconceptions"]:
            misconception = "Common mistake: " + str(q["misconceptions"][0])
        correct_text = q["answer"]
    else:
        score, feedback, misconception = _grade_short(q, response, units)
        correct_text = q["answer"]
    upd = learner.observe(student_id, q["topic_id"], score, q["difficulty"], q["type"], ref=question_id) if update_learner else {}
    fb = {
        "score": score, "correct": score >= 0.75, "correct_answer": correct_text, "explanation": q.get("explanation", ""),
        "feedback": feedback, "misconception": misconception, "citations": cites, "mastery": upd,
    }
    store.insert("attempts", {"assessment_id": assessment_id, "student_id": student_id, "question_id": question_id,
                              "response": str(response)[:2000], "score": score, "feedback": fb, "ts": time.time()})
    return fb


def _grade_short(q: dict[str, Any], response: str, units: list[dict[str, Any]]) -> tuple[float, str, str]:
    if not str(response).strip():
        return 0.0, "No answer given.", ""
    if llm.available():
        src_text, _ = _sources_text(units)
        try:
            r = llm.chat_json(settings.fast_model, "You are a fair, precise grader. Reply with JSON only.",
                              GRADE_PROMPT.format(stem=q["stem"], answer=q["answer"], sources=src_text, response=response),
                              max_tokens=1500, temperature=0.0)
            score = float(r.get("score", 0))
            score = 1.0 if score >= 0.75 else 0.5 if score >= 0.25 else 0.0
            fb = str(r.get("feedback", ""))
            for i, u in enumerate(units, start=1):
                fb = fb.replace(f"[S{i}]", f"[{u['label']}]")
            return score, fb, str(r.get("misconception", ""))
        except Exception:  # noqa: BLE001
            pass
    key = set(re.findall(r"[a-z]{4,}", q["answer"].lower()))
    got = set(re.findall(r"[a-z]{4,}", str(response).lower()))
    overlap = len(key & got) / max(1, len(key))
    score = 1.0 if overlap >= 0.6 else 0.5 if overlap >= 0.3 else 0.0
    return score, f"Keyword overlap with the model answer: {overlap:.0%} (offline grading).", ""


def report(assessment_id: str) -> dict[str, Any]:
    a = store.one("SELECT * FROM assessments WHERE id=?", (assessment_id,))
    if not a:
        raise ValueError("unknown assessment")
    attempts = store.many("SELECT * FROM attempts WHERE assessment_id=? ORDER BY id", (assessment_id,))
    names = {t["id"]: t["name"] for t in store.many("SELECT id, name FROM topics")}
    per: dict[str, dict[str, Any]] = {}
    misconceptions = []
    for at in attempts:
        q = store.one("SELECT * FROM questions WHERE id=?", (at["question_id"],)) or {}
        tid = q.get("topic_id")
        d = per.setdefault(tid, {"topic_id": tid, "name": names.get(tid, tid), "n": 0, "score": 0.0, "before": None, "after": None})
        d["n"] += 1
        d["score"] += at["score"] or 0
        m = (at["feedback"] or {}).get("mastery") or {}
        if m:
            d["before"] = d["before"] if d["before"] is not None else m.get("before")
            d["after"] = m.get("after")
        fb = at["feedback"] or {}
        if fb.get("misconception"):
            misconceptions.append({"topic": names.get(tid, tid), "question": q.get("stem", "")[:160],
                                   "misconception": fb["misconception"], "citations": fb.get("citations", [])[:1]})
    topics = []
    for d in per.values():
        d["accuracy"] = round(d["score"] / d["n"], 3) if d["n"] else None
        topics.append(d)
    weak = [d for d in topics if (d["accuracy"] or 0) < 0.6 or (d["after"] is not None and d["after"] < 0.5)]
    recs = []
    from .tutor import retrieve

    for d in weak:
        t = store.one("SELECT * FROM topics WHERE id=?", (d["topic_id"],)) or {}
        hits = retrieve(f"{t.get('name', '')}: {t.get('description', '')}", k=2, topic_ids=[d["topic_id"]])
        recs.append({"topic_id": d["topic_id"], "topic": d["name"], "review": [citation(h.unit) for h in hits],
                     "action": f"Review these sources, then take a 5-question quiz on {d['name']}."})
    total = sum(d["score"] for d in topics)
    n = sum(d["n"] for d in topics)
    rep = {"assessment_id": assessment_id, "kind": a["kind"], "score": round(total, 2), "n": n,
           "accuracy": round(total / n, 3) if n else None, "topics": topics, "weak_topics": [d["name"] for d in weak],
           "misconceptions": misconceptions, "recommendations": recs, "repeats": (a.get("scope") or {}).get("repeats", 0)}
    store.update("assessments", "id", assessment_id, {"finished_at": time.time(), "report": rep})
    return rep
