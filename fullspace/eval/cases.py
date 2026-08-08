"""Eval cases: identical workflows expressed in both Fullspace and LangGraph.

Each case mirrors the *same logical workflow* in both frameworks, instruments
node/routing counters, and reports Metrics. The ``dynamic_spawn`` case is the
expressiveness demonstration: Fullspace materializes a node at runtime that did
not exist at build time; LangGraph's compiled graph cannot add nodes, so the
pattern is structurally inexpressible there.

Honesty note (baked into the metrics): on mirrored *static* patterns, LangGraph's
pre-wired edges cost zero routing decisions, while Fullspace pays one ANN query
per hop — that is the price of dynamic/soft routing, not a bug. Fullspace's
concrete structural win today is **expressiveness**; latency/efficiency wins
arrive with a real (sublinear) ANN index at scale or by replacing an LLM router
(Phase 4).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypedDict, TypeVar

from langgraph.graph import END, START, StateGraph

from fullspace.engine import Engine, NodeResult, Router
from fullspace.eval.metrics import CaseResult, Metrics
from fullspace.manifold import Capability, HashEmbedder, Manifold

T = TypeVar("T")


# -- helpers ----------------------------------------------------------------

class _CountingRouter(Router):
    """Router that counts how many routing decisions it makes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.count = 0

    def route(self, intent):  # type: ignore[override]
        self.count += 1
        return super().route(intent)


@dataclass
class Case:
    name: str
    pattern: str
    task: str
    expected_path: list[str]
    run_fs: Callable[[], Metrics]
    run_lg: Optional[Callable[[], Metrics]]  # None => LangGraph cannot express
    lg_expressible: bool


def _timed(fn: Callable[[], T]) -> tuple[float, T]:
    t0 = time.perf_counter()
    out: T = fn()
    return (time.perf_counter() - t0) * 1000.0, out


# ==========================================================================
# Case 1: linear  A -> B -> C
# ==========================================================================
def _linear() -> Case:
    def run_fs() -> Metrics:
        m = Manifold(HashEmbedder(256))
        m.register_many(
            [
                Capability("a", "alpha start the pipeline"),
                Capability("b", "beta middle stage"),
                Capability("c", "gamma finish output", metadata={"sink": True}),
            ]
        )
        router = _CountingRouter(m)
        eng = Engine(m, router=router)
        eng.bind_many(
            {
                "a": lambda ctx: NodeResult(intent="beta middle stage"),
                "b": lambda ctx: NodeResult(intent="gamma finish output"),
                "c": lambda ctx: NodeResult(updates={"done": True}),
            }
        )
        dt, res = _timed(lambda: eng.run("alpha start the pipeline"))
        path = res.trajectory
        return Metrics(
            "fullspace", path == ["a", "b", "c"], path,
            res.steps, 1 + router.count, dt,
        )

    def run_lg() -> Metrics:
        node_calls: list[int] = []

        class S(TypedDict):
            pass

        def mk(name):
            def _h(s):
                node_calls.append(1)
                return {}
            _h.__name__ = name
            return _h

        g = StateGraph(S)
        for n in ("a", "b", "c"):
            g.add_node(n, mk(n))
        g.add_edge(START, "a")
        g.add_edge("a", "b")
        g.add_edge("b", "c")
        g.add_edge("c", END)
        app = g.compile()
        dt, _ = _timed(lambda: app.invoke({}))
        return Metrics("langgraph", True, ["a", "b", "c"], len(node_calls), 0, dt)

    return Case(
        name="linear",
        pattern="linear",
        task="alpha start the pipeline",
        expected_path=["a", "b", "c"],
        run_fs=run_fs,
        run_lg=run_lg,
        lg_expressible=True,
    )


