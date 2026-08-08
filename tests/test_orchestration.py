"""Orchestration parity: Fullspace provides the same orchestration guarantees
as LangGraph — state threading, conditional branching, loops, parallel
fan-out/fan-in, and checkpoint/resume — plus capability-space extras.

Each test maps to a LangGraph orchestration primitive and asserts Fullspace
behaves identically.
"""

from __future__ import annotations

import numpy as np

from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import Engine, FieldFlow, NodeResult
from fullspace.state import InMemoryCheckpointer, add


def _m(*caps: Capability) -> Manifold:
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(list(caps))
    return m


# 1. State threading across a chain (LangGraph: state passed node-to-node).
def test_state_threads_across_chain():
    eng = Engine(
        _m(
            Capability("a", "fetch data"),
            Capability("b", "transform data"),
            Capability("c", "store data", metadata={"sink": True}),
        )
    )
    eng.bind("a", lambda ctx: NodeResult(updates={"data": "raw"}, intent="transform data"))
    eng.bind("b", lambda ctx: NodeResult(updates={"data": ctx.state["data"] + "->clean"}, intent="store data"))
    eng.bind("c", lambda ctx: NodeResult(updates={"saved": ctx.state["data"]}))
    res = eng.run("fetch data")
    assert res.state["saved"] == "raw->clean"


# 2. Conditional branching by state (LangGraph: conditional_edges reading state).
def test_conditional_branch_by_state():
    eng = Engine(
        _m(
            Capability("router", "classify route the request"),
            Capability("yes", "process approved path"),
            Capability("no", "process rejected path"),
            Capability("end", "final answer output", metadata={"sink": True}),
        )
    )

    def router(ctx):
        intent = "process approved path" if ctx.state.get("ok") else "process rejected path"
        return NodeResult(intent=intent)

    eng.bind("router", router)
    eng.bind("yes", lambda ctx: NodeResult(updates={"result": "approved"}, goto="end"))
    eng.bind("no", lambda ctx: NodeResult(updates={"result": "rejected"}, goto="end"))
    eng.bind("end", lambda ctx: NodeResult())

    r1 = eng.run("classify route the request", state={"ok": True})
    r2 = eng.run("classify route the request", state={"ok": False})
    assert r1.state["result"] == "approved" and "yes" in r1.trajectory
    assert r2.state["result"] == "rejected" and "no" in r2.trajectory


# 3. Loop until a condition (LangGraph: self-edge with conditional exit).
def test_loop_until_condition():
    eng = Engine(
        _m(
            Capability("refine", "refine iterate improve the result"),
            Capability("end", "final answer output", metadata={"sink": True}),
        )
    )

    def refine(ctx):
        v = ctx.state.get("v", 0) + 1
        if v < 3:
            return NodeResult(updates={"v": v}, intent="refine iterate improve the result")
        return NodeResult(updates={"v": v}, goto="end")

    eng.bind("refine", refine)
    eng.bind("end", lambda ctx: NodeResult())
    res = eng.run("refine iterate improve the result")
    assert res.trajectory == ["refine", "refine", "refine", "end"]
    assert res.state["v"] == 3


