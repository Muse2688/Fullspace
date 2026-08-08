"""Vector distance / affinity helpers (cosine-based).

Embeddings are unit-normalized, so cosine similarity reduces to a dot product.
These helpers are kept dependency-light (numpy only) and used by both the
index and the routing layer.
"""

from __future__ import annotations

import numpy as np


def normalize(v: np.ndarray) -> np.ndarray:
    """L2-normalize a vector; the zero vector is returned unchanged."""
    v = np.asarray(v, dtype=np.float32)
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two vectors in [-1, 1]."""
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def cosine_to_all(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity of one query vector vs each row of ``matrix``.

    Returns an array of shape (matrix.shape[0],).
    """
    matrix = np.asarray(matrix, dtype=np.float32)
    if matrix.shape[0] == 0:
        return np.zeros((0,), dtype=np.float32)
    q = normalize(query)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1e-12
    unit = matrix / norms
    return unit @ q


def affinity(score: float) -> float:
    """Map cosine similarity [-1, 1] to affinity [0, 1]."""
    return (float(score) + 1.0) / 2.0


def top_k(scores: np.ndarray, k: int) -> list[int]:
    """Indices of the top-k scores, descending. Caps at len(scores)."""
    n = scores.shape[0]
    k = min(k, n)
    if k <= 0:
        return []
    part = np.argpartition(-scores, k - 1)[:k]
    return part[np.argsort(-scores[part])].tolist()
