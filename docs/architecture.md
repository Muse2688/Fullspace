# Fullspace — Architecture

Fullspace is a 3D **capability-manifold** agent orchestration framework: a superset
replacement for LangGraph. This document maps the design decisions to the code.

## The two facts that decide everything

1. **A graph has no inherent dimension.** Drawing N finite nodes on a 2D plane vs.
   on a sphere is the *same* graph (the complete graph Kₙ), which LangGraph already
   expresses via conditional edges. For "3D" to mean anything, geometry must carry
   computational semantics.
   → The substrate is a **high-dimensional embedding manifold** (used for routing);
   the **3D sphere is only its projection** (used by humans). Routing *never* uses
   the 3D projection. ([`fullspace/manifold/`](../fullspace/manifold/))

2. **Capability-space routing beats edge-wiring.** Instead of pre-wiring N edges and
   evaluating a router per branch, Fullspace locates the right capability with one
   nearest-neighbour query. That single substitution is the source of every advantage.

## Module map

| Package | Responsibility | Key types |
|---|---|---|
| `manifold/` | the substrate: descriptions → vectors, ANN index, 3D projection | `Manifold`, `Capability`, `Embedder`, `AnnIndex`, `Projector` |
| `engine/` | the closed loop + flow policies + router + termination | `Engine`, `Router`, `FlowPolicy` (`Discrete`/`Field`/`Wavefront`), `NodeResult`, `RunResult` |
| `state/` | per-key reducers + checkpointing (persistence/resume/time-travel) | `merge_updates`, `Checkpointer` (`InMemory`/`Sqlite`), `Checkpoint` |
| `interop/` | bidirectional LangGraph compatibility (the "load-bearing wall") | `as_capability` (LG→FS), `as_langgraph_node` (FS→LG), `FullspaceRunnable` |
| `eval/` | dual-track benchmark vs real LangGraph + FAISS scaling | `run_all`, `scaling.run` |
| `viz/` | 3D sphere visualization (HTML, no plotting dep) | `render_sphere` |
| `examples/` | runnable patterns | linear, branching, ReAct, interrupt/resume |

## The execution model (the closed loop)

```
task → embed → ANN locate start
  → step: activate capability(ies) [flow policy decides how many]
       → run handler(s) → merge updates [per-key reducers]
       → each returns an intent vector ("where next")
       → checkpoint (if thread_id + checkpointer)
       → combine intents → ANN route to next [mixed router: coarse hop, optional LLM at ambiguous junctions]
       → terminate on sink / halt / no-intent / budget
```

- **Discrete flow** activates one capability per step (LangGraph-equivalent).
- **Field flow** activates a neighbourhood per step (barrier-free parallelism).
- **Wavefront flow** activates a *widening* neighbourhood per step.
- The **mixed router** does one ANN query per hop by default (affinity pruning);
  it calls an LLM disambiguator only when the top-2 candidates are too close to
  call, and can **materialize** a new capability on a near-miss (spawn-on-miss).

## The four latency mechanisms (the axis Fullspace wins at scale)

1. **Affinity pruning** — one ANN query replaces N router evaluations. (`router.py`)
2. **Sublinear ANN** — FAISS IVFFlat beats O(N) routing ~80-123× at N=5k-20k. (`index.py`)
3. **Barrier-free parallelism** — field/wavefront activate sets without superstep barriers. (`flow/`)
4. **(deferred)** speculative pre-warm + neighbour prefix caching — most meaningful once real LLMs are plugged in.

## Extending Fullspace

- **New embedder**: subclass `Embedder`, implement `embed`/`dim`. (`manifold/embedding.py`)
- **New ANN backend**: subclass `AnnIndex` (`add`/`search`/`remove`). (`manifold/index.py`)
- **New flow policy**: subclass `FlowPolicy`, implement `select(manifold, query)`. (`engine/flow/`)
- **New checkpointer**: subclass `Checkpointer` (`put`/`get`/`list`). (`state/checkpoint.py`)

## Honest benchmark (vs real LangGraph)

Run `python -m fullspace.eval` and `python -m fullspace.eval.scaling`.

| Axis | Result |
|---|---|
| Correctness + node-execution on mirrored patterns | **parity** |
| Expressiveness (dynamic materialization) | **Fullspace wins** (LG inexpressible) |
| OOD robustness (no explicit fallback wired) | **Fullspace wins** (LG errors) |
| Routing latency at scale (FAISS) | **Fullspace wins** (~80-123×) |
| Barrier-free parallelism | **Fullspace wins** |
| Ecosystem compat | **Fullspace wins** (bidirectional interop + Runnable) |
| Routing overhead on tiny static graphs | LangGraph (its pre-wired edges are free; recovered at scale) |

The eval harness is the source of truth — run it before claiming any win.
