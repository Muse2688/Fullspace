"""Streaming + async: watch the agent execute step by step.

Mirrors LangGraph's ``stream`` / ``astream``: instead of blocking until the end,
you observe each step as it completes. The async variant also shows an
``async def`` node handler (where an async LLM / I/O call would go).

Run:  python -m fullspace.examples.streaming
"""

from __future__ import annotations

import asyncio

from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import Engine, NodeResult


def _manifold() -> Manifold:
    m = Manifold(HashEmbedder(dim=256))
    m.register_many(
        [
            Capability("plan", "plan the research steps"),
            Capability("search", "search the web for information"),
            Capability("summarize", "summarize the findings into key points"),
            Capability("end", "final answer output", metadata={"sink": True}),
        ]
    )
    return m


def demo_sync_stream() -> None:
    eng = Engine(_manifold())
    eng.bind("plan", lambda ctx: NodeResult(updates={"plan": "3 steps"}, intent="search the web for information"))
    eng.bind("search", lambda ctx: NodeResult(updates={"found": "facts"}, intent="summarize the findings into key points"))
    eng.bind("summarize", lambda ctx: NodeResult(updates={"summary": "short"}, goto="end"))
    eng.bind("end", lambda ctx: NodeResult(updates={"answer": ctx.state.get("summary")}))

    print("sync stream - one event per step:")
    for ev in eng.stream("plan the research steps"):
        print(f"  step {ev.step}: activated={ev.group}  terminated={ev.terminated}"
              + (f"  ({ev.terminated_by})" if ev.terminated else ""))


async def demo_async_astream() -> None:
    eng = Engine(_manifold())

    async def search(ctx):  # async handler — e.g. an async LLM / HTTP call
        await asyncio.sleep(0)
        return NodeResult(updates={"found": "facts (async)"}, intent="summarize the findings into key points")

    eng.bind("plan", lambda ctx: NodeResult(updates={"plan": "3 steps"}, intent="search the web for information"))
    eng.bind("search", search)
    eng.bind("summarize", lambda ctx: NodeResult(updates={"summary": "short"}, goto="end"))
    eng.bind("end", lambda ctx: NodeResult(updates={"answer": ctx.state.get("summary")}))

    print("\nasync stream - async node handler awaited:")
    async for ev in eng.astream("plan the research steps"):
        print(f"  step {ev.step}: activated={ev.group}  state.answer={ev.state.get('answer')!r}")


def main() -> None:
    demo_sync_stream()
    asyncio.run(demo_async_astream())


if __name__ == "__main__":
    main()