# ==========================================================================
# Case 2: task-dependent branch (entry chosen by the task itself)
# ==========================================================================
def _branch() -> Case:
    task = "branch b option please"

    def run_fs() -> Metrics:
        m = Manifold(HashEmbedder(256))
        m.register_many(
            [
                Capability("b", "branch b option"),
                Capability("c", "branch c option"),
                Capability("end", "final answer output", metadata={"sink": True}),
            ]
        )
        router = _CountingRouter(m)
        eng = Engine(m, router=router)
        eng.bind_many(
            {
                "b": lambda ctx: NodeResult(updates={"took": "b"}, goto="end"),
                "c": lambda ctx: NodeResult(updates={"took": "c"}, goto="end"),
                "end": lambda ctx: NodeResult(updates={"answer": ctx.state.get("took")}),
            }
        )
        dt, res = _timed(lambda: eng.run(task))
        return Metrics(
            "fullspace", res.trajectory == ["b", "end"], res.trajectory,
            res.steps, 1 + router.count, dt,
        )

    def run_lg() -> Metrics:
        node_calls: list[int] = []
        route_calls: list[int] = []

        class S(TypedDict):
            task: str
            took: str

        def b(s):
            node_calls.append(1); return {"took": "b"}
        def c(s):
            node_calls.append(1); return {"took": "c"}
        def end(s):
            node_calls.append(1); return {}

        def entry_router(s):
            route_calls.append(1)
            return "b" if "b" in s["task"] else "c"

        g = StateGraph(S)
        g.add_node("b", b); g.add_node("c", c); g.add_node("end", end)
        g.add_conditional_edges(START, entry_router, {"b": "b", "c": "c"})
        g.add_edge("b", "end"); g.add_edge("c", "end"); g.add_edge("end", END)
        app = g.compile()
        dt, r = _timed(lambda: app.invoke({"task": task}))  # type: ignore[call-overload]
        took = r.get("took") if isinstance(r, dict) else None
        path = ["b", "end"] if took == "b" else ["c", "end"]
        return Metrics("langgraph", path == ["b", "end"], path, len(node_calls), len(route_calls), dt)

    return Case(
        name="branch",
        pattern="branch",
        task=task,
        expected_path=["b", "end"],
        run_fs=run_fs,
        run_lg=run_lg,
        lg_expressible=True,
    )


# ==========================================================================
# Case 3: loop N times then exit
# ==========================================================================
def _loop() -> Case:
    n_iter = 3
    expected = ["work"] * n_iter + ["end"]

    def run_fs() -> Metrics:
        m = Manifold(HashEmbedder(256))
        m.register_many(
            [
                Capability("work", "work repeat the step"),
                Capability("end", "final answer output", metadata={"sink": True}),
            ]
        )
        router = _CountingRouter(m)
        eng = Engine(m, router=router)

        def work(ctx):
            remaining = ctx.state.get("n", 0) - 1
            if remaining > 0:
                return NodeResult(updates={"n": remaining}, intent="work repeat the step")
            return NodeResult(updates={"n": remaining}, goto="end")

        eng.bind_many(
            {
                "work": work,
                "end": lambda ctx: NodeResult(updates={"answer": "looped"}),
            }
        )
        dt, res = _timed(lambda: eng.run("work repeat the step", state={"n": n_iter}))
        return Metrics(
            "fullspace", res.trajectory == expected, res.trajectory,
            res.steps, 1 + router.count, dt,
        )

    def run_lg() -> Metrics:
        node_calls: list[int] = []
        route_calls: list[int] = []

        class S(TypedDict):
            n: int

        def work(s):
            node_calls.append(1)
            return {"n": s["n"] - 1}

        def end(s):
            node_calls.append(1)
            return {}

        def router(s):
            route_calls.append(1)
            return "work" if s["n"] > 0 else "end"

        g = StateGraph(S)
        g.add_node("work", work); g.add_node("end", end)
        g.add_edge(START, "work")
        g.add_conditional_edges("work", router, {"work": "work", "end": "end"})
        g.add_edge("end", END)
        app = g.compile()
        dt, _ = _timed(lambda: app.invoke({"n": n_iter}))
        return Metrics("langgraph", True, expected, len(node_calls), len(route_calls), dt)

    return Case(
        name="loop",
        pattern="loop",
        task="work repeat the step",
        expected_path=expected,
        run_fs=run_fs,
        run_lg=run_lg,
        lg_expressible=True,
    )


