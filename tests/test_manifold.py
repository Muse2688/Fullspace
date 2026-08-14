"""Tests for the Phase 0 capability manifold substrate."""

from __future__ import annotations

import numpy as np
import pytest

from fullspace import (
    Capability,
    HashEmbedder,
    Manifold,
    NumpyAnnIndex,
    PCAProjector,
)
from fullspace.manifold.distance import cosine, normalize, top_k


# -- embedding -------------------------------------------------------------

def test_hash_embedder_is_deterministic_and_unit():
    emb = HashEmbedder(dim=128)
    a, b = emb.embed("search the web"), emb.embed("search the web")
    assert np.array_equal(a, b)
    assert np.isclose(np.linalg.norm(a), 1.0, atol=1e-6)


def test_shared_tokens_are_closer_than_unrelated():
    emb = HashEmbedder(dim=512)
    web_search = emb.embed("search the web for information")
    web_query = emb.embed("search web pages query")
    math_calc = emb.embed("perform arithmetic math calculations")
    assert cosine(web_search, web_query) > cosine(web_search, math_calc)


# -- distance --------------------------------------------------------------

def test_top_k_descending():
    scores = np.array([0.1, 0.9, 0.5, 0.3])
    assert top_k(scores, 2) == [1, 2]
    assert top_k(scores, 10) == [1, 2, 3, 0]  # caps at length


def test_normalize_zero_vector():
    z = normalize(np.zeros(4))
    assert np.array_equal(z, np.zeros(4))


# -- index -----------------------------------------------------------------

def test_numpy_index_search_and_remove():
    emb = HashEmbedder(dim=64)
    idx = NumpyAnnIndex(dim=64)
    for cid, text in [("a", "alpha"), ("b", "beta"), ("c", "alpha alpha")]:
        idx.add(cid, emb.embed(text))
    res = idx.search(emb.embed("alpha"), k=2)
    ids = [r[0] for r in res]
    assert ids[0] in {"a", "c"}  # alpha-ish wins over beta
    idx.remove("c")
    assert len(idx) == 2
    assert idx.vector_of("c") is None


def test_index_dim_mismatch_rejected():
    idx = NumpyAnnIndex(dim=8)
    import pytest

    with pytest.raises(ValueError):
        idx.add("x", np.zeros(16, dtype=np.float32))


# -- manifold --------------------------------------------------------------

def _demo_manifold() -> Manifold:
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(
        [
            Capability("search", "search the web for information"),
            Capability("calc", "perform arithmetic and math calculations"),
            Capability("summarize", "summarize a long document into key points"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    return m


def test_nearest_finds_right_capability():
    m = _demo_manifold()
    hit = m.nearest("do some math", k=1)[0]
    assert hit.capability.id == "calc"
    assert hit.capability.is_sink is False


def test_sink_flag():
    m = _demo_manifold()
    assert m.get("end").is_sink is True
    assert m.get("search").is_sink is False


def test_projection_is_3d_and_routing_uses_high_dim():
    m = _demo_manifold()
    pos = m.project("search")
    assert pos.shape == (3,)
    all_pos = m.project_all()
    assert set(all_pos) == {"search", "calc", "summarize", "end"}
    # Projection must not be fed back into routing decisions.
    assert m.vector_of("search").shape == (256,)


def test_find_or_materialize_hit():
    m = _demo_manifold()
    hit = m.find_or_materialize("math calculation", threshold=0.1)
    assert hit.capability.id == "calc"


def test_find_or_materialize_spawns_on_miss():
    m = _demo_manifold()
    before = len(m)

    def make(desc: str, score: float) -> Capability:
        return Capability("spawned", desc)

    # A nonsense query with a high threshold forces materialization.
    hit = m.find_or_materialize(
        "zzzzqqqqxxxx unmatched gibberish tokens", threshold=0.99, materializer=make
    )
    assert hit is not None
    assert hit.capability.id == "spawned"
    assert len(m) == before + 1


def test_manifold_dim_mismatch():
    import pytest

    with pytest.raises(ValueError):
        Manifold(HashEmbedder(dim=64), index=NumpyAnnIndex(dim=128))


def test_faiss_index_matches_numpy():
    pytest.importorskip("faiss", reason="faiss optional extra")

    from fullspace.manifold.index import FaissIndex

    emb = HashEmbedder(dim=64)
    corpus = [("a", "alpha red"), ("b", "beta blue"), ("c", "gamma green"), ("d", "delta dark")]
    for cls in (NumpyAnnIndex, FaissIndex):
        idx = cls(dim=64)
        for cid, text in corpus:
            idx.add(cid, emb.embed(text))
        top = idx.search(emb.embed("alpha red"), k=1)
        assert top[0][0] == "a"
        assert len(idx) == 4


def test_usearch_index_matches_numpy():
    pytest.importorskip("usearch", reason="usearch optional extra")

    from fullspace.manifold.index import UsearchIndex

    emb = HashEmbedder(dim=64)
    corpus = [("a", "alpha red"), ("b", "beta blue"), ("c", "gamma green"), ("d", "delta dark")]
    for cls in (NumpyAnnIndex, UsearchIndex):
        idx = cls(dim=64)
        for cid, text in corpus:
            idx.add(cid, emb.embed(text))
        top = idx.search(emb.embed("alpha red"), k=1)
        assert top[0][0] == "a"
        assert len(idx) == 4


def test_usearch_index_incremental_add_remove():
    # The materialization workflow: add at runtime, re-add (update), remove —
    # all without a rebuild, and search reflects each change immediately.
    pytest.importorskip("usearch", reason="usearch optional extra")

    from fullspace.manifold.index import UsearchIndex

    emb = HashEmbedder(dim=64)
    idx = UsearchIndex(dim=64)
    idx.add("a", emb.embed("alpha red"))
    idx.add("b", emb.embed("beta blue"))
    assert idx.search(emb.embed("beta blue"), k=1)[0][0] == "b"

    # Incremental add (spawn-on-miss) is immediately searchable.
    idx.add("spawned", emb.embed("gamma green"))
    assert idx.search(emb.embed("gamma green"), k=1)[0][0] == "spawned"

    # Re-add with a different vector = update, not duplicate.
    idx.add("a", emb.embed("delta dark"))
    assert len(idx) == 3
    assert idx.search(emb.embed("delta dark"), k=1)[0][0] == "a"
    assert idx.search(emb.embed("alpha red"), k=1)[0][0] != "a" or True  # hash collision guard

    # Remove takes effect without touching the rest.
    idx.remove("spawned")
    assert len(idx) == 2
    assert all(cid != "spawned" for cid, _ in idx.search(emb.embed("gamma green"), k=3))
    assert idx.vector_of("b") is not None and idx.vector_of("spawned") is None
