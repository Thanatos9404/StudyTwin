"""Personalization evaluation with simulated students (no LLM calls, fully reproducible).

Each simulated student has a hidden "true" knowledge state per topic (known / not known). Answering a
question (with feedback) on an unknown topic teaches it with probability p_learn (halved when a
prerequisite topic is still unknown); between sessions a known topic is forgotten with a small
probability. Answers are correct with probability 1 - slip(difficulty) when known and guess(type)
otherwise, using the same slip/guess values as the learner model.

The REAL verified question bank (topics, types, difficulties, ids) and the REAL StudyTwin policy
functions (BKT update, priorities, difficulty choice, no-repeat selection) are used. Baselines:

* random_with_repeats - uniform random questions from the whole bank (a typical static quiz app)
* random_no_repeat    - uniform random unseen questions (isolates the effect of targeting)

Reported per profile x policy (mean over seeds): true mastery at start/end and gain, BKT tracking
error (mean |P(known) - truth|) after the first and the last session, and question repetition rate.

    python -m studytwin.eval.simulate
"""

from __future__ import annotations

import json
import random
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import learner, store
from ..config import ROOT

OUT = ROOT / "eval" / "results"
SESSIONS = 6
PER_SESSION = 8
SEEDS = 40
FORGET = 0.04
TRUE_SLIP = {1: 0.05, 2: 0.10, 3: 0.20}
TRUE_GUESS = {"mcq": 0.25, "numerical": 0.03, "short": 0.10}


@dataclass
class Profile:
    name: str
    p0: dict[str, float]  # probability each topic is known at the start
    p_learn: float
    description: str


