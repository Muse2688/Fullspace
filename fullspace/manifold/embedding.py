"""Capability description -> unit high-dimensional vector.

The embedder decides *where* each capability sits in the manifold. It is the
single most consequential component for routing quality. A crude dependency-free
``HashEmbedder`` is provided so the framework runs and is testable with no API
keys and no native deps; swap in a real semantic embedder for production.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from collections import OrderedDict

import numpy as np

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class Embedder(ABC):
    """Maps text to a unit-normalized high-dimensional vector."""

    dim: int

    @abstractmethod
    def embed(self, text: str) -> np.ndarray:
        """Return a unit vector of shape (dim,)."""

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self.embed(t) for t in texts])


class CachedEmbedder(Embedder):
    """Memoizing wrapper around any embedder.

    Every routing hop re-embeds an intent string, and intents recur heavily in
    loops (e.g. a ReAct cycle's "act" / "observe" intents). With a neural or
    API-backed embedder each call is a forward pass or network round-trip, so
    caching repeated texts is a large real-world win. With HashEmbedder the win
    is smaller but still measurable, and correctness is identical (embedders are
    pure functions of text).

    Args:
        inner: the wrapped embedder.
        maxsize: max cached texts (FIFO eviction).
    """

    def __init__(self, inner: Embedder, maxsize: int = 4096):
        self._inner = inner
        self.dim = inner.dim
        self._maxsize = maxsize
        self._cache: "OrderedDict[str, np.ndarray]" = OrderedDict()
        self.hits = 0
        self.misses = 0

    def embed(self, text: str) -> np.ndarray:
        cached = self._cache.get(text)
        if cached is not None:
            self.hits += 1
            return cached
        self.misses += 1
        vec = self._inner.embed(text)
        if len(self._cache) >= self._maxsize:
            self._cache.popitem(last=False)  # FIFO evict
        self._cache[text] = vec
        return vec

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self.embed(t) for t in texts])


class HashEmbedder(Embedder):
    """Dependency-free, deterministic embedder via signed feature hashing.

    Crude but *semantically meaningful*: texts sharing tokens land closer
    together (cosine similarity approximates token overlap). Uses md5 hashing
    so the same text always yields the same vector (reproducible, seedable
    by construction). Ideal for tests/demos; swap for a neural embedder in
    production.
    """

    def __init__(self, dim: int = 256):
        if dim <= 0:
            raise ValueError("dim must be positive")
        self.dim = dim

    def embed(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        for tok in _tokenize(text):
            digest = hashlib.md5(tok.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            vec[bucket] += sign
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec


def _optional_embedder(name: str):  # pragma: no cover - import guard helper
    try:
        return __import__(name)
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            f"Optional dependency for {name!r} is not installed. "
            f"Install the relevant extra, e.g. `pip install -e .[embed-st]`."
        ) from e


class SentenceTransformersEmbedder(Embedder):  # pragma: no cover - needs extra
    """Real semantic embeddings via sentence-transformers (optional)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        st = _optional_embedder("sentence_transformers")
        self._model = st.SentenceTransformer(model_name)
        self.dim = int(self._model.get_sentence_embedding_dimension())

    def embed(self, text: str) -> np.ndarray:
        vec = np.asarray(self._model.encode(text, normalize_embeddings=True), dtype=np.float32)
        return vec


class OpenAIEmbedder(Embedder):  # pragma: no cover - needs extra + key
    """Real semantic embeddings via the OpenAI embeddings API (optional)."""

    def __init__(self, model: str = "text-embedding-3-small", dim: int = 1536, client=None):
        self.model = model
        self.dim = dim
        if client is not None:
            self._client = client
        else:
            oa = _optional_embedder("openai")
            self._client = oa.OpenAI()

    def embed(self, text: str) -> np.ndarray:
        resp = self._client.embeddings.create(model=self.model, input=text)
        vec = np.asarray(resp.data[0].embedding, dtype=np.float32)
        n = np.linalg.norm(vec)
        return vec / n if n > 0 else vec
