# Fullspace

**The capability-manifold agent runtime — route autonomous agents over a high-dimensional capability space instead of hard-wired graphs.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![CI](https://github.com/Muse2688/Fullspace/actions/workflows/ci.yml/badge.svg)](https://github.com/Muse2688/Fullspace/actions/workflows/ci.yml)
[![mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](http://mypy-lang.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

> 🌐 **Languages:** [English](README.md) · [简体中文](README.zh-CN.md)

---

## Why Fullspace

Mainstream agent frameworks inherit a 60-year-old abstraction: the **graph**. You
declare nodes, wire edges, and a router evaluates every conditional branch to decide
where to go next. This works — but it caps what agents can do:

- **Topology is frozen at compile time.** You cannot grow the agent at runtime.
- **Routing is discrete enumeration.** A conditional edge can only return a name you
  already declared — no interpolation, no graceful degradation.
- **Every branch costs a routing decision.** Scale to *N* specialists and routing
  becomes *O(N)* per step.

Fullspace replaces edge-wiring with **capability-space routing**. Each capability is a
point in a high-dimensional semantic manifold; "where next" is answered by a single
nearest-neighbour query, not by traversing a wiring diagram. The 3D *sphere* you
navigate is just a human-facing projection of that space — **routing never uses the
projection**, exactly because a graph has no inherent dimension.

> **Thesis:** *capability-space routing beats edge-wiring.* Locating the right
> capability with one vector query — instead of pre-wiring *N* edges and evaluating a
> router per branch — is the single substitution from which every Fullspace advantage
> follows.

## Features

| | Feature | What it means |
|---|---|---|
| 🧭 | **Capability-space routing** | Soft routing by semantic proximity — no enumerated node names. |
| ✨ | **Dynamic materialization** | Spawn a capability on demand when nothing matches (emergent topology). |
| 🌊 | **Multi-modal execution** | Discrete (graph-equivalent), field diffusion, and wavefront flow policies. |
| ⚡ | **Barrier-free parallelism** | Activate a neighbourhood per step — no superstep synchronization barrier. |
| 🛡️ | **Graceful OOD degradation** | Always routes to the nearest capability; no explicit fallback wiring required. |
| 🔁 | **Bidirectional LangGraph interop** | Embed a LangGraph subgraph as a region; export Fullspace as a LangGraph node; run as a langchain `Runnable`. |
| 💾 | **Persistence & time-travel** | In-memory + SQLite checkpointers; resume; checkpoint history. |
| 📈 | **Sublinear scaling** | Drop in FAISS for *O(log N)* routing at manifold scale. |
| 🔄 | **Streaming & async** | `stream`/`astream` yield per-step events; `async def` node handlers (LangGraph stream parity). |
| 🚀 | **Embedding cache** | Memoizes recurring intent embeddings (20× fewer calls in loops). |
| 🔬 | **Deterministic & reproducible** | Seedable, same-input-same-trajectory by construction. |

## How it works

```
                          capability manifold
        (high-dimensional embedding; 3D sphere is its projection for navigation)

            ·search        ·calc              ·summarize
               \             |                   /
                \            |                  /
   task ─► embed ─► ANN ─► nearest region ─► run handler
                /            |                  \
               /             |                   \
            ·translate     ·code                ·plan

   ┌──────────────────────────────────────────────────────────────┐
   │  locate ─► run ─► (state Δ + intent vector) ─► route ─► ...  │
   │            terminate on  sink / halt / budget                │
   └──────────────────────────────────────────────────────────────┘
```

A **flow policy** decides how many capabilities activate per step (discrete → 1;
field/wavefront → a neighbourhood). The **mixed router** performs one coarse
nearest-neighbour hop by default, escalating to an LLM disambiguator only at genuinely
ambiguous junctions, and can **materialize** a new capability on a near-miss. See
[docs/architecture.md](docs/architecture.md) for the full design.

## Installation

> `fullspace` is **not yet on PyPI** (the name is available — publishing is planned).
> Install from GitHub for now:

```bash
# core (zero heavy deps)
pip install git+https://github.com/Muse2688/Fullspace.git
pip install faiss-cpu                       # + sublinear ANN at scale
```

With extras (LangGraph interop/eval, tests, mypy), clone and install editable:

```bash
git clone https://github.com/Muse2688/Fullspace.git
cd Fullspace
pip install -e ".[langgraph,dev]"
```

> Fullspace is dependency-light by default: only NumPy is required. FAISS,
> sentence-transformers, UMAP, and LangGraph are **optional** extras — install the ones
> you need and Fullspace uses them automatically.

## Quickstart

```python
from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import Engine, NodeResult

manifold = Manifold(HashEmbedder())
manifold.register_many([
    Capability("search",    "search the web for information"),
    Capability("calc",      "perform arithmetic and math calculations"),
    Capability("summarize", "summarize a long document into key points"),
    Capability("end",       "final answer output", metadata={"sink": True}),
])

agent = Engine(manifold)
agent.bind("search",    lambda ctx: NodeResult(updates={"found": "..."},
                                              intent="summarize a long document into key points"))
agent.bind("summarize", lambda ctx: NodeResult(updates={"summary": "..."}, goto="end"))
agent.bind("end",       lambda ctx: NodeResult(updates={"answer": "..."}))

result = agent.run("search the web for information")
print(result.trajectory)   # ['search', 'summarize', 'end']
```

Replace `HashEmbedder` with `SentenceTransformersEmbedder` or `OpenAIEmbedder`, and the
plain handlers with LLM-backed ones, to move from runnable mechanics to production
semantics.

## Benchmarks (vs. real LangGraph)

Fullspace is benchmarked head-to-head against the installed LangGraph package on
identical workflows (`python -m fullspace.eval`):

| Axis | Result |
|---|---|
| Correctness & node-execution on mirrored patterns (linear / branch / loop / ReAct) | **Parity** |
| **Expressiveness** — dynamic materialization | **Fullspace** (LangGraph inexpressible) |
| **OOD robustness** — no fallback wired | **Fullspace** (LangGraph errors) |
| **Routing latency at scale** — FAISS, `eval.scaling` | **Fullspace** (~80–123× at *N*=5k–20k) |
| **Barrier-free parallelism** | **Fullspace** |
| Ecosystem compatibility | **Fullspace** (bidirectional interop + `Runnable`) |
| Routing overhead on tiny static graphs | LangGraph (pre-wired edges are free; recovered at scale) |

The harness is the source of truth — run it before claiming any win. Methodology and
scaling curves: `python -m fullspace.eval.scaling`.

## Examples

| Example | Pattern |
|---|---|
| [`linear_pipeline`](fullspace/examples/linear_pipeline.py) | `A → B → C` (graph-equivalent) |
| [`branching`](fullspace/examples/branching.py) | task-dependent soft routing |
| [`react_agent`](fullspace/examples/react_agent.py) | ReAct loop (think → act → observe) |
| [`interrupt_resume`](fullspace/examples/interrupt_resume.py) | human-in-the-loop / fault tolerance |
| [`streaming`](fullspace/examples/streaming.py) | sync + async streaming (`async def` handlers) |

```bash
python -m fullspace.examples.react_agent
python -m fullspace.viz            # interactive 3D capability sphere → fullspace_sphere.html
```

## Roadmap

- [x] Manifold substrate, ANN index, 3D projection
- [x] Engine: discrete / field / wavefront flow policies, mixed router
- [x] State: per-key reducers, checkpointing, resume, time-travel
- [x] Bidirectional LangGraph interop & langchain `Runnable`
- [x] Dual-track evaluation harness + FAISS scaling
- [x] Streaming + async (`stream` / `astream` / `ainvoke`, `async def` node handlers)
- [x] Embedding cache for recurring intents
- [ ] Speculative pre-warming & neighbour prefix caching *(lands with real-LLM integration)*
- [ ] Continuous-navigation flow policy
- [ ] Reference integrations: OpenAI, Anthropic, sentence-transformers

## Contributing

Contributions are welcome. The codebase is fully type-checked (`mypy` clean) and covered
by 68 tests. Run `pip install -e ".[langgraph,dev]" && pytest -q` before opening a PR.

## Citation

If Fullspace informs your work, please cite it:

```bibtex
@software{fullspace,
  title  = {Fullspace: A Capability-Manifold Agent Runtime},
  author = {Fullspace},
  year   = {2026},
  url    = {https://github.com/Muse2688/Fullspace},
  note   = {Capability-space routing as a successor to graph-based agent orchestration}
}
```

Conceptual lineage: graph-structured agent runtimes draw on the **Pregel** bulk-synchronous
model (Malewicz et al., 2010). Fullspace reframes agent routing as nearest-neighbour
retrieval over a continuous **capability manifold** — relating to mixture-of-experts and
dense retrieval — so that topology can emerge at runtime rather than be declared statically.

## License

[MIT](LICENSE) © Fullspace
