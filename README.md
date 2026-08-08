# Fullspace

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-53%20passing-brightgreen.svg)](#run)

A **3D capability-manifold** agent orchestration framework — a **superset** replacement for LangGraph.

> **The thesis, in two facts:**
> 1. A graph has no inherent dimension — drawing N nodes on a sphere is the same graph as on a plane. For "3D" to mean anything, geometry must carry semantic meaning.
> 2. Capability-space routing beats edge-wiring — locate the right capability with one nearest-neighbour query instead of pre-wiring N edges.
>
> So Fullspace's substrate is a **high-dimensional embedding manifold** (used for routing); the **3D sphere is only its projection** (for human navigation/viz). Routing never uses the projection. See [docs/architecture.md](docs/architecture.md).

## What it does that LangGraph can't

- **Soft routing** by proximity in capability space (no enumerated node names).
- **Dynamic materialization** — create a capability on demand when nothing is close enough (LangGraph's compiled graph can't add nodes).
- **Barrier-free parallelism** — field/wavefront flow policies activate sets per step.
- **Graceful OOD degradation** — always routes to the nearest capability; no explicit fallback wiring needed.
- **Bidirectional interop** — a LangGraph subgraph embeds as a Fullspace region; Fullspace exports as a LangGraph node; engines are langchain `Runnable`s.
- **Persistence & time-travel** — checkpointer (in-memory + SQLite), resume, checkpoint history.

## Install

```bash
pip install -e .                         # core, zero heavy deps
pip install -e ".[langgraph,dev]"        # + interop/eval + tests/mypy
pip install faiss-cpu                    # + sublinear ANN for large manifolds
```

## Run

```bash
python -m pytest tests/                  # 53 tests
python -m fullspace.examples.linear_pipeline
python -m fullspace.examples.branching
python -m fullspace.examples.react_agent
python -m fullspace.examples.interrupt_resume
python -m fullspace.eval                 # dual-track benchmark vs real LangGraph
python -m fullspace.eval.scaling         # FAISS routing-latency scaling
python -m fullspace.viz                  # 3D capability sphere -> fullspace_sphere.html
python -m mypy fullspace                 # type check (0 errors)
```

## Quick start

```python
from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import Engine, NodeResult

m = Manifold(HashEmbedder())
m.register_many([
    Capability("search",  "search the web for information"),
    Capability("calc",    "perform arithmetic and math calculations"),
    Capability("summarize","summarize a long document into key points"),
    Capability("end",     "final answer output", metadata={"sink": True}),
])

eng = Engine(m)
eng.bind("search",   lambda ctx: NodeResult(updates={"found": "..."}, intent="summarize a long document into key points"))
eng.bind("summarize",lambda ctx: NodeResult(updates={"summary": "..."}, goto="end"))
eng.bind("end",      lambda ctx: NodeResult(updates={"answer": "..."}))

res = eng.run("search the web for information")
print(res.trajectory, res.state["answer"])
```

## Honest benchmark vs LangGraph (`python -m fullspace.eval`)

| Axis | Result |
|---|---|
| Correctness + node-execution on mirrored patterns (linear/branch/loop/ReAct) | **parity** |
| Expressiveness (dynamic materialization) | **Fullspace wins** — LangGraph inexpressible |
| OOD robustness (no explicit fallback wired) | **Fullspace wins** — LangGraph errors |
| Routing latency at scale (FAISS, `eval.scaling`) | **Fullspace wins** — ~80–123× at N=5k–20k |
| Barrier-free parallelism (field/wavefront) | **Fullspace wins** |
| Ecosystem compat | **Fullspace wins** — bidirectional interop + Runnable |
| Routing overhead on tiny static graphs | LangGraph (its pre-wired edges are free; recovered at scale) |

The eval harness is the source of truth — run it before claiming any win.

## Status

All planned phases implemented and tested (53 tests, mypy clean):
manifold substrate · engine + flow policies (discrete/field/wavefront) · mixed router ·
state/reducers/checkpointing/time-travel · bidirectional LangGraph interop ·
dual-track eval + FAISS scaling · 3D sphere viz.

**Deferred** (most meaningful once real LLMs are plugged in): speculative pre-warming,
neighbour prefix caching. Swap `HashEmbedder` for `SentenceTransformersEmbedder`/`OpenAIEmbedder`
and bind LLM-backed handlers to go from mechanics to production semantics.
