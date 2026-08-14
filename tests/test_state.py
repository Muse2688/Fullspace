"""Tests for Phase 2: reducers, checkpointing, resume, time-travel, persistence."""

from __future__ import annotations

from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import Engine, NodeResult
from fullspace.state import (
    Checkpoint,
    InMemoryCheckpointer,
    SqliteCheckpointer,
    add,
    annotate_positions,
    last_value,
)


def _three_step_engine(checkpointer=None, state_spec=None, max_steps=25) -> Engine:
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(
        [
            Capability("a", "alpha step"),
            Capability("b", "beta step"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    eng = Engine(m, checkpointer=checkpointer, state_spec=state_spec, max_steps=max_steps)
    eng.bind("a", lambda ctx: NodeResult(intent="beta step"))
    eng.bind("b", lambda ctx: NodeResult(goto="end"))
    eng.bind("end", lambda ctx: NodeResult())
    return eng


# -- reducers ---------------------------------------------------------------

def test_reducer_add_channel_appends():
    eng = _three_step_engine(state_spec={"messages": add})
    # Override handlers to write to the append channel across two steps.
    eng.bind("a", lambda ctx: NodeResult(updates={"messages": ["one"]}, intent="beta step"))
    eng.bind("b", lambda ctx: NodeResult(updates={"messages": ["two"]}, goto="end"))
    res = eng.run("alpha step")
    assert res.state["messages"] == ["one", "two"]


def test_reducer_last_value_keeps_on_none():
    eng = _three_step_engine(state_spec={"flag": last_value})
    eng.bind("a", lambda ctx: NodeResult(updates={"flag": "set"}, intent="beta step"))
    eng.bind("b", lambda ctx: NodeResult(updates={"flag": None}, goto="end"))
    res = eng.run("alpha step")
    assert res.state["flag"] == "set"  # None update did not overwrite


# -- checkpointing ----------------------------------------------------------

def test_checkpointer_writes_one_per_step():
    cp = InMemoryCheckpointer()
    eng = _three_step_engine(checkpointer=cp)
    eng.run("alpha step", thread_id="t1")

    hist = eng.history("t1")
    assert len(hist) == 3
    assert [c.step for c in hist] == [1, 2, 3]
    assert hist[0].trajectory == ["a"]
    assert hist[1].trajectory == ["a", "b"]
    assert hist[-1].terminated_by == "sink"
    # Parent chain is linked.
    assert hist[0].parent_id is None
    assert hist[1].parent_id == hist[0].checkpoint_id
    assert hist[2].parent_id == hist[1].checkpoint_id


def test_no_checkpointer_when_no_thread_id():
    cp = InMemoryCheckpointer()
    eng = _three_step_engine(checkpointer=cp)
    eng.run("alpha step")  # no thread_id
    assert eng.history("t1") == []


def test_resume_continues_from_checkpoint():
    cp = InMemoryCheckpointer()
    eng = _three_step_engine(checkpointer=cp, max_steps=1)
    res1 = eng.run("alpha step", thread_id="t1", max_steps=1)
    assert res1.terminated_by == "budget"
    assert res1.trajectory == ["a"]

    # Resume with a larger budget; route from the next intent.
    res2 = eng.resume("t1", task="beta step", max_steps=25)
    assert "b" in res2.trajectory and "end" in res2.trajectory
    assert res2.terminated_by == "sink"
    # Resumed run appended to the prior trajectory.
    assert res2.trajectory[:1] == ["a"]


def test_time_travel_get_checkpoint():
    cp = InMemoryCheckpointer()
    eng = _three_step_engine(checkpointer=cp)
    eng.run("alpha step", thread_id="t1")

    step1 = eng.get_checkpoint("t1", eng.history("t1")[0].checkpoint_id)
    assert step1.step == 1 and step1.trajectory == ["a"]
    latest = eng.get_checkpoint("t1")
    assert latest.step == 3 and latest.terminated_by == "sink"


def test_rerun_appends_not_overwrites_timeline():
    # A re-run of the same thread must not clobber earlier checkpoints:
    # checkpoint ids are unique per write, so the timeline only grows.
    cp = InMemoryCheckpointer()
    eng = _three_step_engine(checkpointer=cp, max_steps=1)
    eng.run("alpha step", thread_id="t1", max_steps=1)
    eng.run("alpha step", thread_id="t1", max_steps=1)
    hist = eng.history("t1")
    # One termination checkpoint per run — and the second run appended instead
    # of replacing the first (ids are unique per write).
    assert len(hist) == 2
    assert len({c.checkpoint_id for c in hist}) == 2
    assert hist[1].parent_id == hist[0].checkpoint_id


# -- sqlite persistence -----------------------------------------------------

def test_sqlite_checkpointer_roundtrip():
    cp = SqliteCheckpointer()
    try:
        original = Checkpoint("t:0001", "t", 1, {"x": 1}, ["a"], [["a"]], None, "sink")
        cp.put(original)
        got = cp.get("t")
        assert got.state == {"x": 1}
        assert got.trajectory == ["a"]
        assert got.step_groups == [["a"]]
        assert got.terminated_by == "sink"
        assert len(cp.list("t")) == 1
    finally:
        cp.close()


def test_sqlite_survives_reopen():
    import tempfile
    import os
    path = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
    try:
        cp1 = SqliteCheckpointer(path)
        cp1.put(Checkpoint("t:0001", "t", 1, {"x": 1}, ["a"], [["a"]], None, None))
        cp1.close()
        cp2 = SqliteCheckpointer(path)
        got = cp2.get("t")
        assert got is not None and got.state == {"x": 1}
        cp2.close()
    finally:
        os.unlink(path)


# -- trajectory spatial annotation -----------------------------------------

def test_annotate_positions():
    m = Manifold(HashEmbedder(dim=256))
    m.register_many([Capability("a", "alpha"), Capability("b", "beta")])
    ann = annotate_positions([["a"], ["a", "b"]], m)
    assert len(ann) == 2
    assert len(ann[0]["positions3d"][0]) == 3  # 3D, viz only
