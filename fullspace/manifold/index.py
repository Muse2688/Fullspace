"""Approximate/exact nearest-neighbour index over capability vectors.

``NumpyAnnIndex`` is the exact brute-force reference implementation (fine for
small N, no native deps). At scale, drop in a ``FaissIndex`` (optional) with
the same interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from fullspace.manifold.distance import cosine_to_all, top_k


class AnnIndex(ABC):
    """Nearest-neighbour index keyed by capability id."""

    dim: int

    @abstractmethod
    def add(self, id: str, vector: np.ndarray) -> None:
        """Insert or update the vector for ``id``."""

    @abstractmethod
    def search(self, query: np.ndarray, k: int = 5) -> list[tuple[str, float]]:
        """Return up to k (id, cosine-score) pairs, best first."""

    @abstractmethod
    def remove(self, id: str) -> None:
        """Remove ``id`` from the index (no-op if absent)."""

    @abstractmethod
    def vector_of(self, id: str) -> np.ndarray | None:
        """Return the stored vector for ``id`` or None."""

    @abstractmethod
    def __len__(self) -> int: ...


class NumpyAnnIndex(AnnIndex):
    """Exact brute-force cosine index. Reference implementation.

    Vectors are stored in an ``id -> vector`` map; the (matrix, ids) pair is
    **cached** and only rebuilt when the index mutates, so read-heavy workloads
    (the common routing case) pay the O(N) materialization once, not per query.
    O(N) per query but zero dependencies and exact results — the right default
    until the manifold holds thousands of capabilities.
    """

    def __init__(self, dim: int):
        self.dim = dim
        self._store: dict[str, np.ndarray] = {}
        self._cache: tuple[np.ndarray, list[str]] | None = None
        self._dirty: bool = True

    def add(self, id: str, vector: np.ndarray) -> None:
        v = np.asarray(vector, dtype=np.float32)
        if v.shape != (self.dim,):
            raise ValueError(f"vector shape {v.shape} != index dim ({self.dim},)")
        self._store[id] = v
        self._dirty = True

    def remove(self, id: str) -> None:
        self._store.pop(id, None)
        self._dirty = True

    def _matrix_and_ids(self) -> tuple[np.ndarray, list[str]]:
        if self._cache is None or self._dirty:
            ids = list(self._store.keys())
            matrix = (
                np.vstack([self._store[i] for i in ids])
                if ids
                else np.zeros((0, self.dim), dtype=np.float32)
            )
            self._cache = (matrix, ids)
            self._dirty = False
        return self._cache

    def search(self, query: np.ndarray, k: int = 5) -> list[tuple[str, float]]:
        matrix, ids = self._matrix_and_ids()
        if not ids:
            return []
        scores = cosine_to_all(query, matrix)
        idxs = top_k(scores, k)
        return [(ids[i], float(scores[i])) for i in idxs]

    def vector_of(self, id: str) -> np.ndarray | None:
        v = self._store.get(id)
        return None if v is None else v

    def __len__(self) -> int:
        return len(self._store)


class FaissIndex(AnnIndex):  # pragma: no cover - needs optional faiss-cpu
    """Approximate nearest-neighbour index backed by FAISS (optional).

    Same interface as ``NumpyAnnIndex``; install with ``pip install -e ".[ann-faiss]"``.
    FAISS does not support cheap arbitrary deletion, so removals are handled by
    lazily rebuilding on the next search after any removal.
    """

    def __init__(self, dim: int, nlist: int = 100, nprobe: int = 10):
        import faiss  # type: ignore

        self._faiss = faiss
        self.dim = dim
        self.nlist = nlist
        self.nprobe = nprobe
        self._store: dict[str, np.ndarray] = {}
        self._ids: list[str] = []
        self._index = None
        self._dirty = True

    def _build(self) -> None:
        if not self._store:
            self._ids = []
            self._index = None
            return
        self._ids = list(self._store.keys())
        matrix = np.vstack([self._store[i] for i in self._ids]).astype(np.float32)
        faiss = self._faiss
        n, d = matrix.shape
        if n < self.nlist * 39:
            idx = faiss.IndexFlatIP(d)
        else:
            quantizer = faiss.IndexFlatIP(d)
            idx = faiss.IndexIVFFlat(quantizer, d, self.nlist)
            idx.train(matrix)
            idx.nprobe = self.nprobe
        idx.add(matrix)
        self._index = idx
        self._dirty = False

    def add(self, id: str, vector: np.ndarray) -> None:
        v = np.asarray(vector, dtype=np.float32)
        if v.shape != (self.dim,):
            raise ValueError(f"vector shape {v.shape} != index dim ({self.dim},)")
        self._store[id] = v
        self._dirty = True

    def remove(self, id: str) -> None:
        if id in self._store:
            del self._store[id]
            self._dirty = True

    def search(self, query: np.ndarray, k: int = 5) -> list[tuple[str, float]]:
        if self._dirty:
            self._build()
        if self._index is None or not self._ids:
            return []
        q = np.asarray(query, dtype=np.float32).reshape(1, -1)
        scores, indices = self._index.search(q, min(k, len(self._ids)))
        return [
            (self._ids[i], float(s))
            for s, i in zip(scores[0], indices[0])
            if 0 <= i < len(self._ids)
        ]

    def vector_of(self, id: str) -> np.ndarray | None:
        v = self._store.get(id)
        return None if v is None else v

    def __len__(self) -> int:
        return len(self._store)
