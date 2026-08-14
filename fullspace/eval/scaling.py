"""Routing-latency scaling benchmark: numpy brute-force vs FAISS.

Measures Fullspace's own two ANN indexes against each other as the manifold
grows. With the default numpy index, one Fullspace route is O(N) dot products.
With a sublinear FAISS index (IVFFlat, roughly O(sqrt(N)) probe cost), the
per-hop query cost grows far more slowly — this is what keeps Fullspace's
soft routing viable at manifold scale.

Honesty note: this is *not* a LangGraph comparison. LangGraph's pre-wired
conditional edges are O(1) lookups at any N; their cost does not grow with
graph size. The axis where the FAISS index matters is comparing against
routing strategies that must score N candidates per hop (as Fullspace's
soft routing does by design, in exchange for runtime extensibility).

Run:  python -m fullspace.eval.scaling
"""

from __future__ import annotations

import time

import numpy as np

from fullspace.manifold import HashEmbedder, NumpyAnnIndex
from fullspace.manifold.index import FaissIndex


def _build_corpus(n: int, dim: int) -> tuple[list[str], list[np.ndarray], HashEmbedder]:
    emb = HashEmbedder(dim=dim)
    ids = [f"cap_{i}" for i in range(n)]
    texts = [f"capability {i} domain {i % 17} skill {i % 13} tier {i % 7}" for i in range(n)]
    vecs = [emb.embed(t) for t in texts]
    return ids, vecs, emb


def _make_queries(vecs: list[np.ndarray], n_queries: int, dim: int) -> list[np.ndarray]:
    rng = np.random.default_rng(0)
    qs = []
    for i in range(n_queries):
        base = vecs[int(rng.integers(0, len(vecs)))]
        noise = rng.normal(0, 0.03, dim).astype(np.float32)
        q = base + noise
        n = np.linalg.norm(q)
        qs.append(q / n if n > 0 else q)
    return qs


def _time_per_query(idx, queries: list[np.ndarray], k: int = 1) -> float:
    # Warm up.
    idx.search(queries[0], k=k)
    t0 = time.perf_counter()
    for q in queries:
        idx.search(q, k=k)
    return (time.perf_counter() - t0) * 1000.0 / len(queries)


def run(sizes=(1000, 5000, 20000), n_queries: int = 500, dim: int = 256) -> None:
    print(f"Routing-latency scaling (dim={dim}, queries={n_queries}, per-query ms)\n")
    print(f"{'N':>7} {'numpy(ms)':>12} {'faiss(ms)':>12} {'speedup':>10} {'faiss_idx':>10}")
    print("-" * 55)
    for n in sizes:
        ids, vecs, _emb = _build_corpus(n, dim)
        queries = _make_queries(vecs, n_queries, dim)

        np_idx = NumpyAnnIndex(dim)
        f_idx = FaissIndex(dim)
        for cid, v in zip(ids, vecs):
            np_idx.add(cid, v)
            f_idx.add(cid, v)

        t_np = _time_per_query(np_idx, queries)
        t_fa = _time_per_query(f_idx, queries)
        speedup = t_np / t_fa if t_fa > 0 else float("inf")
        kind = "IVFFlat" if n >= f_idx.nlist * 39 else "FlatIP"
        print(f"{n:>7} {t_np:>12.4f} {t_fa:>12.4f} {speedup:>9.2f}x {kind:>10}")

    print()
    print("Reading: at small N the FAISS FlatIP index is exact (O(N), same as numpy),")
    print("so the gap is just implementation quality. Past the training threshold FAISS")
    print("switches to IVFFlat (sublinear) and Fullspace routing pulls ahead - the")
    print("mechanism that flips the latency axis at scale.")


if __name__ == "__main__":
    run()