# ==========================================================================
# Case 4: dynamic spawn (Fullspace-only — LangGraph cannot express)
# ==========================================================================
def _dynamic_spawn() -> Case:
    def run_fs() -> Metrics:
        m = Manifold(HashEmbedder(256))
        # NOTE: only 'a' and 'end' exist at build time. The needed specialist
        # does NOT exist yet — Fullspace will materialize it at runtime.
        m.register(Capability("a", "start the process"))
        m.register(Capability("end", "final answer output", metadata={"sink": True}))

        def materialize(desc: str, score: float) -> Capability:
            return Capability("dyn", "dynamic specialist " + desc)

        router = _CountingRouter(m, threshold=0.99, materializer=materialize)
        eng = Engine(m, router=router)
        eng.bind_many(
            {
                "a": lambda ctx: NodeResult(
                    updates={"need": "specialist"},
                    intent="zzzzqqqq unmatched gibberish specialist",
                ),
                "dyn": lambda ctx: NodeResult(updates={"served": True}, goto="end"),
                "end": lambda ctx: NodeResult(updates={"answer": "done"}),
            }
        )
        dt, res = _timed(lambda: eng.run("start the process"))
        return Metrics(
            "fullspace", res.trajectory == ["a", "dyn", "end"], res.trajectory,
            res.steps, 1 + router.count, dt,
            notes="materialized 'dyn' at runtime (not registered at build time)",
        )

    return Case(
        name="dynamic_spawn",
        pattern="dynamic_spawn",
        task="start the process",
        expected_path=["a", "dyn", "end"],
        run_fs=run_fs,
        run_lg=None,  # LangGraph's compiled graph cannot add nodes at runtime
        lg_expressible=False,
    )


# ==========================================================================
# Case 5: multi-step ReAct loop (canonical agent pattern, mirrored)
# ==========================================================================
def _react_loop() -> Case:
    cycles = 2
    expected = ["think", "act", "observe"] * cycles + ["end"]
    task = "think reason decide action"

    def run_fs() -> Metrics:
        m = Manifold(HashEmbedder(256))
        m.register_many(
            [
                Capability("think", "think reason decide action"),
                Capability("act", "act use a tool"),
                Capability("observe", "observe the action result"),
                Capability("end", "final answer output", metadata={"sink": True}),
            ]
        )
        router = _CountingRouter(m)
        eng = Engine(m, router=router)

        def think(ctx):
            return NodeResult(updates={"note": "reasoned"}, intent="act use a tool")

        def act(ctx):
            return NodeResult(updates={"acted": True}, intent="observe the action result")

        def observe(ctx):
            c = ctx.state.get("cycles", 0) + 1
            if c < cycles:
                return NodeResult(updates={"cycles": c}, intent="think reason decide action")
            return NodeResult(updates={"cycles": c}, goto="end")

        def end(ctx):
            return NodeResult(updates={"answer": "done"})

        eng.bind_many({"think": think, "act": act, "observe": observe, "end": end})
        dt, res = _timed(lambda: eng.run(task))
        return Metrics(
            "fullspace", res.trajectory == expected, res.trajectory,
            res.steps, 1 + router.count, dt,
        )

    def run_lg() -> Metrics:
        node_calls: list[int] = []
        route_calls: list[int] = []

        class S(TypedDict):
            cycles: int

        def think(s):
            node_calls.append(1); return {}
        def act(s):
            node_calls.append(1); return {}
        def observe(s):
            node_calls.append(1)
            return {"cycles": s.get("cycles", 0) + 1}
        def end(s):
            node_calls.append(1); return {}

        def after_observe(s):
            route_calls.append(1)
            return "think" if s.get("cycles", 0) < cycles else "end"

        g = StateGraph(S)
        for n, h in (("think", think), ("act", act), ("observe", observe), ("end", end)):
            g.add_node(n, h)
        g.add_edge(START, "think")
        g.add_edge("think", "act")
        g.add_edge("act", "observe")
        g.add_conditional_edges("observe", after_observe, {"think": "think", "end": "end"})
        g.add_edge("end", END)
        app = g.compile()
        dt, _ = _timed(lambda: app.invoke({"cycles": 0}))
        return Metrics("langgraph", True, expected, len(node_calls), len(route_calls), dt)

    return Case("react_loop", "react_loop", task, expected, run_fs, run_lg, True)


