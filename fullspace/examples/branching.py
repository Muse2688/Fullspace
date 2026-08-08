"""Branching: the same manifold soft-routes different tasks to different starts.

There are no conditional edges to declare. The task text itself is embedded and
routed to the nearest capability, so 'perform math calculations' lands on
``calc`` while 'search the web' lands on ``search``. This is capability-space
routing replacing edge-wiring.

Run:  python -m fullspace.examples.branching
"""

from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import Engine, NodeContext, NodeResult


def build() -> Engine:
    m = Manifold(HashEmbedder())
    m.register_many(
        [
            Capability("calc", "perform arithmetic and math calculations"),
            Capability("search", "search the web for information"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    eng = Engine(m)

    def worker(ctx: NodeContext):
        return NodeResult(updates={"result": f"handled by {ctx.trajectory[-1]}"}, goto="end")

    def end(ctx: NodeContext):
        return NodeResult(updates={"answer": ctx.state.get("result", "")})

    eng.bind_many({"calc": worker, "search": worker, "end": end})
    return eng


def main() -> None:
    eng = build()
    tasks = [
        "perform math calculations on numbers",
        "search the web for information about cats",
    ]
    for task in tasks:
        res = eng.run(task)
        print(f"{task!r}\n  -> trajectory={res.trajectory} terminated_by={res.terminated_by}\n")


if __name__ == "__main__":
    main()
