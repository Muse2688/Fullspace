"""The capability manifold — high-dimensional semantic metric space.

This is Fullspace's substrate. Each capability is a point; routing means
"find the nearest capability to the current intent vector". The 3D sphere is
just a projection of this space for human consumption.

The manifold also implements two of the four latency mechanisms from the
design plan:

* **affinity pruning** — ``find_or_materialize`` returns on the first hit above
  a threshold, replacing N router evaluations with one nearest-neighbour query.
* **spawn-on-miss materialization** — when nothing is close enough, a new
  capability is created on demand (the source of Fullspace's emergence win).
"""

from __future__ import annotations

import hashlib
from typing import Callable, Optional, Union

import numpy as np

from fullspace.manifold.embedding import Embedder
from fullspace.manifold.index import AnnIndex, NumpyAnnIndex
from fullspace.manifold.projection import PCAProjector, Projector
from fullspace.manifold.types import Capability, Hit

Query = Union[str, np.ndarray]
Materializer = Callable[[str, float], Capability]


class Manifold:
    """Facade over embedder + ANN index + projector.

    Args:
        embedder: maps descriptions to high-dim unit vectors.
        index: nearest-neighbour index (defaults to a numpy brute-force index).
        projector: high-dim -> 3D for visualization (defaults to PCA).
    """

    def __init__(
        self,
        embedder: Embedder,
        index: AnnIndex | None = None,
        projector: Projector | None = None,
    ):
        self.embedder = embedder
        # NOTE: use explicit `is None`, not `or` — an empty AnnIndex defines
        # __len__ and is therefore falsy, so `index or ...` would silently
        # replace a caller-supplied empty index.
        self.index: AnnIndex = NumpyAnnIndex(embedder.dim) if index is None else index
        self.projector: Projector = PCAProjector() if projector is None else projector
        if self.index.dim != embedder.dim:
            raise ValueError(
                f"index dim {self.index.dim} != embedder dim {embedder.dim}"
            )
        self._caps: dict[str, Capability] = {}
        self._projection_dirty = True

    # -- registration -------------------------------------------------------

    def register(self, capability: Capability) -> Capability:
        """Embed a capability's description and index its position."""
        vector = self.embedder.embed(capability.description)
        capability.vector = vector
        self._caps[capability.id] = capability
        self.index.add(capability.id, vector)
        self._projection_dirty = True
        return capability

    def register_many(self, capabilities: list[Capability]) -> list[Capability]:
        return [self.register(c) for c in capabilities]

    def remove(self, capability_id: str) -> None:
        self._caps.pop(capability_id, None)
        self.index.remove(capability_id)
        self._projection_dirty = True

    # -- querying -----------------------------------------------------------

    def _as_vector(self, query: Query) -> np.ndarray:
        if isinstance(query, str):
            return self.embedder.embed(query)
        return np.asarray(query, dtype=np.float32)

    def nearest(self, query: Query, k: int = 5) -> list[Hit]:
        """Return the k closest capabilities to ``query`` (text or vector)."""
        q = self._as_vector(query)
        results = self.index.search(q, k=k)
        return [
            Hit(self._caps[cid], score)
            for cid, score in results
            if cid in self._caps
        ]

    def find_or_materialize(
        self,
        query: Query,
        threshold: float = 0.5,
        k: int = 1,
        materializer: Optional[Materializer] = None,
    ) -> Optional[Hit]:
        """Affinity pruning + spawn-on-miss.

        If the best match scores at least ``threshold``, return it immediately
        (one query replaces many router evaluations). Otherwise, if a
        ``materializer`` is supplied, create and register a new capability for
        the query and return it. Returns None only when the manifold is empty
        and no materializer can help.
        """
        hits = self.nearest(query, k=k)
        if hits and hits[0].score >= threshold:
            return hits[0]
        if materializer is None:
            return hits[0] if hits else None
        # Deterministic across processes (builtin hash() is PYTHONHASHSEED-salted).
        description = (
            query
            if isinstance(query, str)
            else f"materialized:{hashlib.sha1(query.tobytes()).hexdigest()[:12]}"
        )
        best_score = hits[0].score if hits else 0.0
        capability = materializer(description, best_score)
        self.register(capability)
        return Hit(capability, 1.0)

    # -- introspection ------------------------------------------------------

    def get(self, capability_id: str) -> Optional[Capability]:
        return self._caps.get(capability_id)

    def vector_of(self, capability_id: str) -> Optional[np.ndarray]:
        cap = self._caps.get(capability_id)
        return None if cap is None or cap.vector is None else cap.vector

    def __contains__(self, capability_id: object) -> bool:
        return capability_id in self._caps

    def __len__(self) -> int:
        return len(self._caps)

    @property
    def capabilities(self) -> dict[str, Capability]:
        return dict(self._caps)

    # -- projection (visualization only) ------------------------------------

    def _ensure_projector_fitted(self) -> None:
        if not self._projection_dirty:
            return
        vectors = (
            np.vstack([c.vector for c in self._caps.values() if c.vector is not None])
            if self._caps
            else np.zeros((0, self.embedder.dim), dtype=np.float32)
        )
        self.projector.fit(vectors)
        self._projection_dirty = False

    def project(self, capability_id: str) -> np.ndarray:
        """3D position of a capability on the navigable sphere (viz only)."""
        self._ensure_projector_fitted()
        v = self.vector_of(capability_id)
        if v is None:
            return np.zeros(3, dtype=np.float32)
        return self.projector.project(v)

    def project_all(self) -> dict[str, np.ndarray]:
        """3D positions of all capabilities (for rendering the sphere)."""
        self._ensure_projector_fitted()
        return {
            cid: self.projector.project(c.vector)
            for cid, c in self._caps.items()
            if c.vector is not None
        }
