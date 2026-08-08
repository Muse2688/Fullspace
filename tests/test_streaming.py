"""Tests for streaming + async execution (LangGraph production-parity)."""

from __future__ import annotations

import asyncio

from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import Engine, NodeResult
from fullspace.interop import FullspaceRunnable


def _three_step() -> Engine:
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(
        [
            Capability("a", "alpha step"),
            Capability("b", "beta step"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    eng = Engine(m)
    eng.bind("a", lambda ctx: NodeResult(intent="beta step"))
    eng.bind("b", lambda ctx: NodeResult(goto="end"))
    eng.bind("end", lambda ctx: NodeResult(updates={"answer": "done"}))
    return eng


# -- sync streaming ---------------------------------------------------------

def test_stream_yields_one_event_per_step():
    eng = _three_step()
    events = list(eng.stream("alpha step"))
    assert len(events) == 3
    assert [e.step for e in events] == [1, 2, 3]
    assert [e.group for e in events] == [["a"], ["b"], ["end"]]
    assert events[-1].terminated is True
    assert events[-1].terminated_by == "sink"
    # trajectory grows incrementally
    assert events[0].trajectory == ["a"]
    assert events[1].trajectory == ["a", "b"]
    assert events[2].trajectory == ["a", "b", "end"]
    # state snapshot after the final step carries the answer
    assert events[2].state["answer"] == "done"


def test_stream_matches_run_result():
    eng = _three_step()
    run_result = eng.run("alpha step")
    streamed = list(eng.stream("alpha step"))
    last = streamed[-1]
    assert last.state == run_result.state
    assert last.trajectory == run_result.trajectory
    assert last.terminated_by == run_result.terminated_by


# -- async execution --------------------------------------------------------

async def test_ainvoke_matches_sync_run():
    eng = _three_step()
    sync = eng.run("alpha step")
    asy = await eng.ainvoke("alpha step")
    assert asy.trajectory == sync.trajectory == ["a", "b", "end"]
    assert asy.state == sync.state
    assert asy.terminated_by == "sink"


async def test_astream_with_async_handler():
    """An `async def` node handler is awaited correctly inside astream/ainvoke."""
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(
        [
            Capability("fetch", "fetch the data"),
            Capability("process", "process the data"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    eng = Engine(m)

    async def fetch(ctx):
        await asyncio.sleep(0)  # simulates an async I/O / LLM call
        return NodeResult(updates={"data": "fetched"}, intent="process the data")

    eng.bind("fetch", fetch)
    eng.bind("process", lambda ctx: NodeResult(updates={"data": ctx.state["data"] + "+processed"}, goto="end"))
    eng.bind("end", lambda ctx: NodeResult(updates={"answer": ctx.state["data"]}))

    events = [ev async for ev in eng.astream("fetch the data")]
    assert [e.group for e in events] == [["fetch"], ["process"], ["end"]]
    assert events[-1].state["answer"] == "fetched+processed"
    assert events[-1].terminated is True


async def test_ainvoke_with_mixed_sync_async_handlers():
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(
        [
            Capability("sync_node", "do sync work"),
            Capability("async_node", "do async work"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    eng = Engine(m)
    eng.bind("sync_node", lambda ctx: NodeResult(updates={"s": 1}, intent="do async work"))

    async def async_node(ctx):
        await asyncio.sleep(0)
        return NodeResult(updates={"a": 2}, goto="end")

    eng.bind("async_node", async_node)
    eng.bind("end", lambda ctx: NodeResult())
    res = await eng.ainvoke("do sync work")
    assert res.trajectory == ["sync_node", "async_node", "end"]
    assert res.state == {"s": 1, "a": 2}


# -- Runnable streaming surface --------------------------------------------

def test_runnable_stream_yields_chunks():
    r = FullspaceRunnable(_three_step())
    chunks = list(r.stream({"task": "alpha step"}))
    assert len(chunks) == 3
    assert chunks[-1]["terminated"] is True
    assert chunks[-1]["state"]["answer"] == "done"


async def test_runnable_astream_and_ainvoke():
    r = FullspaceRunnable(_three_step())
    chunks = [c async for c in r.astream({"task": "alpha step"})]
    assert len(chunks) == 3
    out = await r.ainvoke({"task": "alpha step"})
    assert out["trajectory"] == ["a", "b", "end"]
    assert out["terminated_by"] == "sink"
