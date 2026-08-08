"""Interrupt + resume: human-in-the-loop / fault tolerance on the manifold.

A long-running workflow is interrupted (here by a step budget — in production
this could be a human-in-the-loop pause or a crash), then resumed from its
checkpoint to completion. This is the persistence/time-travel capability that
matches LangGraph's checkpointer, demonstrated end to end.

Run:  python -m fullspace.examples.interrupt_resume
"""

from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import Engine, NodeContext, NodeResult
from fullspace.state import InMemoryCheckpointer


def build() -> Engine:
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(
        [
            Capability("work", "work repeat the processing step"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    eng = Engine(m, checkpointer=InMemoryCheckpointer())

    def work(ctx: NodeContext):
        remaining = ctx.state.get("n", 0) - 1
        if remaining > 0:
            return NodeResult(updates={"n": remaining}, intent="work repeat the processing step")
        return NodeResult(updates={"n": remaining}, goto="end")

    def end(ctx: NodeContext):
        return NodeResult(updates={"answer": "completed all steps"})

    eng.bind_many({"work": work, "end": end})
    return eng


def main() -> None:
    eng = build()
    total = 5

    # Run with a tiny budget: interrupts after 2 steps (budget guardrail).
    r1 = eng.run("work repeat the processing step", state={"n": total}, thread_id="job1", max_steps=2)
    print("after interrupt :", f"terminated_by={r1.terminated_by} trajectory={r1.trajectory} n={r1.state['n']}")

    # Inspect the time-travel timeline so far.
    hist = eng.history("job1")
    print("checkpoints     :", [(c.step, c.terminated_by) for c in hist])

    # Resume from the latest checkpoint and let it finish.
    r2 = eng.resume("job1", task="work repeat the processing step", max_steps=25)
    print("after resume    :", f"terminated_by={r2.terminated_by} trajectory={r2.trajectory} n={r2.state['n']}")
    print("answer          :", r2.state.get("answer"))


if __name__ == "__main__":
    main()
