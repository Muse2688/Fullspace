"""High-dimensional -> 3D projection, for visualization/navigation only.

The 3D sphere is how humans see and navigate the manifold. **Routing never
uses the projection** — it always operates in the high-dimensional space.
``PCAProjector`` is a deterministic, zero-dependency default; ``UMAPProjector``
is an optional non-linear alternative.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class Projector(ABC):
    """Projects high-dim vectors to 3D for human navigation/visualization."""

    @abstractmethod
    def fit(self, vectors: np.ndarray) -> "Projector":
        """Fit on a (n, d) matrix of vectors."""

    @abstractmethod
    def project(self, vector: np.ndarray) -> np.ndarray:
        """Project a single high-dim vector to a length-3 array."""


class PCAProjector(Projector):
    """Deterministic PCA to 3 components. Zero dependencies.

    Preserves the global directions of greatest variance. Good enough as a
    navigable "world map"; pair with UMAP for non-local structure if desired.
    """

    def __init__(self):
        self._mean: np.ndarray = np.zeros(0, dtype=np.float32)
        self._components: np.ndarray | None = None  # shape (3, d)

    def fit(self, vectors: np.ndarray) -> "PCAProjector":
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.shape[0] == 0:
            self._mean = np.zeros(0, dtype=np.float32)
            self._components = None
            return self
        self._mean = vectors.mean(axis=0)
        centered = vectors - self._mean
        # SVD rank is bounded by the smaller dimension, so cap k at both.
        k = min(3, min(centered.shape))
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
        comps = vt[:k]
        if k < 3:  # pad with zero directions so output is always length-3
            pad = np.zeros((3 - k, centered.shape[1]), dtype=np.float32)
            comps = np.vstack([comps, pad]).astype(np.float32)
        self._components = comps.astype(np.float32)
        return self

    def project(self, vector: np.ndarray) -> np.ndarray:
        if self._components is None or self._mean.shape == (0,):
            return np.zeros(3, dtype=np.float32)
        v = np.asarray(vector, dtype=np.float32) - self._mean
        return self._components @ v


class UMAPProjector(Projector):  # pragma: no cover - needs optional umap-learn
    """Non-linear projection to 3D via UMAP (optional).

    Preserves local neighbourhood structure better than PCA, at the cost of a
    dependency and non-determinism (set ``random_state`` for reproducibility).
    """

    def __init__(self, n_neighbors: int = 15, random_state: int = 0):
        self.n_neighbors = n_neighbors
        self.random_state = random_state
        self._model: Any = None

    def fit(self, vectors: np.ndarray) -> "UMAPProjector":
        import umap  # type: ignore

        self._model = umap.UMAP(
            n_components=3,
            n_neighbors=self.n_neighbors,
            random_state=self.random_state,
        )
        self._model.fit(np.asarray(vectors, dtype=np.float32))
        return self

    def project(self, vector: np.ndarray) -> np.ndarray:
        if self._model is None:
            return np.zeros(3, dtype=np.float32)
        return np.asarray(
            self._model.transform(np.asarray(vector, dtype=np.float32).reshape(1, -1))[0],
            dtype=np.float32,
        )