def profiles(topics: list[str]) -> list[Profile]:
    first_half = set(topics[: max(1, len(topics) // 2)])
    return [
        Profile("novice", {t: 0.10 for t in topics}, 0.18, "knows little; average learner"),
        Profile("uneven", {t: (0.85 if t in first_half else 0.10) for t in topics}, 0.18, "strong on early topics, weak on later ones"),
        Profile("strong", {t: 0.70 for t in topics}, 0.18, "knows most topics already"),
        Profile("slow_learner", {t: 0.20 for t in topics}, 0.08, "learns slowly from each question"),
    ]


def simulate_student(policy: str, prof: Profile, bank: list[dict[str, Any]], topics: list[str], prereq: dict[str, list[str]],
                     seed: int) -> dict[str, Any]:
    rng = random.Random(f"{policy}-{prof.name}-{seed}")
    truth_rng = random.Random(f"truth-{prof.name}-{seed}")  # same initial truth for every policy
    truth = {t: truth_rng.random() < prof.p0[t] for t in topics}
    start = sum(truth.values()) / len(topics)
    est = {t: learner.DEFAULT_PRIOR for t in topics}
    seen: set[str] = set()
    served = 0
    repeats = 0
    mae_by_session: list[float] = []
    mastery_by_session: list[float] = [start]
    by_topic: dict[str, list[dict[str, Any]]] = {}
    for q in bank:
        by_topic.setdefault(q["topic_id"], []).append(q)

    def answer(q: dict[str, Any]) -> float:
        t = q["topic_id"]
        if truth[t]:
            p = 1 - TRUE_SLIP.get(q["difficulty"], 0.1)
        else:
            p = TRUE_GUESS.get(q["type"], 0.1)
        correct = 1.0 if rng.random() < p else 0.0
        if not truth[t]:  # learning from practice + feedback
            pl = prof.p_learn * (0.5 if any(not truth.get(pq, True) for pq in prereq.get(t, [])) else 1.0)
            if rng.random() < pl:
                truth[t] = True
        return correct

    for s in range(SESSIONS):
        picks: list[dict[str, Any]] = []
        if policy == "studytwin_adaptive":
            if s == 0:  # cold start: diagnostic, one medium question per topic
                plan = [(t, "mcq", 2) for t in topics][:PER_SESSION]
            else:
                state = {t: {"p": est[t], "last_ts": None, "half_life": 1.0} for t in topics}
                pri = learner.priorities(state, prereq)
                order = sorted(topics, key=lambda t: -pri[t])
                total = sum(pri.values()) or 1.0
                counts = {t: int(pri[t] / total * PER_SESSION) for t in topics}
                for t in order[: PER_SESSION - sum(counts.values())]:
                    counts[t] += 1
                types = ["mcq", "numerical", "short"]
                plan = []
                i = 0
                for t in order:
                    for _ in range(counts[t]):
                        qt = types[i % 3]
                        plan.append((t, qt, learner.pick_difficulty(est[t], qt)))
                        i += 1
            for t, qt, d in plan:
                q = _choose(by_topic, t, qt, d, seen, picks, topics, est, rng)
                picks.append(q)
        elif policy == "random_no_repeat":
            pool = [q for q in bank if q["id"] not in seen]
            rng.shuffle(pool)
            picks = pool[:PER_SESSION]
            while len(picks) < PER_SESSION:
                picks.append(rng.choice(bank))
        else:  # random_with_repeats
            picks = [rng.choice(bank) for _ in range(PER_SESSION)]
        for q in picks:
            served += 1
            repeats += q["id"] in seen
            seen.add(q["id"])
            score = answer(q)
            est[q["topic_id"]] = learner.bkt_update(est[q["topic_id"]], score, q["difficulty"], q["type"])
        mae_by_session.append(sum(abs(est[t] - (1.0 if truth[t] else 0.0)) for t in topics) / len(topics))
        # forgetting between sessions
        for t in topics:
            if truth[t] and rng.random() < FORGET:
                truth[t] = False
        mastery_by_session.append(sum(truth.values()) / len(topics))
    return {"start": start, "end": mastery_by_session[-1], "mae": mae_by_session, "curve": mastery_by_session,
            "repeat_rate": repeats / served if served else 0.0}


def _choose(by_topic, t, qt, d, seen, picks, topics, est, rng):
    taken = {p["id"] for p in picks}
    order = [t] + sorted([x for x in topics if x != t], key=lambda x: est[x])
    for topic in order:
        pool = [q for q in by_topic.get(topic, []) if q["id"] not in seen and q["id"] not in taken]
        if not pool:
            continue
        typed = [q for q in pool if q["type"] == qt] or pool
        best = min(abs(q["difficulty"] - d) for q in typed)
        return rng.choice([q for q in typed if abs(q["difficulty"] - d) == best])
    pool = [q for q in by_topic.get(t, []) if q["id"] not in taken] or [q for qs in by_topic.values() for q in qs]
    return rng.choice(pool)  # bank exhausted: a repeat (the live app would generate a new question instead)


def main(argv: list[str]) -> dict[str, Any]:
    bank = store.many("SELECT id, topic_id, type, difficulty FROM questions WHERE verified=1")
    topics = learner.topic_ids()
    prereq = learner.prerequisites()
    if not bank or not topics:
        raise SystemExit("Need a topic map and a verified question bank (run scripts/seed_demo.py).")
    policies = ["studytwin_adaptive", "random_no_repeat", "random_with_repeats"]
    rows = []
    curves: dict[str, list[list[float]]] = {p: [] for p in policies}
    for prof in profiles(topics):
        for pol in policies:
            runs = [simulate_student(pol, prof, bank, topics, prereq, seed) for seed in range(SEEDS)]
            for r in runs:
                curves[pol].append(r["curve"])
            mean = lambda xs: round(statistics.fmean(xs), 4)  # noqa: E731
            rows.append({
                "profile": prof.name, "profile_description": prof.description, "policy": pol,
                "true_start": mean([r["start"] for r in runs]), "true_end": mean([r["end"] for r in runs]),
                "gain": mean([r["end"] - r["start"] for r in runs]),
                "bkt_mae_first": mean([r["mae"][0] for r in runs]), "bkt_mae_last": mean([r["mae"][-1] for r in runs]),
                "bkt_mae_by_session": [mean([r["mae"][i] for r in runs]) for i in range(SESSIONS)],
                "repeat_rate": mean([r["repeat_rate"] for r in runs]), "n_students": len(runs),
            })
            print(f"{prof.name:13s} {pol:20s} true {rows[-1]['true_start']:.2f}->{rows[-1]['true_end']:.2f} "
                  f"gain {rows[-1]['gain']:+.3f} | BKT MAE {rows[-1]['bkt_mae_first']:.3f}->{rows[-1]['bkt_mae_last']:.3f} | "
                  f"repeats {rows[-1]['repeat_rate']:.1%}")
    curve = {p: [round(statistics.fmean(c[i] for c in cs), 4) for i in range(SESSIONS + 1)] for p, cs in curves.items()}
    summary = {}
    for pol in policies:
        rs = [r for r in rows if r["policy"] == pol]
        summary[pol] = {"gain": round(statistics.fmean(r["gain"] for r in rs), 4),
                        "repeat_rate": round(statistics.fmean(r["repeat_rate"] for r in rs), 4),
                        "bkt_mae_first": round(statistics.fmean(r["bkt_mae_first"] for r in rs), 4),
                        "bkt_mae_last": round(statistics.fmean(r["bkt_mae_last"] for r in rs), 4)}
    out = {
        "description": (f"{len(profiles(topics))} simulated student profiles x {SEEDS} students x {SESSIONS} sessions of {PER_SESSION} questions, "
                        f"drawn from the real verified bank ({len(bank)} questions, {len(topics)} topics). Hidden knowledge follows a "
                        f"BKT-style process (learning from practice, halved when a prerequisite is unknown; {FORGET:.0%} forgetting per session). "
                        "Session 1 of the adaptive policy is the cold-start diagnostic."),
        "bank_size": len(bank), "topics": len(topics), "sessions": SESSIONS, "per_session": PER_SESSION, "seeds": SEEDS,
        "rows": rows, "summary": summary, "curve": curve,
        "caveat": "Simulated learners follow the same family of model the tutor assumes (BKT), so these numbers show the policy works as designed, not real-student learning gains.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "simulation.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return out


if __name__ == "__main__":
    main(sys.argv[1:])
