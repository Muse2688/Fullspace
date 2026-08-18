"""Approximate/exact nearest-neighbour index over capability vectors.

``NumpyAnnIndex`` is the exact brute-force reference implementation (fine for
small N, no native deps). At scale, drop in a ``UsearchIndex`` (incremental
add/remove — pairs well with spawn-on-miss materialization) or a ``FaissIndex``
(static-batch workloads), both optional with the same interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

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
        return None if v is None else v.copy()

    def __len__(self) -> int:
        return len(self._store)


class UsearchIndex(AnnIndex):  # pragma: no cover - needs optional usearch
    """Incremental ANN index backed by USearch (optional).

    Unlike ``FaissIndex`` — which rebuilds and retrains the whole index after
    any mutation — USearch supports true incremental ``add``/``remove`` with
    O(log N)-ish HNSW-style search. This is the index to pair with
    spawn-on-miss materialization, where capabilities appear at runtime.
    Install with ``pip install fullspace[ann-usearch]``.

    Args:
        dim: vector dimensionality (must match the embedder).
        connectivity: HNSW graph degree (higher = more recall, more memory).
        expansion_add: candidate-list size when inserting.
        expansion_search: candidate-list size when searching.
    """

    def __init__(self, dim: int, connectivity: int = 16, expansion_add: int = 128,
                 expansion_search: int = 64):
        from typing import cast

        from usearch.index import Index, MetricKind  # type: ignore

        self.dim = dim
        self._store: dict[str, np.ndarray] = {}
        self._key_of: dict[str, int] = {}
        self._id_of: dict[int, str] = {}
        self._next_key: int = 1
        self._index = Index(
            ndim=dim,
            metric=MetricKind.Cos,
            dtype=np.float32,  # type: ignore[arg-type]  # DTypeLike at runtime
            connectivity=connectivity,
            expansion_add=expansion_add,
            expansion_search=expansion_search,
        )
        # USearch's Matches/BatchMatches union is awkward to iterate type-safely;
        # narrow once here instead of sprinkling ignores through search().
        self._search = cast("Any", self._index.search)

    def _key(self, id: str) -> int:
        if id not in self._key_of:
            self._key_of[id] = self._next_key
            self._id_of[self._next_key] = id
            self._next_key += 1
        return self._key_of[id]

    def add(self, id: str, vector: np.ndarray) -> None:
        v = np.asarray(vector, dtype=np.float32)
        if v.shape != (self.dim,):
            raise ValueError(f"vector shape {v.shape} != index dim ({self.dim},)")
        self._store[id] = v
        key = self._key(id)
        if key in self._index:  # re-add with an existing key = replace
            self._index.remove(key)
        self._index.add(key, v)

    def remove(self, id: str) -> None:
        if id in self._key_of:
            self._index.remove(self._key_of[id])
            del self._id_of[self._key_of.pop(id)]
        self._store.pop(id, None)

    def search(self, query: np.ndarray, k: int = 5) -> list[tuple[str, float]]:
        if not self._store:
            return []
        q = np.asarray(query, dtype=np.float32)
        matches = self._search(q, min(k, len(self._store)))
        # USearch "Cos" metric returns distances (1 - cosine); flip to scores.
        return [
            (self._id_of[int(m.key)], 1.0 - float(m.distance))
            for m in matches
            if int(m.key) in self._id_of
        ]

    def vector_of(self, id: str) -> np.ndarray | None:
        v = self._store.get(id)
        return None if v is None else v.copy()

    def __len__(self) -> int:
        return len(self._store)


class MilvusIndex(AnnIndex):  # pragma: no cover - needs optional pymilvus + server
    """ANN index backed by a Milvus server / Milvus Lite (optional).

    Use when many capabilities live in one **shared, persistent** collection —
    Milvus is a service, so the index survives processes and can be written by
    one worker while others query it (embeddings are already unit-normalized,
    so the COSINE metric equals dot-product ranking). Capability ids are used
    directly as VARCHAR primary keys, so no id mapping is needed; re-adding an
    id upserts (replace semantics, same as every other ``AnnIndex``).

    Single-writer mode: ``vector_of``/``__len__`` serve from a local mirror,
    so capabilities registered by *other* processes are searchable but not
    reflected in those two methods. Install with ``pip install fullspace[ann-milvus]``.

    Args:
        dim: vector dimensionality (must match the embedder).
        collection: Milvus collection name (created if missing).
        uri: Milvus standalone (``http://localhost:19530``) or Milvus Lite
            (a local ``.db`` file path).
        token / user / password / db_name: server auth, as needed.
        client: an existing ``pymilvus.MilvusClient`` (overrides uri/auth).
    """

    def __init__(self, dim: int, collection: str = "fullspace",
                 uri: str = "http://localhost:19530", token: str = "",
                 user: str = "", password: str = "", db_name: str = "default",
                 client: Any = None):
        self.dim = dim
        self._collection = collection
        self._store: dict[str, np.ndarray] = {}
        if client is None:
            from pymilvus import MilvusClient  # type: ignore

            client = MilvusClient(uri=uri, token=token or None,
                                  user=user or None, password=password or None,
                                  db_name=db_name)
        self._client = client
        if not self._client.has_collection(collection):
            from pymilvus import DataType  # type: ignore
            schema = self._client.create_schema(auto_id=False, enable_dynamic_field=False)
            schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=256)
            schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dim)
            index_params = self._client.prepare_index_params()
            index_params.add_index(field_name="vector", index_type="AUTOINDEX",
                                   metric_type="COSINE")
            self._client.create_collection(collection, schema=schema,
                                           index_params=index_params)

    def add(self, id: str, vector: np.ndarray) -> None:
        v = np.asarray(vector, dtype=np.float32)
        if v.shape != (self.dim,):
            raise ValueError(f"vector shape {v.shape} != index dim ({self.dim},)")
        self._store[id] = v
        self._client.upsert(self._collection, [{"id": id, "vector": v.tolist()}])

    def remove(self, id: str) -> None:
        self._store.pop(id, None)
        self._client.delete(self._collection, filter=f'id == "{id}"')

    def search(self, query: np.ndarray, k: int = 5) -> list[tuple[str, float]]:
        if not self._store:
            return []
        res = self._client.search(
            self._collection, data=[np.asarray(query, dtype=np.float32).tolist()],
            limit=min(k, len(self._store)), output_fields=[],
        )
        hits = res[0] if res else []
        # COSINE metric: Milvus returns similarity scores (higher = closer),
        # matching our cosine-score convention.
        return [(h["id"], float(h["distance"])) for h in hits if h["id"] in self._store]

    def vector_of(self, id: str) -> np.ndarray | None:
        v = self._store.get(id)
        return None if v is None else v.copy()

    def __len__(self) -> int:
        return len(self._store)


class Neo4jVectorIndex(AnnIndex):  # pragma: no cover - needs optional neo4j driver
    """ANN index backed by Neo4j's native vector index (5.13+; optional).

    For teams whose capability registry already lives in Neo4j — routing uses
    ``db.index.vector.queryNodes`` over a cosine vector index on ``(:Capability).vector``.
    Neo4j normalizes cosine scores to [0, 1] via ``(1 + cos) / 2``; this class
    converts back to raw cosine so scores are comparable with the other indexes.

    Install with ``pip install fullspace[ann-neo4j]``.

    Args:
        dim: vector dimensionality (must match the embedder).
        uri / user / password: Neo4j connection (``bolt://localhost:7687``).
        index_name: vector index name (created if missing).
        label: node label capabilities are stored under.
        driver: an existing ``neo4j.GraphDatabase`` driver (overrides uri/auth).
    """

    def __init__(self, dim: int, uri: str = "bolt://localhost:7687",
                 user: str = "neo4j", password: str = "password",
                 index_name: str = "fullspace_caps", label: str = "Capability",
                 driver: Any = None):
        if driver is None:
            from neo4j import GraphDatabase  # type: ignore

            driver = GraphDatabase.driver(uri, auth=(user, password))
        self.dim = dim
        self._driver = driver
        self._index = index_name
        self._label = label
        self._store: dict[str, np.ndarray] = {}
        with self._driver.session() as s:
            s.run(
                f"CREATE VECTOR INDEX $name IF NOT EXISTS FOR (c:{label}) ON (c.vector)"
                " OPTIONS {indexConfig: {`vector.dimensions`: $dim,"
                " `vector.similarity`: 'cosine'}}",
                name=index_name, dim=dim,
            )

    def add(self, id: str, vector: np.ndarray) -> None:
        v = np.asarray(vector, dtype=np.float32)
        if v.shape != (self.dim,):
            raise ValueError(f"vector shape {v.shape} != index dim ({self.dim},)")
        self._store[id] = v
        with self._driver.session() as s:
            s.run(f"MERGE (c:{self._label} {{id: $id}}) SET c.vector = $vec",
                  id=id, vec=v.tolist())

    def remove(self, id: str) -> None:
        self._store.pop(id, None)
        with self._driver.session() as s:
            s.run(f"MATCH (c:{self._label} {{id: $id}}) DETACH DELETE c", id=id)

    def search(self, query: np.ndarray, k: int = 5) -> list[tuple[str, float]]:
        if not self._store:
            return []
        with self._driver.session() as s:
            result = s.run(
                "CALL db.index.vector.queryNodes($name, $k, $query)"
                " YIELD node, score RETURN node.id AS id, score",
                name=self._index, k=min(k, len(self._store)),
                query=np.asarray(query, dtype=np.float32).tolist(),
            )
            # Neo4j cosine score = (1 + cos) / 2 -> convert to raw cosine.
            return [(r["id"], 2.0 * float(r["score"]) - 1.0)
                    for r in result if r["id"] in self._store]

    def vector_of(self, id: str) -> np.ndarray | None:
        v = self._store.get(id)
        return None if v is None else v.copy()

    def __len__(self) -> int:
        return len(self._store)

    def close(self) -> None:
        self._driver.close()


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
