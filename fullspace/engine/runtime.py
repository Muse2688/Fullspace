"""The runtime — the closed loop that executes capabilities on the manifold.

Execution models:
* ``run``    / ``stream``    — synchronous; ``stream`` yields a ``StepEvent`` per step.
* ``ainvoke``/ ``astream``   — asynchronous; node handlers may be ``async def``
  (e.g. async LLM calls). ``astream`` yields ``StepEvent`` per step.

A checkpoint is written after every step when a ``thread_id`` and ``checkpointer``
are supplied, so streaming, async, and persistence compose freely.
"""

from __future__ import annotations

import asyncio
import inspect
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, AsyncIterator, Iterator, Optional

import numpy as np

from fullspace.engine.flow import DiscreteFlow, FlowPolicy
from fullspace.engine.router import Router
from fullspace.engine.terminator import Terminator
from fullspace.engine.types import (
    NodeContext,
    NodeHandler,
    NodeResult,
    RunResult,
    StepEvent,
    coerce_result,
)
from fullspace.manifold.manifold import Manifold
from fullspace.manifold.types import Capability, Hit
from fullspace.state.channels import StateSpec, merge_updates
from fullspace.state.checkpoint import Checkpoint, Checkpointer


class Engine:
    """Executes a task by routing over the capability manifold.

    Args:
        manifold: the capability manifold (positions + ANN index).
        flow: flow policy (default discrete; use ``FieldFlow``/``WavefrontFlow``).
        router: the mixed router (default coarse ANN, no LLM).
        terminator: termination logic.
        handlers: optional mapping of capability id -> handler (sync or async).
        max_steps: override the terminator's step budget.
        state_spec: per-key reducers for state merging (default overwrite).
        checkpointer: enables persistence/resume/time-travel with a thread_id.
    """

    def __init__(
        self,
        manifold: Manifold,
        flow: Optional[FlowPolicy] = None,
        router: Optional[Router] = None,
        terminator: Optional[Terminator] = None,
        handlers: Optional[dict[str, NodeHandler]] = None,
        max_steps: Optional[int] = None,
        state_spec: Optional[StateSpec] = None,
        checkpointer: Optional[Checkpointer] = None,
    ):
        self.manifold = manifold
        self.flow = flow or DiscreteFlow()
        self.terminator = terminator or Terminator(
            max_steps=max_steps if max_steps is not None else 25
        )
        self.router = router or Router(manifold)
        self.handlers: dict[str, NodeHandler] = dict(handlers or {})
        self.state_spec: StateSpec = dict(state_spec or {})
        self.checkpointer = checkpointer
        self._pool: Optional[ThreadPoolExecutor] = None

    def shutdown(self) -> None:
        """Release the internal handler thread pool (call when done with the engine)."""
        if self._pool is not None:
            self._pool.shutdown(wait=True)
            self._pool = None

    # -- binding ------------------------------------------------------------

    def bind(self, capability_id: str, handler: NodeHandler) -> "Engine":
        self.handlers[capability_id] = handler
        return self

    def bind_many(self, handlers: dict[str, NodeHandler]) -> "Engine":
        self.handlers.update(handlers)
        return self

    # -- synchronous execution ----------------------------------------------

    def run(
        self,
        task: str,
        state: Optional[dict[str, Any]] = None,
        thread_id: Optional[str] = None,
        max_steps: Optional[int] = None,
    ) -> RunResult:
        """Run ``task`` to completion synchronously and return the final result."""
        state = dict(state or {})
        trajectory: list[str] = []
        step_groups: list[list[str]] = []
        if len(self.manifold) == 0:
            return self._finish("empty", state, trajectory, step_groups, 0, None, thread_id)
        self.flow.reset()
        active = self.flow.select(self.manifold, task)
        if not active:
            return self._finish("empty", state, trajectory, step_groups, 0, None, thread_id)
        budget = max_steps if max_steps is not None else self.terminator.max_steps
        return self._collect_sync(
            self._steps_sync(task, state, trajectory, step_groups, 0, active, thread_id, budget),
            step_groups,
        )

    def stream(
        self,
        task: str,
        state: Optional[dict[str, Any]] = None,
        thread_id: Optional[str] = None,
        max_steps: Optional[int] = None,
    ) -> Iterator[StepEvent]:
        """Yield a ``StepEvent`` after each step (synchronous streaming)."""
        state = dict(state or {})
        trajectory: list[str] = []
        step_groups: list[list[str]] = []
        if len(self.manifold) == 0:
            yield StepEvent(0, [], {}, state, [], True, "empty")
            return
        self.flow.reset()
        active = self.flow.select(self.manifold, task)
        if not active:
            yield StepEvent(0, [], {}, state, [], True, "empty")
            return
        budget = max_steps if max_steps is not None else self.terminator.max_steps
        yield from self._steps_sync(task, state, trajectory, step_groups, 0, active, thread_id, budget)

    # -- asynchronous execution --------------------------------------------

    async def ainvoke(
        self,
        task: str,
        state: Optional[dict[str, Any]] = None,
        thread_id: Optional[str] = None,
        max_steps: Optional[int] = None,
    ) -> RunResult:
        """Async run to completion; node handlers may be ``async def``."""
        last: Optional[StepEvent] = None
        step_groups: list[list[str]] = []
        async for ev in self.astream(task, state=state, thread_id=thread_id, max_steps=max_steps):
            last = ev
            if ev.group:
                step_groups.append(list(ev.group))
        if last is None:
            return RunResult(dict(state or {}), [], 0, "empty", None, step_groups)
        final_id = last.trajectory[-1] if last.trajectory else None
        reason = last.terminated_by or "unknown"
        return RunResult(last.state, last.trajectory, last.step, reason, final_id, step_groups)

    async def astream(
        self,
        task: str,
        state: Optional[dict[str, Any]] = None,
        thread_id: Optional[str] = None,
        max_steps: Optional[int] = None,
    ) -> AsyncIterator[StepEvent]:
        """Async streaming; yields a ``StepEvent`` per step. Awaits async handlers."""
        state = dict(state or {})
        trajectory: list[str] = []
        step_groups: list[list[str]] = []
        if len(self.manifold) == 0:
            yield StepEvent(0, [], {}, state, [], True, "empty")
            return
        self.flow.reset()
        active = self.flow.select(self.manifold, task)
        if not active:
            yield StepEvent(0, [], {}, state, [], True, "empty")
            return
        budget = max_steps if max_steps is not None else self.terminator.max_steps
        async for ev in self._steps_async(task, state, trajectory, step_groups, 0, active, thread_id, budget):
            yield ev

    # -- resume (sync + async) ---------------------------------------------

    def resume(self, thread_id: str, task: str, max_steps: Optional[int] = None) -> RunResult:
        if self.checkpointer is None:
            raise ValueError("resume requires a checkpointer")
        cp = self.checkpointer.get(thread_id)
        if cp is None:
            raise KeyError(f"no checkpoint for thread {thread_id!r}")
        state, trajectory, step_groups, step = self._restore(cp)
        budget = max_steps if max_steps is not None else self.terminator.max_steps
        self.flow.reset()
        active = self.flow.select(self.manifold, task)
        if not active:
            return RunResult(state, trajectory, step, "empty", None, step_groups)
        return self._collect_sync(
            self._steps_sync(task, state, trajectory, step_groups, step, active, thread_id, budget),
            step_groups,
        )

    async def aresume(self, thread_id: str, task: str, max_steps: Optional[int] = None) -> RunResult:
        if self.checkpointer is None:
            raise ValueError("aresume requires a checkpointer")
        cp = self.checkpointer.get(thread_id)
        if cp is None:
            raise KeyError(f"no checkpoint for thread {thread_id!r}")
        state, trajectory, step_groups, step = self._restore(cp)
        budget = max_steps if max_steps is not None else self.terminator.max_steps
        self.flow.reset()
        active = self.flow.select(self.manifold, task)
        last: Optional[StepEvent] = None
        if active:
            async for ev in self._steps_async(task, state, trajectory, step_groups, step, active, thread_id, budget):
                last = ev
        final_id = last.trajectory[-1] if (last and last.trajectory) else None
        reason = (last.terminated_by or "unknown") if last is not None else "empty"
        steps = last.step if last is not None else step
        return RunResult(state, trajectory, steps, reason, final_id, step_groups)

    # -- time-travel inspection --------------------------------------------

    def history(self, thread_id: str) -> list[Checkpoint]:
        if self.checkpointer is None:
            return []
        return self.checkpointer.list(thread_id)

    def get_checkpoint(self, thread_id: str, checkpoint_id: Optional[str] = None) -> Optional[Checkpoint]:
        if self.checkpointer is None:
            return None
        return self.checkpointer.get(thread_id, checkpoint_id)

    # -- the synchronous step loop (generator) ------------------------------

    def _steps_sync(
        self, task, state, trajectory, step_groups, step, active, thread_id, budget
    ) -> Iterator[StepEvent]:
        while active:
            group = [h.capability.id for h in active]
            step_groups.append(group)
            trajectory.extend(group)
            step_updates, intents, gotos, halted, sink_hit, last_id = self._prep(active)

            if any(h.capability.id not in self.handlers for h in active):
                yield self._end_step(state, trajectory, step_groups, step, group, step_updates,
                                     thread_id, "no_handler", last_id)
                return
            for h, result in zip(active, self._run_group(task, state, trajectory, step, active)):
                cap = h.capability
                self._absorb(state, result, step_updates)
                halted |= result.halt
                sink_hit |= cap.is_sink
                if result.goto:
                    gotos.append(result.goto)
                if result.intent is not None:
                    intents.append((result.intent, h.score))

            step += 1
            active = self._after_step(
                state, trajectory, step_groups, step, group, step_updates, thread_id,
                budget, halted, sink_hit, gotos, intents,
            )
            if isinstance(active, str):  # termination reason
                yield self._end_step(state, trajectory, step_groups, step, group, step_updates, thread_id, active, last_id)
                return
            if active is None:  # mid-step termination already yielded inside _after_step? no
                return
            yield StepEvent(step, list(group), dict(step_updates), dict(state), list(trajectory), False, None)

    # -- the asynchronous step loop (async generator) -----------------------

    async def _steps_async(
        self, task, state, trajectory, step_groups, step, active, thread_id, budget
    ) -> AsyncIterator[StepEvent]:
        while active:
            group = [h.capability.id for h in active]
            step_groups.append(group)
            trajectory.extend(group)
            step_updates, intents, gotos, halted, sink_hit, last_id = self._prep(active)

            if any(h.capability.id not in self.handlers for h in active):
                yield self._end_step(state, trajectory, step_groups, step, group, step_updates,
                                     thread_id, "no_handler", last_id)
                return
            for h, result in zip(active, await self._run_group_async(task, state, trajectory, step, active)):
                cap = h.capability
                self._absorb(state, result, step_updates)
                halted |= result.halt
                sink_hit |= cap.is_sink
                if result.goto:
                    gotos.append(result.goto)
                if result.intent is not None:
                    intents.append((result.intent, h.score))

            step += 1
            nxt = self._after_step(
                state, trajectory, step_groups, step, group, step_updates, thread_id,
                budget, halted, sink_hit, gotos, intents,
            )
            if isinstance(nxt, str):
                yield self._end_step(state, trajectory, step_groups, step, group, step_updates, thread_id, nxt, last_id)
                return
            if nxt is None:
                return
            active = nxt
            yield StepEvent(step, list(group), dict(step_updates), dict(state), list(trajectory), False, None)

    # -- shared step helpers ------------------------------------------------

    def _prep(self, active):
        step_updates: dict[str, Any] = {}
        intents: list[tuple[Any, float]] = []
        gotos: list[str] = []
        halted = False
        sink_hit = False
        last_id = active[-1].capability.id
        return step_updates, intents, gotos, halted, sink_hit, last_id

    def _absorb(self, state, result: NodeResult, step_updates: dict) -> None:
        merge_updates(state, result.updates, self.state_spec)
        step_updates.update(result.updates)

    def _after_step(
        self, state, trajectory, step_groups, step, group, step_updates, thread_id,
        budget, halted, sink_hit, gotos, intents
    ):
        """Return the next active list, or a termination-reason string.

        Writes the mid-run (continuing) checkpoint only; termination checkpoints
        are written by ``_end_step`` so every termination path is persisted.
        """
        reason = self._terminate_reason(step, budget, halted, sink_hit)
        if reason is None and not gotos and not intents:
            reason = "no_intent"
        if reason is not None:
            return reason
        self._put_checkpoint(thread_id, step, state, trajectory, step_groups, None)
        if gotos:
            nxt = self.manifold.get(gotos[0])
            return "bad_goto" if nxt is None else [Hit(nxt, 1.0)]
        nxt_active = self._route_next(intents)
        return "no_route" if nxt_active is None else nxt_active

    def _end_step(self, state, trajectory, step_groups, step, group, step_updates, thread_id, reason, last_id) -> StepEvent:
        self._put_checkpoint(thread_id, step, state, trajectory, step_groups, reason)
        return StepEvent(step, list(group), dict(step_updates), dict(state), list(trajectory), True, reason)

    def _collect_sync(self, gen: Iterator[StepEvent], step_groups: list[list[str]]) -> RunResult:
        last: Optional[StepEvent] = None
        for ev in gen:
            last = ev
        if last is None:
            return RunResult({}, [], 0, "empty", None, step_groups)
        final_id = last.trajectory[-1] if last.trajectory else None
        reason = last.terminated_by or "unknown"
        return RunResult(last.state, last.trajectory, last.step, reason, final_id, step_groups)

    async def _invoke_handler_async(self, handler: NodeHandler, ctx: NodeContext) -> NodeResult:
        res = handler(ctx)
        if inspect.isawaitable(res):
            res = await res
        return coerce_result(res)

    # -- concurrent group execution (barrier-free neighbourhoods) ------------

    def _run_group(self, task, state, trajectory, step, active) -> list[NodeResult]:
        """Execute one step's handlers concurrently; merge afterwards, in order.

        Every handler sees a snapshot of the step-start state (co-activated
        capabilities must not observe each other's half-merged writes), and the
        merged result order follows activation order — runs stay deterministic.
        """
        if len(active) == 1:
            ctx = NodeContext(state=dict(state), trajectory=list(trajectory), step=step, task=task)
            return [self._invoke_sync(self.handlers[active[0].capability.id], ctx)]
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="fullspace")
        futures = []
        for h in active:
            ctx = NodeContext(state=dict(state), trajectory=list(trajectory), step=step, task=task)
            futures.append(self._pool.submit(self._invoke_sync, self.handlers[h.capability.id], ctx))
        return [f.result() for f in futures]

    async def _run_group_async(self, task, state, trajectory, step, active) -> list[NodeResult]:
        """Async counterpart of ``_run_group``: ``asyncio.gather`` runs the
        co-activated handlers concurrently (``async def`` handlers overlap their
        awaits; sync handlers are offloaded to threads)."""
        if len(active) == 1:
            ctx = NodeContext(state=dict(state), trajectory=list(trajectory), step=step, task=task)
            return [await self._invoke_handler_async(self.handlers[active[0].capability.id], ctx)]
        ctxs = [
            NodeContext(state=dict(state), trajectory=list(trajectory), step=step, task=task)
            for _ in active
        ]
        results = await asyncio.gather(*(
            self._offload(self.handlers[h.capability.id], ctx)
            for h, ctx in zip(active, ctxs)
        ))
        return list(results)

    def _invoke_sync(self, handler: NodeHandler, ctx: NodeContext) -> NodeResult:
        """Call a handler on the synchronous path (``run``/``stream``).

        ``async def`` handlers are rejected with a clear error — they need the
        async API (``ainvoke``/``astream``); the returned coroutine is closed
        unstarted so no "never awaited" warning leaks.
        """
        res = handler(ctx)
        if inspect.isawaitable(res):
            close = getattr(res, "close", None)
            if close is not None:
                close()
            raise TypeError(
                "async handlers require the async API: use ainvoke/astream "
                "instead of run/stream"
            )
        return coerce_result(res)

    async def _offload(self, handler: NodeHandler, ctx: NodeContext) -> NodeResult:
        """Run a handler in a thread; await the result there if it is awaitable.

        Sync handlers must not block the event loop while their neighbours
        (possibly async) are being awaited concurrently. Calling an ``async def``
        in a thread only creates its coroutine, which is then awaited on the
        loop — safe for every handler shape, including wrapped callables.
        """
        res = await asyncio.to_thread(handler, ctx)
        if inspect.isawaitable(res):
            res = await res
        return coerce_result(res)

    def _restore(self, cp: Checkpoint):
        return dict(cp.state), list(cp.trajectory), [list(g) for g in cp.step_groups], cp.step

    # -- termination / persistence / routing -------------------------------

    def _terminate_reason(self, step: int, budget: int, halted: bool, sink_hit: bool) -> Optional[str]:
        if step >= budget:
            return "budget"
        if halted:
            return "halt"
        if sink_hit:
            return "sink"
        return None

    def _finish(self, reason, state, trajectory, step_groups, step, last_id, thread_id) -> RunResult:
        self._put_checkpoint(thread_id, step, state, trajectory, step_groups, reason)
        return RunResult(state, trajectory, step, reason, last_id, step_groups)

    def _put_checkpoint(self, thread_id, step, state, trajectory, step_groups, terminated_by) -> None:
        if not (thread_id and self.checkpointer):
            return
        parent = self.checkpointer.get(thread_id)
        cp = Checkpoint(
            # Unique per write: re-running a thread appends to the timeline
            # instead of overwriting earlier checkpoints (time-travel safe).
            checkpoint_id=f"{thread_id}:{step:04d}:{uuid.uuid4().hex[:8]}",
            thread_id=thread_id,
            step=step,
            state=dict(state),
            trajectory=list(trajectory),
            step_groups=[list(g) for g in step_groups],
            parent_id=parent.checkpoint_id if parent else None,
            terminated_by=terminated_by,
        )
        self.checkpointer.put(cp)

    def _route_next(self, intents: list[tuple[Any, float]]):
        if isinstance(self.flow, DiscreteFlow):
            intent = max(intents, key=lambda x: x[1])[0]
            decision = self.router.route(intent)
            if decision.capability is None:
                return None
            return [Hit(decision.capability, decision.score)]
        query_vec = self._combine_intents(intents)
        hits = self.flow.select(self.manifold, query_vec)
        if hits:
            return hits
        if self.router.materializer is not None:
            cap = self.router.materializer("materialized:field", 0.0)
            if cap is not None:  # a declined spawn falls through to no_route
                self.manifold.register(cap)
                return [Hit(cap, 1.0)]
        return None

    def _combine_intents(self, intents: list[tuple[Any, float]]) -> np.ndarray:
        vecs = np.vstack([self.manifold._as_vector(it) for it, _ in intents])
        weights = np.array([max(w, 1e-6) for _, w in intents], dtype=np.float32)
        weights /= weights.sum()
        return (vecs * weights[:, None]).sum(axis=0)
