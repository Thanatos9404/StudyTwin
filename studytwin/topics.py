"""Course topic map: major topics -> subtopics -> key concepts, with prerequisites.

1. A compact digest of every source (section headings, slide titles, timestamped transcript
   openings) is compressed with LLMSlim and sent to the LLM, which proposes the topic map.
2. Every knowledge unit is tagged to its closest subtopic (embedding similarity) and to the key
   concepts it mentions, so citations, questions and mastery all share one topic vocabulary.
Offline fallback: textbook section headings become topics, with sequential prerequisites.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from . import llm, store
from .config import settings
from .embed import get_embedder
from .ingest.video import fmt_ts

TOPIC_PROMPT = """You are designing the topic map for a study companion. Below is a digest of ALL course
material (textbook sections, lecture slides and a timestamped lecture transcript).

Produce a JSON object:
{{"topics": [
  {{"id": "T1", "name": "...", "description": "one sentence", "key_concepts": ["...", "..."],
    "prerequisites": [],
    "subtopics": [{{"id": "T1.1", "name": "...", "description": "one sentence", "key_concepts": ["..."]}}]}}
]}}
Rules:
- {n_min}-{n_max} major topics in a sensible teaching order; 2-4 subtopics each; 3-6 key concepts each
  (short noun phrases that literally appear in the material, e.g. "sample space", "Bayes' rule").
- prerequisites: ids of earlier major topics that must be understood first (a DAG, no cycles).
- Only include topics actually covered by the digest. Ignore administrative content (grading, schedules).
- Every textbook section, every slide deck and the lecture transcript must map to at least one topic or subtopic.
- Output compact (minified) JSON with no extra whitespace; keep descriptions under 20 words.

