"""A ReAct-style agent loop on the capability manifold.

ReAct (Reason + Act) is the canonical agent pattern: think -> act -> observe ->
think -> ... until the agent can answer. Under Fullspace this is just routing
over a manifold whose capabilities are the agent's reasoning phases; an LLM
would supply the intent vectors that hop between them. Here the "reasoning" is
deterministic so the example runs with no API key — swap the handlers for LLM
calls in production.

Run:  python -m fullspace.examples.react_agent
"""

from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import Engine, NodeContext, NodeResult


def build() -> Engine:
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(
        [
            Capability("think", "think reason about the problem and decide an action"),
            Capability("act", "act use a tool to make progress"),
            Capability("observe", "observe the result of the action"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    eng = Engine(m)

    def think(ctx: NodeContext):
        thoughts = ctx.state.get("thoughts", 0) + 1
        return NodeResult(
            updates={"thoughts": thoughts, "plan": f"step {thoughts}"},
            intent="act use a tool to make progress",
        )

    def act(ctx: NodeContext):
        actions = ctx.state.get("actions", 0) + 1
        return NodeResult(
            updates={"actions": actions, "last_tool": f"tool_{actions}"},
            intent="observe the result of the action",
        )

    def observe(ctx: NodeContext):
        # After enough reasoning cycles, produce the answer; otherwise loop back.
        if ctx.state.get("thoughts", 0) >= 2:
            return NodeResult(updates={"observation": "enough info"}, goto="end")
        return NodeResult(
            updates={"observation": "need more"},
            intent="think reason about the problem and decide an action",
        )

    def end(ctx: NodeContext):
        return NodeResult(updates={"answer": f"done after {ctx.state.get('actions', 0)} actions"})

    eng.bind_many({"think": think, "act": act, "observe": observe, "end": end})
    return eng


def main() -> None:
    eng = build()
    res = eng.run("think reason about the problem and decide an action")
    print("trajectory   :", res.trajectory)
    print("thoughts     :", res.state.get("thoughts"))
    print("actions      :", res.state.get("actions"))
    print("answer       :", res.state.get("answer"))


if __name__ == "__main__":
    main()