# 4. Parallel fan-out / fan-in (LangGraph: parallel branches + reducer merge).
def test_parallel_fanout_fanin_merges_via_reducer():
    eng = Engine(
        _m(
            Capability("fanout_a", "research topic alpha"),
            Capability("fanout_b", "research topic beta"),
            Capability("combine", "synthesize combine the findings"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ),
        flow=FieldFlow(width=2),
        state_spec={"findings": add},
    )
    eng.bind("fanout_a", lambda ctx: NodeResult(updates={"findings": ["alpha-fact"]}, goto="combine"))
    eng.bind("fanout_b", lambda ctx: NodeResult(updates={"findings": ["beta-fact"]}, goto="combine"))
    eng.bind("combine", lambda ctx: NodeResult(updates={"count": len(ctx.state["findings"])}, goto="end"))
    eng.bind("end", lambda ctx: NodeResult(updates={"answer": ctx.state["count"]}))

    res = eng.run("research topic alpha beta")
    assert set(res.step_groups[0]) == {"fanout_a", "fanout_b"}      # parallel fan-out, one step
    assert res.state["findings"] == ["alpha-fact", "beta-fact"]     # merged via reducer (fan-in)
    assert res.state["answer"] == 2                                 # combine saw both results


# 5. Checkpoint + resume mid-orchestration (LangGraph: checkpointer + thread resume).
def test_checkpoint_resume_mid_orchestration():
    cp = InMemoryCheckpointer()
    eng = Engine(
        _m(
            Capability("s1", "step one start"),
            Capability("s2", "step two middle"),
            Capability("s3", "step three final", metadata={"sink": True}),
        ),
        checkpointer=cp,
    )
    eng.bind("s1", lambda ctx: NodeResult(intent="step two middle"))
    eng.bind("s2", lambda ctx: NodeResult(intent="step three final"))
    eng.bind("s3", lambda ctx: NodeResult(updates={"done": True}))

    r1 = eng.run("step one start", thread_id="t", max_steps=1)   # interrupt after s1
    assert r1.terminated_by == "budget"
    assert r1.trajectory == ["s1"]

    r2 = eng.resume("t", task="step two middle", max_steps=25)
    assert r2.terminated_by == "sink"
    assert r2.trajectory == ["s1", "s2", "s3"]
    assert r2.state["done"] is True


# 6. Reducer parity: `add` accumulates like LangGraph message channels.
def test_add_reducer_accumulates_like_channels():
    eng = Engine(
        _m(
            Capability("a", "append message one"),
            Capability("b", "append message two"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ),
        state_spec={"messages": add},
    )
    eng.bind("a", lambda ctx: NodeResult(updates={"messages": "m1"}, intent="append message two"))
    eng.bind("b", lambda ctx: NodeResult(updates={"messages": "m2"}, goto="end"))
    eng.bind("end", lambda ctx: NodeResult())
    res = eng.run("append message one")
    assert res.state["messages"] == ["m1", "m2"]


# 7. CachedEmbedder: identical results, fewer inner calls (the optimization).
def test_cached_embedder_identical_and_fewer_calls():
    from fullspace import CachedEmbedder

    calls = {"n": 0}

    class Counting(HashEmbedder):
        def embed(self, t):
            calls["n"] += 1
            return super().embed(t)

    inner = Counting(dim=256)
    cached = CachedEmbedder(inner)

    a = cached.embed("repeat me")
    b = cached.embed("repeat me")
    c = cached.embed("other")
    assert np.array_equal(a, b)              # cached result identical
    assert cached.hits == 1 and cached.misses == 2
    assert calls["n"] == 2                   # 3 embed() calls, only 2 hit the inner embedder


# 8. Composed: a realistic multi-primitive agent (branch + loop + accumulate).
def test_composed_agent_branch_loop_accumulate():
    eng = Engine(
        _m(
            Capability("intake", "intake classify the user request"),
            Capability("work", "work process the task step"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ),
        state_spec={"log": add},
    )

    def intake(ctx):
        kind = "work process the task step"  # route into the work loop
        return NodeResult(updates={"remaining": 2, "log": "intake"}, intent=kind)

    def work(ctx):
        rem = ctx.state.get("remaining", 0) - 1
        upd = {"remaining": rem, "log": f"work-{rem}"}
        if rem > 0:
            return NodeResult(updates=upd, intent="work process the task step")
        return NodeResult(updates=upd, goto="end")

    eng.bind("intake", intake)
    eng.bind("work", work)
    eng.bind("end", lambda ctx: NodeResult(updates={"answer": "done"}))

    res = eng.run("intake classify the user request")
    assert res.trajectory == ["intake", "work", "work", "end"]
    assert res.state["log"] == ["intake", "work-1", "work-0"]
    assert res.state["remaining"] == 0
