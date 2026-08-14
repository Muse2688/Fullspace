"""Tests for LangGraphCheckpointer: LangGraph savers as Fullspace backends."""

from __future__ import annotations

import pytest

pytest.importorskip("langgraph", reason="langgraph optional extra")

from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import Engine, NodeResult
from fullspace.interop import LangGraphCheckpointer
from fullspace.state.checkpoint import Checkpoint


def _engine(cp) -> Engine:
    m = Manifold(HashEmbedder(dim=64))
    m.register_many(
        [
            Capability("a", "alpha begin"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    eng = Engine(m, checkpointer=cp)
    eng.bind("a", lambda ctx: NodeResult(intent="final answer output"))
    eng.bind("end", lambda ctx: NodeResult(updates={"answer": "done"}))
    return eng


def _savers():
    from langgraph.checkpoint.memory import InMemorySaver

    yield "memory", InMemorySaver()
    sqlite_ok = pytest.importorskip("langgraph.checkpoint.sqlite",
                                    reason="langgraph-checkpoint-sqlite optional")
    import sqlite3
    import tempfile

    conn = sqlite3.connect(tempfile.NamedTemporaryFile(suffix=".db", delete=False).name,
                           check_same_thread=False)
    yield "sqlite", sqlite_ok.SqliteSaver(conn)


@pytest.mark.parametrize("backend", ["memory", "sqlite"])
def test_run_resume_and_time_travel(backend):
    for name, saver in _savers():
        if name != backend:
            continue
        eng = _engine(LangGraphCheckpointer(saver))
        r1 = eng.run("alpha begin", state={"seed": 1}, thread_id="t1", max_steps=1)
        assert r1.terminated_by == "budget" and r1.trajectory == ["a"]

        # Oldest-first timeline, parent chaining intact.
        hist = eng.history("t1")
        assert [c.step for c in hist] == [1]
        assert hist[0].trajectory == ["a"]

        r2 = eng.resume("t1", task="final answer output")
        assert r2.terminated_by == "sink"
        assert r2.trajectory == ["a", "end"]
        assert r2.state["answer"] == "done"

        hist = eng.history("t1")
        assert [c.step for c in hist] == [1, 2]        # oldest first
        assert len({c.checkpoint_id for c in hist}) == 2
        assert hist[1].parent_id == hist[0].checkpoint_id

        # Latest = final state; point lookup = time travel.
        latest = eng.get_checkpoint("t1")
        assert latest.step == 2 and latest.state["answer"] == "done"
        step1 = eng.get_checkpoint("t1", hist[0].checkpoint_id)
        assert step1.step == 1 and step1.trajectory == ["a"]


def test_put_get_roundtrip_raw():
    from langgraph.checkpoint.memory import InMemorySaver

    cp = LangGraphCheckpointer(InMemorySaver())
    cp.put(Checkpoint("fs-id-1", "t9", 1, {"x": 1}, ["a"], [["a"]], None, "budget"))
    got = cp.get("t9")
    assert got is not None
    assert got.state == {"x": 1} and got.trajectory == ["a"]
    assert got.terminated_by == "budget"
    cp.put(Checkpoint("fs-id-2", "t9", 2, {"x": 2}, ["a", "b"], [["a"], ["b"]], "fs-id-1", "sink"))
    assert [c.step for c in cp.list("t9")] == [1, 2]  # oldest first
    assert cp.get("t9", "fs-id-1").state == {"x": 1}  # point lookup by our id
    assert cp.get("missing-thread") is None
