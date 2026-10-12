"""Learner model: Bayesian Knowledge Tracing per topic + forgetting-curve scheduling.

Each (student, topic) keeps P(known). After every graded answer:

    posterior = P(known | obs)   using slip (by difficulty) and guess (by question type)
    p_next    = posterior + (1 - posterior) * P(learn)

Partial credit (0 < score < 1) mixes the correct/incorrect posteriors. Tutor conversations give
*soft* evidence (a weighted, smaller update) when the student's message reveals a misconception,
confusion or correct understanding.

Spaced repetition: every topic also keeps a memory half-life (days) that doubles after a correct
answer and halves after a mistake; predicted retention = 2^(-days_since_practice / half_life).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

from . import store

P_LEARN = 0.12
SLIP = {1: 0.05, 2: 0.10, 3: 0.18}
GUESS = {"mcq": 0.25, "numerical": 0.05, "short": 0.10}
MASTERED = 0.80
DEFAULT_PRIOR = 0.30
INTAKE_PRIOR = {1: 0.10, 2: 0.20, 3: 0.35, 4: 0.55, 5: 0.70}
SOFT_WEIGHT = {"misconception": (0.0, 0.5), "confusion": (0.0, 0.2), "understanding": (1.0, 0.3)}


@dataclass
class BKTParams:
    p_learn: float = P_LEARN

    @staticmethod
    def slip(difficulty: int) -> float:
        return SLIP.get(int(difficulty or 2), 0.10)

    @staticmethod
    def guess(qtype: str) -> float:
        return GUESS.get(qtype or "mcq", 0.15)


def bkt_update(p: float, score: float, difficulty: int = 2, qtype: str = "mcq", p_learn: float = P_LEARN) -> float:
    """Return P(known) after observing a (possibly partial-credit) answer, including learning."""
    s, g = BKTParams.slip(difficulty), BKTParams.guess(qtype)
    p = min(max(p, 1e-4), 1 - 1e-4)
    post_c = p * (1 - s) / (p * (1 - s) + (1 - p) * g)
    post_w = p * s / (p * s + (1 - p) * (1 - g))
    score = min(max(score, 0.0), 1.0)
    post = score * post_c + (1 - score) * post_w
    return post + (1 - post) * p_learn


def p_correct(p: float, difficulty: int = 2, qtype: str = "mcq") -> float:
    return p * (1 - BKTParams.slip(difficulty)) + (1 - p) * BKTParams.guess(qtype)


def retention(last_ts: float | None, half_life_days: float | None, now: float | None = None) -> float:
    if not last_ts:
        return 1.0
    days = max(0.0, ((now or time.time()) - last_ts) / 86400)
    return math.pow(2.0, -days / max(half_life_days or 1.0, 0.25))


# ---- persistence ---------------------------------------------------------------------------

def topic_ids() -> list[str]:
    return [t["id"] for t in store.many("SELECT id FROM topics WHERE parent_id IS NULL ORDER BY ord")]


def get_state(student_id: str) -> dict[str, dict[str, Any]]:
    rows = {r["topic_id"]: r for r in store.many("SELECT * FROM mastery WHERE student_id=?", (student_id,))}
    student = store.one("SELECT intake FROM students WHERE id=?", (student_id,)) or {}
    intake = (student.get("intake") or {}).get("ratings", {}) if isinstance(student.get("intake"), dict) else {}
    out = {}
    for tid in topic_ids():
        r = rows.get(tid)
        if r is None:
            prior = INTAKE_PRIOR.get(int(intake.get(tid, 0) or 0), DEFAULT_PRIOR)
            r = {"student_id": student_id, "topic_id": tid, "p": prior, "n": 0, "correct": 0.0, "last_ts": None, "half_life": 1.0}
        out[tid] = r
    return out


def _save(row: dict[str, Any]) -> None:
    store.insert("mastery", {k: row[k] for k in ("student_id", "topic_id", "p", "n", "correct", "last_ts", "half_life")}, replace=True)


def observe(student_id: str, topic_id: str, score: float, difficulty: int, qtype: str, ref: str = "", event: str = "quiz") -> dict[str, float]:
    state = get_state(student_id)
    if topic_id not in state:
        return {}
    row = state[topic_id]
    before = row["p"]
    row["p"] = bkt_update(before, score, difficulty, qtype)
    row["n"] = int(row["n"] or 0) + 1
    row["correct"] = float(row["correct"] or 0) + score
    hl = float(row.get("half_life") or 1.0)
    row["half_life"] = min(60.0, hl * 2.0) if score >= 0.75 else max(0.5, hl * 0.5) if score < 0.5 else hl
    row["last_ts"] = time.time()
    _save(row)
    store.insert("mastery_log", {"student_id": student_id, "topic_id": topic_id, "ts": time.time(),
                                 "p_before": before, "p_after": row["p"], "event": event, "ref": ref})
    return {"topic_id": topic_id, "before": round(before, 3), "after": round(row["p"], 3)}


def observe_conversation(student_id: str, topic_id: str | None, signal: str, ref: str = "") -> dict[str, float] | None:
    """Soft BKT update from a tutor conversation turn."""
    if not topic_id or signal not in SOFT_WEIGHT:
        return None
    state = get_state(student_id)
    if topic_id not in state:
        return None
    row = state[topic_id]
    before = row["p"]
    score, w = SOFT_WEIGHT[signal]
    full = bkt_update(before, score, 2, "short", p_learn=0.0)
    row["p"] = before + w * (full - before)
    _save(row)
    store.insert("mastery_log", {"student_id": student_id, "topic_id": topic_id, "ts": time.time(),
                                 "p_before": before, "p_after": row["p"], "event": f"chat:{signal}", "ref": ref})
    return {"topic_id": topic_id, "before": round(before, 3), "after": round(row["p"], 3), "signal": signal}


def set_intake(student_id: str, ratings: dict[str, int], goals: str = "") -> None:
    store.update("students", "id", student_id, {"intake": {"ratings": ratings, "goals": goals, "ts": time.time()}})
    for tid, r in ratings.items():
        existing = store.one("SELECT n FROM mastery WHERE student_id=? AND topic_id=?", (student_id, tid))
        if existing and existing["n"]:
            continue  # do not overwrite evidence with self-report
        _save({"student_id": student_id, "topic_id": tid, "p": INTAKE_PRIOR.get(int(r), DEFAULT_PRIOR), "n": 0,
               "correct": 0.0, "last_ts": None, "half_life": 1.0})


# ---- adaptive policy -----------------------------------------------------------------------

def prerequisites() -> dict[str, list[str]]:
    return {t["id"]: (t["prerequisites"] or []) for t in store.many("SELECT id, prerequisites FROM topics WHERE parent_id IS NULL")}


def priorities(state: dict[str, dict[str, Any]], prereq: dict[str, list[str]], now: float | None = None) -> dict[str, float]:
    """Higher = practice sooner. Low mastery, fading memory and ready prerequisites raise priority."""
    out = {}
    for tid, r in state.items():
        p = r["p"]
        ret = retention(r.get("last_ts"), r.get("half_life"), now)
        eff = p * ret
        pri = (1 - eff) + (0.25 if (p >= MASTERED and ret < 0.8) else 0.0)
        blocked = [q for q in prereq.get(tid, []) if q in state and state[q]["p"] < 0.4]
        if blocked:
            pri *= 0.5  # learn the prerequisite first
        out[tid] = pri
    return out


def allocate(state: dict[str, dict[str, Any]], prereq: dict[str, list[str]], n: int, focus: int = 3,
             now: float | None = None) -> list[str]:
    """Topic for each of n quiz slots: concentrate on the `focus` highest-priority topics that are not yet
    mastered (or are due for review), round-robin, so practice goes where the learner model expects gains."""
    pri = priorities(state, prereq, now)
    ranked = sorted(state, key=lambda t: -pri[t])
    open_ = [t for t in ranked if state[t]["p"] < MASTERED or retention(state[t].get("last_ts"), state[t].get("half_life"), now) < 0.8]
    chosen = (open_ or ranked)[: max(1, focus)]
    return [chosen[i % len(chosen)] for i in range(n)]


def pick_difficulty(p: float, qtype: str = "mcq", target: float = 0.7) -> int:
    """Choose the difficulty whose predicted success probability is closest to the target (~70%)."""
    return min((1, 2, 3), key=lambda d: (abs(p_correct(p, d, qtype) - target), d))


def summary(student_id: str) -> list[dict[str, Any]]:
    state = get_state(student_id)
    names = {t["id"]: t["name"] for t in store.many("SELECT id, name FROM topics")}
    out = []
    for tid, r in state.items():
        ret = retention(r.get("last_ts"), r.get("half_life"))
        p = float(r["p"])
        out.append({
            "topic_id": tid, "name": names.get(tid, tid), "p": round(p, 3), "n": int(r["n"] or 0),
            "accuracy": round(float(r["correct"] or 0) / r["n"], 3) if r["n"] else None,
            "retention": round(ret, 3), "half_life_days": round(float(r.get("half_life") or 1.0), 2),
            "level": "mastered" if p >= MASTERED else "developing" if p >= 0.5 else "needs work",
            "due": bool(r.get("last_ts")) and ret < 0.8,
        })
    return out
