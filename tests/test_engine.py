"""Tests for the Phase 1 engine: closed loop + discrete flow + mixed router."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import (
    Engine,
    FieldFlow,
    NodeContext,
    NodeResult,
    Router,
    WavefrontFlow,
)


# -- fixtures ----------------------------------------------------------------

def _manifold(*caps: Capability) -> Manifold:
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(list(caps))
    return m


def _linear_engine() -> Engine:
    eng = Engine(
        _manifold(
            Capability("search", "search the web for information"),
            Capability("summarize", "summarize a long document into key points"),
            Capability("end", "final answer output", metadata={"sink": True}),
        )
    )

    def search(ctx):
        return NodeResult(
            updates={"findings": f"found:{ctx.task}"},
            intent="summarize the findings into key points",
        )

    def summarize(ctx):
        return NodeResult(updates={"summary": f"sum:{ctx.state['findings']}"}, goto="end")

    def end(ctx):
        return NodeResult(updates={"answer": ctx.state.get("summary", "")})

    eng.bind_many({"search": search, "summarize": summarize, "end": end})
    return eng


# -- the canonical happy path -----------------------------------------------

def test_linear_pipeline_trajectory_and_sink():
    eng = _linear_engine()
    res = eng.run("search for information about physics")
    assert res.trajectory == ["search", "summarize", "end"]
    assert res.terminated_by == "sink"
    assert res.steps == 3
    assert res.state["answer"].startswith("sum:")


def test_branching_soft_routes_to_correct_start():
    eng = Engine(
        _manifold(
            Capability("calc", "perform arithmetic and math calculations"),
            Capability("search", "search the web for information"),
            Capability("end", "final answer output", metadata={"sink": True}),
        )
    )
    eng.bind_many(
        {
            "calc": lambda ctx: NodeResult(updates={"r": "calc"}, goto="end"),
            "search": lambda ctx: NodeResult(updates={"r": "search"}, goto="end"),
            "end": lambda ctx: NodeResult(updates={"answer": ctx.state.get("r")}),
        }
    )
    assert eng.run("perform math calculations on numbers").trajectory[0] == "calc"
    assert eng.run("search the web for information about cats").trajectory[0] == "search"


# -- termination paths ------------------------------------------------------

def test_halt_terminates():
    eng = Engine(_manifold(Capability("n", "do the node thing")))
    eng.bind("n", lambda ctx: NodeResult(halt=True))
    res = eng.run("do the node thing")
    assert res.trajectory == ["n"]
    assert res.terminated_by == "halt"


def test_no_intent_terminates_gracefully():
    eng = Engine(_manifold(Capability("n", "do the node thing")))
    eng.bind("n", lambda ctx: NodeResult(updates={"x": 1}))  # no intent/goto/halt
    res = eng.run("do the node thing")
    assert res.terminated_by == "no_intent"


def test_dict_return_is_updates_and_terminates():
    eng = Engine(_manifold(Capability("n", "do the node thing")))
    eng.bind("n", lambda ctx: {"x": 1})
    res = eng.run("do the node thing")
    assert res.state["x"] == 1
    assert res.terminated_by == "no_intent"


def test_budget_guardrail():
    eng = Engine(_manifold(Capability("loop", "loop repeat the process")))
    eng.bind("loop", lambda ctx: NodeResult(intent="loop repeat the process"))
    res = eng.run("loop repeat the process", max_steps=3)
    assert res.terminated_by == "budget"
    assert res.steps == 3
    assert res.trajectory == ["loop", "loop", "loop"]


def test_no_handler_terminates():
    eng = Engine(_manifold(Capability("lonely", "the lonely node")))
    res = eng.run("the lonely node")
    assert res.terminated_by == "no_handler"


def test_empty_manifold():
    eng = Engine(Manifold(HashEmbedder()))
    res = eng.run("anything")
    assert res.terminated_by == "empty"
    assert res.steps == 0


def test_bad_goto_terminates():
    eng = Engine(_manifold(Capability("n", "do the node thing")))
    eng.bind("n", lambda ctx: NodeResult(goto="does_not_exist"))
    res = eng.run("do the node thing")
    assert res.terminated_by == "bad_goto"


# -- router: spawn-on-miss + disambiguation ---------------------------------

def test_spawn_on_miss_creates_capability_mid_run():
    m = _manifold(Capability("greet", "greet the user hello"))
    eng = Engine(
        m,
        router=Router(
            m,
            threshold=0.99,  # force a near-miss on the gibberish intent
            materializer=lambda desc, score: Capability("fallback", desc),
        ),
    )
    eng.bind("greet", lambda ctx: NodeResult(intent="zzzzqqqq unmatched gibberish"))
    eng.bind("fallback", lambda ctx: NodeResult(halt=True))
    res = eng.run("greet the user hello")
    assert "fallback" in m                      # materialized
    assert res.trajectory == ["greet", "fallback"]
    assert res.terminated_by == "halt"


def test_disambiguator_invoked_at_ambiguous_junction():
    # Two capabilities with identical descriptions -> tie -> margin ~0.
    m = _manifold(
        Capability("start", "begin the work"),
        Capability("a", "do the thing"),
        Capability("b", "do the thing"),
    )
    called = {"n": 0}

    def disambig(intent, hits):
        called["n"] += 1
        return "b"

    eng = Engine(m, router=Router(m, margin=0.15, disambiguator=disambig))
    eng.bind("start", lambda ctx: NodeResult(intent="do the thing"))
    eng.bind("b", lambda ctx: NodeResult(halt=True))
    eng.bind("a", lambda ctx: NodeResult(halt=True))
    res = eng.run("begin the work")
    assert called["n"] == 1                      # LLM would be called here
    assert res.trajectory == ["start", "b"]


# -- determinism ------------------------------------------------------------

def test_same_input_same_trajectory():
    eng = _linear_engine()
    t1 = eng.run("search for information about physics").trajectory
    t2 = eng.run("search for information about physics").trajectory
    assert t1 == t2


# -- example modules import & run ------------------------------------------

def test_examples_run_without_error():
    from fullspace.examples import (
        branching,
        interrupt_resume,
        linear_pipeline,
        react_agent,
    )

    linear_pipeline.main()
    branching.main()
    react_agent.main()
    interrupt_resume.main()


def test_react_agent_loop_structure():
    from fullspace.examples import react_agent

    eng = react_agent.build()
    res = eng.run("think reason about the problem and decide an action")
    # Canonical ReAct cycle (think -> act -> observe) repeated, then answer.
    assert res.trajectory == ["think", "act", "observe", "think", "act", "observe", "end"]
    assert res.state["actions"] == 2
    assert res.terminated_by == "sink"


def test_interrupt_then_resume_completes():
    from fullspace.examples import interrupt_resume

    eng = interrupt_resume.build()
    r1 = eng.run("work repeat the processing step", state={"n": 5}, thread_id="job", max_steps=2)
    assert r1.terminated_by == "budget"
    assert r1.state["n"] == 3  # 2 work steps done
    # Time-travel: a checkpoint exists per step.
    assert len(eng.history("job")) == 2

    r2 = eng.resume("job", task="work repeat the processing step", max_steps=25)
    assert r2.terminated_by == "sink"
    assert r2.state["n"] == 0
    assert "end" in r2.trajectory


# -- Phase 4: field diffusion (multi-activation) ---------------------------

def test_field_flow_activates_neighborhood():
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(
        [
            Capability("a", "alpha topic shared"),
            Capability("b", "alpha topic variant"),
            Capability("c", "alpha topic other"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    eng = Engine(m, flow=FieldFlow(width=3))
    eng.bind("a", lambda ctx: NodeResult(updates={"a": 1}, goto="end"))
    eng.bind("b", lambda ctx: NodeResult(updates={"b": 1}, goto="end"))
    eng.bind("c", lambda ctx: NodeResult(updates={"c": 1}, goto="end"))
    eng.bind("end", lambda ctx: NodeResult(updates={"answer": "done"}))

    res = eng.run("alpha topic shared")
    # Step 1 activates a neighbourhood of 3 (barrier-free parallelism);
    # step 2 is the exact goto "end" (sink).
    assert len(res.step_groups) == 2
    assert set(res.step_groups[0]) == {"a", "b", "c"}
    assert res.step_groups[1] == ["end"]
    assert res.terminated_by == "sink"
    # Flat trajectory preserves backward-compatible shape.
    assert res.trajectory == ["a", "b", "c", "end"]


def test_field_flow_combines_intents_to_navigate():
    # Two neighbours activated; their combined intent vector routes onward.
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(
        [
            Capability("start_a", "alpha begin"),
            Capability("start_b", "alpha commence"),
            Capability("next", "alpha proceed middle stage"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    eng = Engine(m, flow=FieldFlow(width=2))
    eng.bind("start_a", lambda ctx: NodeResult(intent="alpha proceed"))
    eng.bind("start_b", lambda ctx: NodeResult(intent="middle stage"))
    eng.bind("next", lambda ctx: NodeResult(goto="end"))
    eng.bind("end", lambda ctx: NodeResult(updates={"answer": "done"}))
    res = eng.run("alpha begin commence")
    assert set(res.step_groups[0]) == {"start_a", "start_b"}
    # The combined intent vector ("alpha proceed" + "middle stage") points most
    # strongly at 'next' (it shares all four tokens) -> next is the top hit.
    assert res.step_groups[1][0] == "next"
    assert "next" in res.trajectory and "end" in res.trajectory
    assert res.terminated_by == "sink"


async def test_field_flow_group_runs_concurrently():
    # Two async handlers in the same activation group must overlap: they
    # handshake via events, so sequential execution would deadlock (timeout).
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(
        [
            Capability("a", "alpha topic shared"),
            Capability("b", "alpha topic variant"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    started, release = asyncio.Event(), asyncio.Event()

    async def handler_a(ctx):
        started.set()
        await release.wait()
        return NodeResult(updates={"a": 1}, goto="end")

    async def handler_b(ctx):
        await started.wait()
        release.set()
        return NodeResult(updates={"b": 1}, goto="end")

    eng = Engine(m, flow=FieldFlow(width=2))
    eng.bind("a", handler_a)
    eng.bind("b", handler_b)
    eng.bind("end", lambda ctx: NodeResult(updates={"answer": "done"}))
    res = await asyncio.wait_for(eng.ainvoke("alpha topic shared"), timeout=5)
    assert set(res.step_groups[0]) == {"a", "b"}
    assert res.terminated_by == "sink"


def test_field_flow_group_sees_step_start_state():
    # Co-activated handlers get a snapshot of the step-start state: neither
    # observes the other's not-yet-merged write.
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(
        [
            Capability("a", "alpha topic shared"),
            Capability("b", "alpha topic variant"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    seen: dict[str, Any] = {}
    eng = Engine(m, flow=FieldFlow(width=2))
    eng.bind("a", lambda ctx: seen.__setitem__("a", dict(ctx.state)) or NodeResult(updates={"a": 1}, goto="end"))
    eng.bind("b", lambda ctx: seen.__setitem__("b", dict(ctx.state)) or NodeResult(updates={"b": 1}, goto="end"))
    eng.bind("end", lambda ctx: NodeResult(updates={"answer": "done"}))
    res = eng.run("alpha topic shared", state={"seed": 0})
    assert res.terminated_by == "sink"
    # Neither handler saw the other's intra-step write ("a"/"b" keys absent).
    assert "a" not in seen["a"] and "a" not in seen["b"]
    assert "b" not in seen["a"] and "b" not in seen["b"]
    # But both saw the pre-run state, and the final state has both writes.
    assert seen["a"]["seed"] == 0 and seen["b"]["seed"] == 0
    assert res.state["a"] == 1 and res.state["b"] == 1


# -- Phase 4: wavefront (expanding parallel activation) ---------------------

def test_wavefront_flow_expands_width():
    m = Manifold(HashEmbedder(dim=256))
    caps = [Capability(f"c{i}", f"cap number {i} shared topic") for i in range(6)]
    m.register_many(caps)
    eng = Engine(m, flow=WavefrontFlow(base_width=1, growth=1))
    for c in caps:
        eng.bind(c.id, lambda ctx: NodeResult(intent="cap number shared topic"))

    res = eng.run("cap number 0 shared topic", max_steps=3)
    assert res.terminated_by == "budget"
    # The fan-out widens each step: width 1 -> 2 -> 3.
    assert [len(g) for g in res.step_groups] == [1, 2, 3]


def test_wavefront_resets_between_runs():
    m = Manifold(HashEmbedder(dim=256))
    caps = [Capability(f"c{i}", f"cap number {i} shared topic") for i in range(6)]
    m.register_many(caps)
    flow = WavefrontFlow(base_width=1, growth=1)
    eng = Engine(m, flow=flow)
    for c in caps:
        eng.bind(c.id, lambda ctx: NodeResult(intent="cap number shared topic"))
    r1 = eng.run("cap number 0 shared topic", max_steps=2)
    r2 = eng.run("cap number 0 shared topic", max_steps=2)
    # Both runs start from width 1 (reset), not from the previous run's counter.
    assert len(r1.step_groups[0]) == 1
    assert len(r2.step_groups[0]) == 1
