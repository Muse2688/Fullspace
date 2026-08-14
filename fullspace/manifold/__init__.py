"""The capability manifold substrate.

    embedding  — description -> unit high-dim vector (pluggable backend)
    distance   — cosine / top-k helpers
    index      — ANN over capability vectors (numpy reference; FAISS optional)
    projection — high-dim -> 3D, for visualization only (never for routing)
    manifold   — facade tying them together + spawn-on-miss materialization
    types      — Capability, Hit dataclasses

Optional extras-backed classes are importable from here too (lazily): raising
a helpful ImportError only if you actually instantiate them without the extra:

    SentenceTransformersEmbedder / OpenAIEmbedder / Model2VecEmbedder
                                                    (embed-st / embed-openai / embed-m2v)
    UsearchIndex / FaissIndex                        (ann-usearch / ann-faiss)
    UMAPProjector                                    (proj-umap)
"""

from typing import Any

from fullspace.manifold.distance import cosine, cosine_to_all, normalize, top_k
from fullspace.manifold.embedding import CachedEmbedder, Embedder, HashEmbedder
from fullspace.manifold.index import AnnIndex, NumpyAnnIndex
from fullspace.manifold.manifold import Manifold
from fullspace.manifold.projection import PCAProjector, Projector
from fullspace.manifold.types import Capability, Hit

__all__ = [
    "Capability",
    "Hit",
    "Embedder",
    "HashEmbedder",
    "CachedEmbedder",
    "cosine",
    "cosine_to_all",
    "normalize",
    "top_k",
    "AnnIndex",
    "NumpyAnnIndex",
    "Projector",
    "PCAProjector",
    "Manifold",
    # lazily re-exported (need optional extras at instantiation time)
    "SentenceTransformersEmbedder",
    "OpenAIEmbedder",
    "Model2VecEmbedder",
    "UsearchIndex",
    "FaissIndex",
    "UMAPProjector",
]

_LAZY_OPTIONAL: dict[str, str] = {
    "SentenceTransformersEmbedder": "fullspace.manifold.embedding",
    "OpenAIEmbedder": "fullspace.manifold.embedding",
    "Model2VecEmbedder": "fullspace.manifold.embedding",
    "UsearchIndex": "fullspace.manifold.index",
    "FaissIndex": "fullspace.manifold.index",
    "UMAPProjector": "fullspace.manifold.projection",
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_OPTIONAL:
        import importlib

        attr = getattr(importlib.import_module(_LAZY_OPTIONAL[name]), name)
        globals()[name] = attr  # cache for subsequent lookups
        return attr
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
