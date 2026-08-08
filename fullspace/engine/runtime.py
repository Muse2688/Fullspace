"""The runtime — the closed loop that executes capabilities on the manifold.

Phase 4: a step may activate multiple capabilities (field diffusion).
Phase 2: per-key reducers + checkpointer-backed persistence, resume, and
time-travel. A checkpoint is written after every step when a ``thread_id`` and
``checkpointer`` are supplied.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from fullspace.engine.flow import DiscreteFlow, FlowPolicy
from fullspace.engine.router import Router
from fullspace.engine.terminator import Terminator
from fullspace.engine.types import (
    NodeContext,
    NodeHandler,
    NodeResult,
    RunResult,
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
        flow: flow policy (default discrete; use ``FieldFlow`` for parallelism).
        router: the mixed router (default coarse ANN, no LLM).
        terminator: termination logic.
        handlers: optional mapping of capability id -> handler.
        max_steps: override the terminator's step budget.
        state_spec: per-key reducers for state merging (default overwrite).
        checkpointer: enables persistence/resume/time-travel when a thread_id is
            passed to ``run``.
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

    # -- binding ------------------------------------------------------------

    def bind(self, capability_id: str, handler: NodeHandler) -> "Engine":
        self.handlers[capability_id] = handler
        return self

    def bind_many(self, handlers: dict[str, NodeHandler]) -> "Engine":
        self.handlers.update(handlers)
        return self

    # -- public execution ---------------------------------------------------

    def run(
        self,
        task: str,
        state: Optional[dict[str, Any]] = None,
        thread_id: Optional[str] = None,
        max_steps: Optional[int] = None,
    ) -> RunResult:
        """Run ``task`` from scratch (or from the given seed ``state``)."""
        state = dict(state or {})
        trajectory: list[str] = []
        step_groups: list[list[str]] = []

        if len(self.manifold) == 0:
            return self._finish("empty", state, trajectory, step_groups, 0, None, thread_id)

        self.flow.reset()  # reset per-run state (e.g. wavefront step counter)
        active = self.flow.select(self.manifold, task)
        if not active:
            return self._finish("empty", state, trajectory, step_groups, 0, None, thread_id)

        budget = max_steps if max_steps is not None else self.terminator.max_steps
        return self._execute(task, state, trajectory, step_groups, 0, active, thread_id, budget)

    def resume(
        self,
        thread_id: str,
        task: str,
        max_steps: Optional[int] = None,
    ) -> RunResult:
        """Continue a thread from its latest checkpoint, routing from ``task``."""
        if self.checkpointer is None:
            raise ValueError("resume requires a checkpointer")
        cp = self.checkpointer.get(thread_id)
        if cp is None:
            raise KeyError(f"no checkpoint for thread {thread_id!r}")
        state = dict(cp.state)
        trajectory = list(cp.trajectory)
        step_groups = [list(g) for g in cp.step_groups]
        step = cp.step
        budget = max_steps if max_steps is not None else self.terminator.max_steps
        self.flow.reset()
        active = self.flow.select(self.manifold, task)
        if not active:
            return self._finish("empty", state, trajectory, step_groups, step, None, thread_id)
        return self._execute(task, state, trajectory, step_groups, step, active, thread_id, budget)

    # -- time-travel inspection --------------------------------------------

    def history(self, thread_id: str) -> list[Checkpoint]:
        if self.checkpointer is None:
            return []
        return self.checkpointer.list(thread_id)

    def get_checkpoint(self, thread_id: str, checkpoint_id: Optional[str] = None) -> Optional[Checkpoint]:
        if self.checkpointer is None:
            return None
        return self.checkpointer.get(thread_id, checkpoint_id)

    # -- the loop -----------------------------------------------------------

    def _execute(
        self,
        task: str,
        state: dict,
        trajectory: list[str],
        step_groups: list[list[str]],
        step: int,
        active: list[Hit],
        thread_id: Optional[str],
        budget: int,
    ) -> RunResult:
        while active:
            group = [h.capability.id for h in active]
            step_groups.append(group)
            trajectory.extend(group)

            intents: list[tuple[Any, float]] = []
            gotos: list[str] = []
            halted = False
            sink_hit = False
            last_id = active[-1].capability.id

            for h in active:
                cap = h.capability
                handler = self.handlers.get(cap.id)
                if handler is None:
                    return self._finish("no_handler", state, trajectory, step_groups, step, cap.id, thread_id)
                ctx = NodeContext(state=state, trajectory=list(trajectory), step=step, task=task)
                result: NodeResult = coerce_result(handler(ctx))
                merge_updates(state, result.updates, self.state_spec)
                if result.halt:
                    halted = True
                if cap.is_sink:
                    sink_hit = True
                if result.goto:
                    gotos.append(result.goto)
                if result.intent is not None:
                    intents.append((result.intent, h.score))

            step += 1

            # Decide termination, then persist this step's checkpoint.
            reason = self._terminate_reason(step, budget, halted, sink_hit)
            if reason is None and not gotos and not intents:
                reason = "no_intent"
            if reason is not None:
                return self._finish(reason, state, trajectory, step_groups, step, last_id, thread_id)

            # Persist a mid-run checkpoint (continuing).
            self._put_checkpoint(thread_id, step, state, trajectory, step_groups, None)

            # Advance to the next step.
            if gotos:
                nxt = self.manifold.get(gotos[0])
                if nxt is None:
                    return self._finish("bad_goto", state, trajectory, step_groups, step, last_id, thread_id)
                active = [Hit(nxt, 1.0)]
            else:
                nxt_active = self._route_next(intents)
                if nxt_active is None:
                    return self._finish("no_route", state, trajectory, step_groups, step, last_id, thread_id)
                active = nxt_active

        return self._finish("no_route", state, trajectory, step_groups, step, None, thread_id)

    # -- helpers ------------------------------------------------------------

    def _terminate_reason(self, step: int, budget: int, halted: bool, sink_hit: bool) -> Optional[str]:
        if step >= budget:
            return "budget"
        if halted:
            return "halt"
        if sink_hit:
            return "sink"
        return None

    def _finish(
        self, reason, state, trajectory, step_groups, step, last_id, thread_id
    ) -> RunResult:
        self._put_checkpoint(thread_id, step, state, trajectory, step_groups, reason)
        return RunResult(state, trajectory, step, reason, last_id, step_groups)

    def _put_checkpoint(self, thread_id, step, state, trajectory, step_groups, terminated_by) -> None:
        if not (thread_id and self.checkpointer):
            return
        parent = self.checkpointer.get(thread_id)
        cp = Checkpoint(
            checkpoint_id=f"{thread_id}:{step:04d}",
            thread_id=thread_id,
            step=step,
            state=dict(state),
            trajectory=list(trajectory),
            step_groups=[list(g) for g in step_groups],
            parent_id=parent.checkpoint_id if parent else None,
            terminated_by=terminated_by,
        )
        self.checkpointer.put(cp)

    def _route_next(self, intents: list[tuple[Any, float]]) -> Optional[list[Hit]]:
        """Turn the previous step's intents into the next activated set."""
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
            self.manifold.register(cap)
            return [Hit(cap, 1.0)]
        return None

    def _combine_intents(self, intents: list[tuple[Any, float]]) -> np.ndarray:
        """Score-weighted average of intent vectors — the field's direction."""
        vecs = np.vstack([self.manifold._as_vector(it) for it, _ in intents])
        weights = np.array([max(w, 1e-6) for _, w in intents], dtype=np.float32)
        weights /= weights.sum()
        return (vecs * weights[:, None]).sum(axis=0)
