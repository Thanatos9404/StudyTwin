"""Hybrid retrieval over knowledge units: BM25 (lexical) + dense embeddings, fused with RRF."""

from __future__ import annotations

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np

from . import store
from .embed import get_embedder

_STOP = set(
    "a an the of and or to in on for is are was were be been it this that these those with as by at from "
    "we you i he she they them our your his her its what which who whom how why when where do does did "
    "can could should would will shall may might must not no yes if then else so than there here into "
    "about over under also just only very more most such each any all some one two let us me my".split()
)


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in toks if t not in _STOP and len(t) > 1]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.4, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = docs
        self.N = len(docs)
        self.avgdl = (sum(len(d) for d in docs) / self.N) if self.N else 0.0
        self.tf = [Counter(d) for d in docs]
        df: Counter = Counter()
        for d in docs:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}

    def scores(self, query: list[str]) -> np.ndarray:
        out = np.zeros(self.N, dtype=np.float32)
        for i, tf in enumerate(self.tf):
            dl = len(self.docs[i])
            s = 0.0
            for t in query:
                f = tf.get(t)
                if not f:
                    continue
                s += self.idf.get(t, 0.0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
            out[i] = s
        return out


@dataclass
class Hit:
    unit: dict[str, Any]
    score: float
    dense: float
    lexical: float
    rank: int


class Index:
    def __init__(self) -> None:
        self.units: list[dict[str, Any]] = []
        self.mat = np.zeros((0, 1), dtype=np.float32)
        self.bm25 = BM25([])
        self.by_id: dict[str, dict[str, Any]] = {}

    def build(self) -> "Index":
        units = store.many("SELECT * FROM units ORDER BY source_id, ord")
        emb = get_embedder()
        vec_rows = {r["unit_id"]: r for r in store.many("SELECT unit_id, model, vec FROM unit_vecs")}
        missing = [u for u in units if u["id"] not in vec_rows or vec_rows[u["id"]]["model"] != emb.name]
        if missing:
            vecs = emb.encode([index_text(u) for u in missing])
            store.insert_many(
                "unit_vecs",
                [{"unit_id": u["id"], "model": emb.name, "vec": v.astype(np.float32).tobytes()} for u, v in zip(missing, vecs)],
                replace=True,
            )
            for u, v in zip(missing, vecs):
                vec_rows[u["id"]] = {"vec": v.astype(np.float32).tobytes(), "model": emb.name}
        self.units = units
        self.by_id = {u["id"]: u for u in units}
        if units:
            self.mat = np.stack([np.frombuffer(vec_rows[u["id"]]["vec"], dtype=np.float32) for u in units])
        else:
            self.mat = np.zeros((0, getattr(emb, "dim", 1)), dtype=np.float32)
        self.bm25 = BM25([tokenize(index_text(u)) for u in units])
        return self

    def search(
        self,
        query: str,
        k: int = 6,
        topic_ids: list[str] | None = None,
        kinds: list[str] | None = None,
        source_ids: list[str] | None = None,
        rrf_k: int = 60,
    ) -> list[Hit]:
        if not self.units:
            return []
        qv = get_embedder().encode([query], query=True)[0]
        dense = self.mat @ qv
        lex = self.bm25.scores(tokenize(query))
        mask = np.ones(len(self.units), dtype=bool)
        if topic_ids:
            tset = set(topic_ids)
            mask &= np.array([(u.get("topic_id") in tset) or (u.get("subtopic_id") in tset) for u in self.units])
        if kinds:
            mask &= np.array([u["kind"] in kinds for u in self.units])
        if source_ids:
            mask &= np.array([u["source_id"] in source_ids for u in self.units])
        idx = np.where(mask)[0]
        if len(idx) == 0:
            return []
        d_rank = idx[np.argsort(-dense[idx])]
        l_rank = idx[np.argsort(-lex[idx])]
        fused: dict[int, float] = {}
        for r, i in enumerate(d_rank):
            fused[int(i)] = fused.get(int(i), 0.0) + 1.0 / (rrf_k + r + 1)
        for r, i in enumerate(l_rank):
            if lex[i] <= 0:
                break
            fused[int(i)] = fused.get(int(i), 0.0) + 1.0 / (rrf_k + r + 1)
        order = sorted(fused, key=lambda i: -fused[i])[:k]
        return [Hit(self.units[i], fused[i], float(dense[i]), float(lex[i]), r) for r, i in enumerate(order)]

    def max_dense(self, query: str) -> float:
        if not self.units:
            return 0.0
        qv = get_embedder().encode([query], query=True)[0]
        return float(np.max(self.mat @ qv))


def index_text(u: dict[str, Any]) -> str:
    head = " ".join(x for x in [u.get("section") or "", u.get("label") or ""] if x)
    return f"{head}\n{u['text']}" if head else u["text"]


_index: Index | None = None
_lock = threading.Lock()


def get_index(rebuild: bool = False) -> Index:
    global _index
    with _lock:
        if _index is None or rebuild:
            _index = Index().build()
    return _index


def invalidate() -> None:
    global _index
    with _lock:
        _index = None
