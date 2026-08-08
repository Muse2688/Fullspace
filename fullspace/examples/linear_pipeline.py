"""Linear pipeline: search -> summarize -> end.

This is the LangGraph-equivalent flow under Fullspace's discrete policy:
the particle hops node-to-node, but *where* it hops is decided by soft routing
on intent vectors (and one exact ``goto``), not by pre-wired edges.

Run:  python -m fullspace.examples.linear_pipeline
"""

from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import Engine, NodeContext, NodeResult


def build() -> Engine:
    m = Manifold(HashEmbedder())
    m.register_many(
        [
            Capability("search", "search the web for information"),
            Capability("summarize", "summarize a long document into key points"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    eng = Engine(m)

    def search(ctx: NodeContext):
        findings = f"found facts about: {ctx.task}"
        # Soft route: the next node is whichever capability is nearest to this
        # intent in the manifold (here: 'summarize').
        return NodeResult(
            updates={"findings": findings},
            intent="summarize the findings into key points",
        )

    def summarize(ctx: NodeContext):
        summary = f"summary of {ctx.state['findings']}"
        # Hard route: exact hop to a known capability (LangGraph-style edge).
        return NodeResult(updates={"summary": summary}, goto="end")

    def end(ctx: NodeContext):
        # Sink: produces the final output. No intent -> run, then terminate.
        return NodeResult(updates={"answer": ctx.state.get("summary", "")})

    eng.bind_many({"search": search, "summarize": summarize, "end": end})
    return eng


def main() -> None:
    eng = build()
    res = eng.run("search for information about quantum entanglement")
    print("trajectory   :", res.trajectory)
    print("terminated_by:", res.terminated_by)
    print("answer       :", res.state.get("answer"))


if __name__ == "__main__":
    main()