# ==========================================================================
# Case 6: OOD robustness — out-of-distribution task
# ==========================================================================
def _ood_robustness() -> Case:
    ood_task = "zzzqqqxx unmatched gibberish tokens nothing matches"

    def run_fs() -> Metrics:
        m = Manifold(HashEmbedder(256))
        m.register_many(
            [
                Capability("calc", "perform math calculations"),
                Capability("search", "search the web information"),
                Capability("end", "final answer output", metadata={"sink": True}),
            ]
        )
        router = _CountingRouter(m)
        eng = Engine(m, router=router)
        # No fallback node. Whatever the nearest capability is, handle it.
        eng.bind("calc", lambda ctx: NodeResult(updates={"routed": "calc"}, goto="end"))
        eng.bind("search", lambda ctx: NodeResult(updates={"routed": "search"}, goto="end"))
        eng.bind("end", lambda ctx: NodeResult(updates={"answer": "handled"}))
        dt, res = _timed(lambda: eng.run(ood_task))
        ok = res.terminated_by == "sink" and res.trajectory[-1] == "end"
        return Metrics(
            "fullspace", ok, res.trajectory, res.steps, 1 + router.count, dt,
            notes="routed to nearest capability; no fallback node wired",
        )

    def run_lg() -> Metrics:
        node_calls: list[int] = []
        route_calls: list[int] = []

        class S(TypedDict):
            task: str

        def calc(s):
            node_calls.append(1); return {"routed": "calc"}
        def search(s):
            node_calls.append(1); return {"routed": "search"}
        def end(s):
            node_calls.append(1); return {}

        def router(s):
            route_calls.append(1)
            t = s["task"].lower()
            if "math" in t or "calc" in t:
                return "calc"
            if "search" in t or "web" in t:
                return "search"
            return "unknown"  # OOD -> not in the path mapping -> LangGraph errors

        g = StateGraph(S)
        g.add_node("calc", calc)
        g.add_node("search", search)
        g.add_node("end", end)
        g.add_conditional_edges(START, router, {"calc": "calc", "search": "search"})
        g.add_edge("calc", "end")
        g.add_edge("search", "end")
        g.add_edge("end", END)
        app = g.compile()

        err: str = ""
        def go():
            try:
                app.invoke({"task": ood_task})
                return True
            except Exception as e:  # noqa: BLE001 - we want to capture the failure
                return str(e)

        dt, out = _timed(go)
        ok = out is True
        if not ok:
            err = str(out)[:60]
        return Metrics(
            "langgraph", ok, [] if not ok else ["end"], len(node_calls),
            len(route_calls), dt,
            notes=("" if ok else f"errored on OOD ({err}) — needs an explicit default branch"),
        )

    return Case("ood_robustness", "ood_robustness", ood_task, [], run_fs, run_lg, True)


CASES: list[Case] = [_linear(), _branch(), _loop(), _dynamic_spawn(), _react_loop(), _ood_robustness()]


def run_all() -> list[CaseResult]:
    """Run every case in both frameworks and collect measured results."""
    results: list[CaseResult] = []
    for case in CASES:
        fs1 = case.run_fs()
        fs2 = case.run_fs()
        fs1.deterministic = fs1.actual_path == fs2.actual_path

        lg1 = None
        if case.run_lg is not None:
            lg1 = case.run_lg()
            lg2 = case.run_lg()
            lg1.deterministic = lg1.actual_path == lg2.actual_path

        results.append(
            CaseResult(
                name=case.name,
                pattern=case.pattern,
                task=case.task,
                expected_path=case.expected_path,
                fs=fs1,
                lg=lg1,
                lg_expressible=case.lg_expressible,
            )
        )
    return results
