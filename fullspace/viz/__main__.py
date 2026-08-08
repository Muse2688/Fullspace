"""CLI demo: build a small manifold, run a workflow, render the 3D sphere.

    python -m fullspace.viz
    # then open fullspace_sphere.html in a browser
"""

from __future__ import annotations

from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import Engine, NodeResult
from fullspace.viz import render_sphere


def main() -> None:
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(
        [
            Capability("search", "search the web for information"),
            Capability("calc", "perform arithmetic and math calculations"),
            Capability("translate", "translate text between languages"),
            Capability("summarize", "summarize a long document into key points"),
            Capability("code", "write and run python code"),
            Capability("plan", "plan the steps of a complex task"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    eng = Engine(m)

    def search(ctx):
        return NodeResult(updates={"found": "facts"}, intent="summarize the findings key points")
    def summarize(ctx):
        return NodeResult(updates={"summary": "short"}, goto="end")
    def end(ctx):
        return NodeResult(updates={"answer": ctx.state.get("summary", "")})

    eng.bind_many({"search": search, "summarize": summarize, "end": end})
    res = eng.run("search the web for information")
    print("trajectory:", res.trajectory)

    out = render_sphere(m, step_groups=res.step_groups, output_path="fullspace_sphere.html")
    print(f"wrote {out} - open it in a browser to see the 3D capability sphere.")


if __name__ == "__main__":
    main()
