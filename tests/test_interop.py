"""Tests for bidirectional LangGraph interop (Phase 3).

All three directions are exercised against the real langgraph + langchain_core
packages: a LangGraph app embedded inside Fullspace, a Fullspace engine embedded
inside a LangGraph graph, and a Fullspace engine used as a langchain Runnable.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import Engine, NodeResult
from fullspace.interop import FullspaceRunnable, as_capability, as_langgraph_node


# -- helpers ----------------------------------------------------------------

def _uppercase_app():
    """A trivial compiled LangGraph app: uppercase state['text']."""

    class S(TypedDict):
        text: str

    def upper(s):
        return {"text": s["text"].upper()}

    g = StateGraph(S)
    g.add_node("u", upper)
    g.add_edge(START, "u")
    g.add_edge("u", END)
    return g.compile()


# -- LG -> FS ---------------------------------------------------------------

def test_langgraph_app_embedded_in_fullspace():
    app = _uppercase_app()
    m = Manifold(HashEmbedder(dim=256))
    eng = Engine(m)

    cap, handler = as_capability(
        app, "translate", "translate uppercase the text", goto="end"
    )
    m.register(cap)
    m.register(Capability("end", "final answer output", metadata={"sink": True}))
    eng.bind("translate", handler)
    eng.bind("end", lambda ctx: NodeResult(updates={"answer": ctx.state.get("text")}))

    res = eng.run("translate uppercase the text", state={"text": "hello"})
    # The LangGraph subgraph ran inside Fullspace and its output flowed onward.
    assert "translate" in res.trajectory and "end" in res.trajectory
    assert res.state["text"] == "HELLO"
    assert res.state["answer"] == "HELLO"


# -- FS -> LG ---------------------------------------------------------------

def test_fullspace_engine_embedded_in_langgraph():
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(
        [
            Capability("greet", "greet the user hello"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    eng = Engine(m)
    eng.bind(
        "greet",
        lambda ctx: NodeResult(updates={"greeting": f"hi {ctx.state.get('name', '')}"}, goto="end"),
    )
    eng.bind("end", lambda ctx: NodeResult(updates={"done": True}))

    node = as_langgraph_node(eng, task="greet the user hello")

    class S(TypedDict):
        name: str
        greeting: str
        done: bool

    g = StateGraph(S)
    g.add_node("fs", node)
    g.add_edge(START, "fs")
    g.add_edge("fs", END)
    app = g.compile()

    out = app.invoke({"name": "ada", "greeting": "", "done": False})
    # Fullspace ran inside LangGraph and its update is visible.
    assert out["greeting"] == "hi ada"


# -- Runnable ---------------------------------------------------------------

def test_fullspace_engine_as_runnable():
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(
        [
            Capability("echo", "echo the input back"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    eng = Engine(m)
    eng.bind("echo", lambda ctx: NodeResult(updates={"out": ctx.task}, goto="end"))
    eng.bind("end", lambda ctx: NodeResult(updates={"ok": True}))

    r = FullspaceRunnable(eng)
    res = r.invoke({"task": "echo the input back"})
    assert res["state"]["out"] == "echo the input back"
    assert "echo" in res["trajectory"]
    assert res["terminated_by"] == "sink"

    # String input also works.
    res2 = r.invoke("echo the input back")
    assert res2["state"]["out"] == "echo the input back"


# -- round-trip: FS engine that internally runs an LG app, itself run as a Runnable

def test_roundtrip_runnable_wrapping_engine_wrapping_langgraph():
    app = _uppercase_app()
    m = Manifold(HashEmbedder(dim=256))
    eng = Engine(m)
    cap, handler = as_capability(app, "up", "translate uppercase the text", goto="end")
    m.register(cap)
    m.register(Capability("end", "final answer output", metadata={"sink": True}))
    eng.bind("up", handler)
    eng.bind("end", lambda ctx: NodeResult(updates={"answer": ctx.state.get("text")}))

    r = FullspaceRunnable(eng)
    res = r.invoke({"task": "translate uppercase the text", "state": {"text": "roundtrip"}})
    assert res["state"]["answer"] == "ROUNDTRIP"