DIGEST:
{digest}"""


def has_topics() -> bool:
    return bool(store.one("SELECT id FROM topics LIMIT 1"))


def _digest() -> str:
    lines: list[str] = []
    for src in store.many("SELECT * FROM sources ORDER BY created_at"):
        units = store.many("SELECT * FROM units WHERE source_id=? ORDER BY ord", (src["id"],))
        lines.append(f"## {src['kind'].upper()}: {src['title']}")
        if src["kind"] == "textbook":
            per_sec: dict[str, list[str]] = {}
            for u in units:
                if u["kind"] == "text" and len(u["text"].split()) > 12:
                    per_sec.setdefault(u["section"] or "Introduction", []).append(u["text"])
            for sec, texts in per_sec.items():
                step = max(1, len(texts) // 4)
                sample = " ... ".join(" ".join(t.split()[:45]) for t in texts[::step][:4])
                lines.append(f"- Section {sec} ({src['title'][:40]}): {sample}")
            for u in units:
                if u["kind"] == "figure":
                    lines.append(f"- Figure ({u['label']}): {' '.join(u['text'].split()[:30])}")
        elif src["kind"] == "slides":
            for u in units:
                if u["kind"] == "slide":
                    lines.append(f"- {u['label']}: {' '.join(u['text'].split()[:30])}")
        else:
            for u in units:
                lines.append(f"- [{fmt_ts(u['loc']['start'])}] {' '.join(u['text'].split()[:30])}")
    return "\n".join(lines)


def build_topics(n_min: int = 6, n_max: int = 7) -> dict[str, Any]:
    """(Re)build the topic map and tag all units. Returns stats for logging/UI."""
    digest = _digest()
    stats: dict[str, Any] = {"digest_tokens_est": len(digest) // 4}
    data = None
    if llm.available():
        if settings.use_llmslim and len(digest) // 4 > 6000:
            from llmslim import compress

            res = compress(digest, target_ratio=max(0.35, 6000 / (len(digest) / 4)),
                           query="course topics, key concepts and prerequisites")
            stats.update({"llmslim_before": res.original_tokens, "llmslim_after": res.compressed_tokens})
            digest = res.compressed_text
        try:
            data = llm.chat_json(settings.generator_model, "You are an expert curriculum designer. Reply with JSON only.",
                                 TOPIC_PROMPT.format(digest=digest, n_min=n_min, n_max=n_max), max_tokens=9000, temperature=0.1)
        except Exception as e:  # noqa: BLE001
            stats["llm_error"] = str(e)[:200]
            data = None
    topics = _normalize(data) if data else _fallback_topics()
    stats["method"] = "llm" if data else "headings"
    store.execute("DELETE FROM topics")
    rows = []
    for i, t in enumerate(topics):
        rows.append({"id": t["id"], "name": t["name"], "parent_id": None, "description": t.get("description", ""),
                     "key_concepts": t.get("key_concepts", []), "prerequisites": t.get("prerequisites", []), "ord": i})
        for j, s in enumerate(t.get("subtopics", [])):
            rows.append({"id": s["id"], "name": s["name"], "parent_id": t["id"], "description": s.get("description", ""),
                         "key_concepts": s.get("key_concepts", []), "prerequisites": [], "ord": j})
    store.insert_many("topics", rows, replace=True)
    tag_units()
    stats["topics"] = len(topics)
    stats["subtopics"] = sum(len(t.get("subtopics", [])) for t in topics)
    return stats


def _normalize(data: Any) -> list[dict[str, Any]]:
    items = data.get("topics", []) if isinstance(data, dict) else data
    out: list[dict[str, Any]] = []
    ids = set()
    for i, t in enumerate(items or [], start=1):
        tid = f"T{i}"
        old_id = str(t.get("id", tid))
        subs = []
        for j, s in enumerate(t.get("subtopics", []) or [], start=1):
            subs.append({"id": f"{tid}.{j}", "name": str(s.get("name", f"Subtopic {j}"))[:80],
                         "description": str(s.get("description", ""))[:300],
                         "key_concepts": [str(c)[:60] for c in (s.get("key_concepts") or [])][:6]})
        out.append({"id": tid, "_old": old_id, "name": str(t.get("name", tid))[:80],
                    "description": str(t.get("description", ""))[:300],
                    "key_concepts": [str(c)[:60] for c in (t.get("key_concepts") or [])][:8],
                    "prerequisites": [str(p) for p in (t.get("prerequisites") or [])], "subtopics": subs})
        ids.add(tid)
    remap = {t["_old"]: t["id"] for t in out}
    order = {t["id"]: i for i, t in enumerate(out)}
    for t in out:
        prereq = [remap.get(p, p) for p in t["prerequisites"]]
        t["prerequisites"] = [p for p in prereq if p in ids and order[p] < order[t["id"]]]  # keep it a DAG
    if not out:
        raise ValueError("empty topic map")
    return out


def _fallback_topics() -> list[dict[str, Any]]:
    secs: list[str] = []
    for u in store.many("SELECT section FROM units u JOIN sources s ON s.id=u.source_id WHERE s.kind='textbook' ORDER BY s.created_at, u.ord"):
        sec = (u["section"] or "").strip()
        if sec and sec not in secs and not re.search(r"introduction|lab|probability topics$", sec, re.I):
            secs.append(sec)
    if not secs:
        secs = sorted({(u["section"] or "General").strip() for u in store.many("SELECT section FROM units")})[:6] or ["General"]
    out = []
    for i, sec in enumerate(secs, start=1):
        name = re.sub(r"^\d+(\.\d+)*\s*", "", sec)
        words = [w for w in re.findall(r"[A-Za-z]+", name) if len(w) > 3]
        out.append({"id": f"T{i}", "name": name, "description": f"Material from section {sec}.",
                    "key_concepts": [w.lower() for w in words][:4], "prerequisites": [f"T{i - 1}"] if i > 1 else [],
                    "subtopics": []})
    return out


def _descriptor(t: dict[str, Any]) -> str:
    return f"{t['name']}. {t.get('description', '')} Key concepts: {', '.join(t.get('key_concepts') or [])}"


def tag_units(unit_ids: list[str] | None = None) -> int:
    """Assign each unit to its closest subtopic (or topic) and to the key concepts it mentions."""
    topics = store.many("SELECT * FROM topics ORDER BY ord")
    if not topics:
        return 0
    leaves = [t for t in topics if t["parent_id"]] or [t for t in topics if not t["parent_id"]]
    parents = {t["id"]: t for t in topics if not t["parent_id"]}
    emb = get_embedder()
    leaf_vecs = emb.encode([_descriptor(t) for t in leaves], query=True)
    all_concepts = sorted({c for t in topics for c in (t.get("key_concepts") or [])}, key=len, reverse=True)
    if unit_ids is None:
        units = store.many("SELECT u.id, u.text, u.section, u.label, v.vec FROM units u LEFT JOIN unit_vecs v ON v.unit_id=u.id")
    else:
        qs = ",".join("?" for _ in unit_ids)
        units = store.many(f"SELECT u.id, u.text, u.section, u.label, v.vec FROM units u LEFT JOIN unit_vecs v ON v.unit_id=u.id WHERE u.id IN ({qs})", tuple(unit_ids))
    updates = []
    for u in units:
        if u["vec"] is None:
            uv = emb.encode([f"{u['section'] or ''}\n{u['text']}"])[0]
        else:
            uv = np.frombuffer(u["vec"], dtype=np.float32)
        sims = leaf_vecs @ uv
        # lexical boost: concepts of the leaf that literally appear in the unit
        low = u["text"].lower()
        for li, leaf in enumerate(leaves):
            hits = sum(1 for c in (leaf.get("key_concepts") or []) if c.lower() in low)
            sims[li] += 0.03 * min(hits, 3)
        best = leaves[int(np.argmax(sims))]
        topic_id = best["parent_id"] or best["id"]
        sub_id = best["id"] if best["parent_id"] else None
        concepts = [c for c in all_concepts if c.lower() in low][:6]
        updates.append((topic_id, sub_id, __import__("json").dumps(concepts), u["id"]))
    with store.db() as c:
        c.executemany("UPDATE units SET topic_id=?, subtopic_id=?, concepts=? WHERE id=?", updates)
    _ = parents
    return len(updates)


def topic_tree() -> list[dict[str, Any]]:
    topics = store.many("SELECT * FROM topics ORDER BY ord")
    counts = store.many(
        "SELECT u.topic_id, u.subtopic_id, s.kind, COUNT(*) n FROM units u JOIN sources s ON s.id=u.source_id GROUP BY 1,2,3"
    )
    out = []
    for t in [x for x in topics if not x["parent_id"]]:
        cov: dict[str, int] = {}
        for c in counts:
            if c["topic_id"] == t["id"]:
                cov[c["kind"]] = cov.get(c["kind"], 0) + c["n"]
        subs = []
        for s in [x for x in topics if x["parent_id"] == t["id"]]:
            n = sum(c["n"] for c in counts if c["subtopic_id"] == s["id"])
            subs.append({**s, "units": n})
        out.append({**t, "subtopics": subs, "coverage": cov})
    return out


def mermaid(mastery: dict[str, float] | None = None) -> str:
    tree = topic_tree()
    lines = ["flowchart LR"]
    for t in tree:
        label = t["name"].replace('"', "'")
        p = (mastery or {}).get(t["id"])
        suffix = f"<br/>{round(p * 100)}% mastery" if p is not None else ""
        lines.append(f'  {t["id"].replace(".", "_")}["{label}{suffix}"]')
    for t in tree:
        for p in t.get("prerequisites") or []:
            lines.append(f"  {p.replace('.', '_')} --> {t['id'].replace('.', '_')}")
    if mastery:
        lines += ["  classDef weak fill:#fde2e1,stroke:#d9534f,color:#5a1a17",
                  "  classDef mid fill:#fff3cd,stroke:#e0a800,color:#5c4400",
                  "  classDef strong fill:#d4edda,stroke:#28a745,color:#14451f"]
        for t in tree:
            p = mastery.get(t["id"], 0.0)
            cls = "strong" if p >= 0.8 else "mid" if p >= 0.5 else "weak"
            lines.append(f"  class {t['id'].replace('.', '_')} {cls}")
    return "\n".join(lines)
