"""Local text embeddings.

Default: a small sentence-transformers model (BAAI/bge-small-en-v1.5, 33M params) on CPU.
Set ``STUDYTWIN_EMBEDDER=hash`` for a deterministic, dependency-free hashing embedder used by
the offline test-suite.
"""

from __future__ import annotations

import hashlib
import re
import threading

import numpy as np

from .config import settings

_BGE_QUERY = "Represent this sentence for searching relevant passages: "


class HashEmbedder:
    """Character 3-5 gram + word hashing into a fixed-size normalized vector (deterministic)."""

    name = "hash-512"
    dim = 512

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        t = re.sub(r"\s+", " ", text.lower())
        words = re.findall(r"[a-z0-9]+", t)
        feats = list(words)
        for w in words:
            w2 = f"#{w}#"
            feats += [w2[i : i + n] for n in (3, 4) for i in range(max(0, len(w2) - n + 1))]
        for f in feats:
            h = int.from_bytes(hashlib.md5(f.encode()).digest()[:4], "little")
            v[h % self.dim] += 1.0 if (h >> 31) & 1 else -1.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def encode(self, texts: list[str], query: bool = False) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.stack([self._vec(t) for t in texts])


class STEmbedder:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.name = model_name
        self.model = SentenceTransformer(model_name, device="cpu")
        self.dim = self.model.get_sentence_embedding_dimension()

    def encode(self, texts: list[str], query: bool = False) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        if query and "bge" in self.name.lower():
            texts = [_BGE_QUERY + t for t in texts]
        return self.model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False).astype(np.float32)


_embedder = None
_lock = threading.Lock()


def get_embedder():
    global _embedder
    with _lock:
        if _embedder is None:
            if settings.embedder == "hash":
                _embedder = HashEmbedder()
            else:
                _embedder = STEmbedder(settings.embedder)
    return _embedder


def reset_embedder() -> None:
    global _embedder
    with _lock:
        _embedder = None
