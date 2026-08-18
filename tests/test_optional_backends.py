"""Fake-connection tests for the optional DB backends.

No MySQL/Milvus/Neo4j server is needed: these tests inject fake clients that
speak the same protocol, verifying the *code paths* — SQL dialect, Cypher
shape, score conversion, call sequence. Real-server smoke tests are gated by
importorskip on the respective client libraries.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from fullspace.state.checkpoint import Checkpoint, MySqlCheckpointer


# ─────────────── MySQL checkpointer (fake DB-API connection) ───────────────

class FakeCursor:
    def __init__(self, conn):
        self._conn = conn
        self._rows: list[tuple] = []

    def execute(self, sql, params=()):
        self._conn.statements.append((sql.strip(), params))
        self._rows = self._conn.results_for(sql)

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def close(self):
        pass


class FakeMySqlConn:
    """Records every statement; returns canned rows per SQL prefix."""

    def __init__(self):
        self.statements: list[tuple[str, tuple]] = []
        self.rows: list[tuple] = []

    def results_for(self, sql):
        return self.rows if "SELECT" in sql.upper() else []

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        pass

    def close(self):
        pass


def _row(cp: Checkpoint) -> tuple:
    return (cp.thread_id, cp.checkpoint_id, cp.step, json.dumps(cp.state),
            json.dumps(cp.trajectory), json.dumps(cp.step_groups),
            cp.parent_id, cp.terminated_by)


def test_mysql_checkpointer_dialect_and_roundtrip():
    conn = FakeMySqlConn()
    cp = MySqlCheckpointer(conn=conn)

    # DDL: MySQL table created once at init.
    assert any(s.startswith("CREATE TABLE IF NOT EXISTS") for s, _ in conn.statements)

    c1 = Checkpoint("t:0001:ab", "t", 1, {"x": 1}, ["a"], [["a"]], None, "budget")
    cp.put(c1)
    writes = [s for s, _ in conn.statements if "REPLACE INTO" in s]
    assert len(writes) == 1 and "`checkpoints`" in writes[0]
    params = [p for s, p in conn.statements if "REPLACE INTO" in s][0]
    assert params[0] == "t" and params[2] == 1 and json.loads(params[3]) == {"x": 1}

    # get / list parse tuple rows back into Checkpoint objects.
    conn.rows = [_row(c1)]
    got = cp.get("t")
    assert got is not None and got.checkpoint_id == "t:0001:ab"
    assert got.state == {"x": 1} and got.trajectory == ["a"]
    assert got.terminated_by == "budget"

    c2 = Checkpoint("t:0002:cd", "t", 2, {"x": 2}, ["a", "b"], [["a"], ["b"]],
                    "t:0001:ab", "sink")
    conn.rows = [_row(c1), _row(c2)]
    listed = cp.list("t")
    assert [c.step for c in listed] == [1, 2]
    assert listed[1].parent_id == listed[0].checkpoint_id

    conn.rows = []                     # empty result set
    assert cp.get("missing") is None and cp.list("missing") == []


# ─────────────── Milvus index (fake MilvusClient) ───────────────

class FakeMilvusClient:
    def __init__(self):
        self.created = False
        self.upserts: list[dict] = []
        self.deletes: list[str] = []
        self.search_results: list[dict] = []

    def has_collection(self, name):
        return self.created

    def create_schema(self, **kw):
        class S(list):
            def add_field(self, *a, **k):
                self.append((a, k))
        return S()

    def prepare_index_params(self):
        class IP:
            def add_index(self, *a, **k):
                pass
        return IP()

    def create_collection(self, name, schema=None, index_params=None):
        self.created = True

    def upsert(self, name, rows):
        self.upserts.extend(rows)

    def delete(self, name, filter=""):
        self.deletes.append(filter)

    def search(self, name, data, limit, output_fields):
        return [self.search_results[:limit]]


def test_milvus_index_calls_and_scores():
    from fullspace.manifold.index import MilvusIndex

    client = FakeMilvusClient()
    idx = MilvusIndex(dim=4, client=client)
    assert client.created  # collection bootstrapped on first use

    v = np.array([1.0, 0, 0, 0], dtype=np.float32)
    idx.add("a", v)
    idx.add("b", np.array([0, 1.0, 0, 0], dtype=np.float32))
    assert [r["id"] for r in client.upserts] == ["a", "b"]

    idx.add("a", np.array([0, 0, 1.0, 0], dtype=np.float32))  # re-add = replace
    assert len(idx) == 2 and len(client.upserts) == 3

    # COSINE metric: distance field carries the similarity score as-is.
    client.search_results = [{"id": "a", "distance": 0.9}, {"id": "b", "distance": 0.4}]
    hits = idx.search(v, k=2)
    assert hits == [("a", 0.9), ("b", 0.4)]

    idx.remove("a")
    assert client.deletes == ['id == "a"'] and len(idx) == 1
    assert idx.vector_of("b") is not None and idx.vector_of("a") is None


# ─────────────── Neo4j vector index + lineage export (fake driver) ───────────────

class FakeNeo4jResult(list):
    def __init__(self, rows):
        super().__init__(rows)


class FakeNeo4jSession:
    def __init__(self, driver):
        self._driver = driver

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, cypher, **params):
        self._driver.cypher.append((cypher.strip(), params))
        return FakeNeo4jResult(self._driver.rows)

    def execute_write(self, fn):
        tx = type("Tx", (), {"run": lambda _, q, **p: self.run(q, **p)})()
        fn(tx)


class FakeNeo4jDriver:
    def __init__(self):
        self.cypher: list[tuple[str, dict]] = []
        self.rows: list[dict] = []

    def session(self):
        return FakeNeo4jSession(self)

    def close(self):
        pass


def test_neo4j_vector_index_score_conversion():
    from fullspace.manifold.index import Neo4jVectorIndex

    driver = FakeNeo4jDriver()
    idx = Neo4jVectorIndex(dim=4, driver=driver)
    assert any("CREATE VECTOR INDEX" in q for q, _ in driver.cypher)

    idx.add("a", np.array([1.0, 0, 0, 0], dtype=np.float32))
    assert any("MERGE (c:Capability" in q for q, _ in driver.cypher)

    # Neo4j cosine score = (1 + cos)/2 in [0,1] -> converted to raw cosine.
    driver.rows = [{"id": "a", "score": 0.9}]        # cos = 0.8
    assert idx.search(np.array([1.0, 0, 0, 0]), k=1) == [("a", pytest.approx(0.8))]

    idx.remove("a")
    assert any("DETACH DELETE" in q for q, _ in driver.cypher)
    assert len(idx) == 0


def test_neo4j_lineage_export_cypher():
    from fullspace.interop.neo4j import export_trajectory_to_neo4j

    driver = FakeNeo4jDriver()
    run_id = export_trajectory_to_neo4j(
        ["diagnose", "plan", "teach"],
        step_groups=[["diagnose", "plan"], ["teach"]],
        terminated_by="sink",
        driver=driver,
    )
    queries = [q for q, _ in driver.cypher]
    assert any("MERGE (r:Run" in q for q in queries)
    assert any("-[v:VISITED" in q for q in queries)
    # Consecutive hops recorded as NEXT transitions.
    nexts = [q for q in queries if ":NEXT" in q]
    assert len(nexts) == 2  # diagnose->plan (intra-group), plan->teach (group head)
    assert any("ENDED_BY" in q for q in queries)
    assert run_id  # returned id usable for later queries


def test_real_server_smoke_gated():
    """Real-server paths stay import-guarded — just assert the extra hint."""
    try:
        import pymysql  # noqa: F401
    except ImportError:
        with pytest.raises(ImportError, match="cp-mysql"):
            MySqlCheckpointer()  # no conn and no driver -> actionable error
