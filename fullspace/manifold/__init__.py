"""The capability manifold substrate.

    embedding  — description -> unit high-dim vector (pluggable backend)
    distance   — cosine / affinity / top-k helpers
    index      — ANN over capability vectors (numpy reference; FAISS optional)
    projection — high-dim -> 3D, for visualization only (never for routing)
    manifold   — facade tying them together + spawn-on-miss materialization
    types      — Capability, Hit dataclasses
"""

from fullspace.manifold.distance import affinity, cosine, cosine_to_all, normalize, top_k
from fullspace.manifold.embedding import Embedder, HashEmbedder
from fullspace.manifold.index import AnnIndex, NumpyAnnIndex
from fullspace.manifold.manifold import Manifold
from fullspace.manifold.projection import PCAProjector, Projector
from fullspace.manifold.types import Capability, Hit

__all__ = [
    "Capability",
    "Hit",
    "Embedder",
    "HashEmbedder",
    "affinity",
    "cosine",
    "cosine_to_all",
    "normalize",
    "top_k",
    "AnnIndex",
    "NumpyAnnIndex",
    "Projector",
    "PCAProjector",
    "Manifold",
]
