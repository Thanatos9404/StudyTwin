"""Two smaller measured evaluations.

* ASR quality: word error rate of the local faster-whisper transcript of Lecture 2 against the official
  MIT OCW caption file (data/demo/MIT6_041F11_lec02_300k.srt).
* Question bank quality: how many generated questions passed cross-model verification, were rejected,
  or were blocked as near-duplicates; type/difficulty mix per topic.

    python -m studytwin.eval.extras
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .. import store
from ..config import ROOT, settings
from ..ingest.video import parse_caption_file

OUT = ROOT / "eval" / "results"


def _words(text: str) -> list[str]:
    text = text.lower().replace("’", "'")
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", text)  # caption annotations like [LAUGHTER]
    return re.findall(r"[a-z0-9']+", text)


def wer(ref: list[str], hyp: list[str]) -> float:
    """Levenshtein word error rate, O(len(ref) * len(hyp)) with two rows."""
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, start=1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, start=1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1] / max(1, len(ref))


def asr() -> dict | None:
    ref_file = ROOT / "data" / "demo" / "MIT6_041F11_lec02_300k.srt"
    cache = sorted((settings.cache_dir / "transcripts").glob("*.json"))
    if not ref_file.exists() or not cache:
        return None
    data = json.loads(cache[0].read_text(encoding="utf-8"))
    hyp = _words(" ".join(s["text"] for s in data["segments"]))
    ref = _words(" ".join(s.text for s in parse_caption_file(ref_file)))
    meta = data["meta"]
    return {
        "wer": round(wer(ref, hyp), 4), "ref_words": len(ref), "hyp_words": len(hyp),
        "model": f"faster-whisper {meta['model']} (int8, CPU)", "duration_s": meta["duration_s"], "wall_time_s": meta["wall_time_s"],
        "realtime_factor": round(meta["duration_s"] / max(1, meta["wall_time_s"]), 2),
        "note": "Reference = official MIT OCW captions for 6.041 Lecture 2 (lower-cased, punctuation removed). "
                "Includes the OCW intro/outro, which both transcripts contain. Measured on a 12-thread laptop CPU.",
    }


def bank() -> dict:
    rows = store.many("SELECT topic_id, type, difficulty, verified, verification FROM questions")
    gen = len(rows)
    ver = sum(r["verified"] for r in rows)
    methods = Counter((r["verification"] or {}).get("method", "") for r in rows)
    by_topic: dict[str, dict] = {}
    for r in rows:
        d = by_topic.setdefault(r["topic_id"], {"verified": 0, "types": Counter(), "difficulty": Counter()})
        if r["verified"]:
            d["verified"] += 1
            d["types"][r["type"]] += 1
            d["difficulty"][str(r["difficulty"])] += 1
    seed_log = ROOT / "data" / "scratch" / "seed_bank.log"
    dups = None
    if seed_log.exists():
        m = re.findall(r"'duplicates': (\d+)", seed_log.read_text(encoding="utf-8", errors="ignore"))
        dups = sum(int(x) for x in m) if m else None
    return {
        "generated": gen, "verified": ver, "rejected": gen - ver, "verified_rate": round(ver / gen, 4) if gen else None,
        "duplicates": dups, "methods": dict(methods),
        "by_topic": {k: {"verified": v["verified"], "types": dict(v["types"]), "difficulty": dict(v["difficulty"])} for k, v in sorted(by_topic.items())},
        "generator": settings.generator_model.id, "verifier": settings.verifier_model.id,
        "note": "Stored questions only; near-duplicates (embedding cosine >= 0.90 to an existing stem) are dropped before storage. "
                "MCQ and numerical questions are solved blind by the verifier and must match the key (numbers within tolerance); "
                "short answers are checked against the sources. Agreement between two models is not proof of correctness.",
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    a = asr()
    if a:
        (OUT / "asr.json").write_text(json.dumps(a, indent=1), encoding="utf-8")
        print("ASR:", json.dumps(a))
    b = bank()
    (OUT / "question_bank.json").write_text(json.dumps(b, indent=1), encoding="utf-8")
    print("Bank:", json.dumps({k: b[k] for k in ("generated", "verified", "rejected", "verified_rate", "duplicates")}))


if __name__ == "__main__":
    main()
