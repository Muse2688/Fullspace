"""Use any LangGraph checkpoint saver as Fullspace's persistence backend.

``LangGraphCheckpointer`` adapts a ``langgraph.checkpoint.base.BaseCheckpointSaver``
(SqliteSaver, AsyncSqliteSaver, PostgresSaver, ...) to Fullspace's simple
``Checkpointer`` interface. Fullspace's (state, trajectory, step_groups) are
stored as channel values inside the LangGraph checkpoint, so resume and
time-travel work unchanged — while the actual storage, and its production
backends, come from the LangGraph ecosystem.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fullspace.state.checkpoint import Checkpoint, Checkpointer

# Fullspace's timeline payload, stored as channels in the LangGraph checkpoint.
_KEY_STATE = "state"
_KEY_TRAJECTORY = "trajectory"
_KEY_STEP_GROUPS = "step_groups"
_KEYS = (_KEY_STATE, _KEY_TRAJECTORY, _KEY_STEP_GROUPS)


class LangGraphCheckpointer(Checkpointer):  # pragma: no cover - needs langgraph extra
    """Fullspace ``Checkpointer`` backed by a LangGraph ``BaseCheckpointSaver``.

    Requires the ``langgraph`` extra: ``pip install fullspace[langgraph]``.

    Example:
        import sqlite3
        from langgraph.checkpoint.sqlite import SqliteSaver
        from fullspace.interop import LangGraphCheckpointer

        saver = SqliteSaver(sqlite3.connect("checkpoints.db", check_same_thread=False))
        eng = Engine(m, checkpointer=LangGraphCheckpointer(saver))
        eng.run(task, state={...}, thread_id="t1")
    """

    def __init__(self, saver: Any):
        try:
            from langgraph.checkpoint.base import BaseCheckpointSaver  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "LangGraphCheckpointer needs the langgraph extra: "
                "pip install fullspace[langgraph]"
            ) from e
        self._saver = saver
        self._versions: dict[str, int] = {}
        # LangGraph savers order a thread's checkpoints by checkpoint_id string
        # (DESC). A zero-padded monotonic prefix makes that ordering equal the
        # write order; the uuid suffix keeps ids unique across saver instances.
        self._seq: int = 0
        self._id_map: dict[str, str] = {}

    # -- helpers -------------------------------------------------------------

    def _config(self, thread_id: str, checkpoint_id: Optional[str] = None) -> dict:
        cfg: dict[str, Any] = {
            "configurable": {"thread_id": thread_id, "checkpoint_ns": ""}
        }
        if checkpoint_id is not None:
            cfg["configurable"]["checkpoint_id"] = checkpoint_id
        return cfg

    # -- Checkpointer API ----------------------------------------------------

    def put(self, cp: Checkpoint) -> None:
        from langgraph.checkpoint.base import Checkpoint as LgCheckpoint

        # Parent chaining: the latest existing checkpoint on this thread.
        parent_cfg = None
        latest = self._saver.get_tuple(self._config(cp.thread_id))
        if latest is not None:
            parent_cfg = latest.config

        # Bump channel versions (LangGraph uses them for write tracking).
        new_versions: dict[str, str | int | float] = {}
        for k in _KEYS:
            self._versions[k] = self._versions.get(k, 0) + 1
            new_versions[k] = self._versions[k]
        self._seq += 1

        lg_cp = LgCheckpoint(
            v=1,
            id=f"{self._seq:012d}-{uuid.uuid4().hex[:16]}",
            ts=datetime.now(timezone.utc).isoformat(),
            channel_values={
                _KEY_STATE: cp.state,
                _KEY_TRAJECTORY: cp.trajectory,
                _KEY_STEP_GROUPS: cp.step_groups,
            },
            channel_versions=new_versions,
            versions_seen={},
            updated_channels=None,
        )
        # `put` stores under thread_id, chaining to the config's checkpoint as parent.
        stored = self._saver.put(
            parent_cfg or self._config(cp.thread_id),
            lg_cp,
            {"source": "fullspace", "step": cp.step, "terminated_by": cp.terminated_by},
            new_versions,
        )
        # Remember our id -> the saver's checkpoint id for point lookups.
        self._id_map[cp.checkpoint_id] = stored["configurable"]["checkpoint_id"]

    def _from_tuple(self, tup) -> Checkpoint:
        cv = tup.checkpoint["channel_values"]
        cfg_id = tup.config["configurable"].get("checkpoint_id")
        return Checkpoint(
            checkpoint_id=cfg_id,
            thread_id=tup.config["configurable"]["thread_id"],
            step=tup.metadata.get("step", 0) if isinstance(tup.metadata, dict) else 0,
            state=dict(cv.get(_KEY_STATE, {})),
            trajectory=list(cv.get(_KEY_TRAJECTORY, [])),
            step_groups=[list(g) for g in cv.get(_KEY_STEP_GROUPS, [])],
            parent_id=(tup.parent_config or {}).get("configurable", {}).get("checkpoint_id"),
            terminated_by=(tup.metadata or {}).get("terminated_by") if isinstance(tup.metadata, dict) else None,
        )

    def get(self, thread_id: str, checkpoint_id: Optional[str] = None) -> Optional[Checkpoint]:
        if checkpoint_id is not None:
            id_map = getattr(self, "_id_map", {})
            saver_id = id_map.get(checkpoint_id, checkpoint_id)
            tup = self._saver.get_tuple(self._config(thread_id, saver_id))
        else:
            tup = self._saver.get_tuple(self._config(thread_id))
        return self._from_tuple(tup) if tup is not None else None

    def list(self, thread_id: str) -> list[Checkpoint]:
        # LangGraph's list yields newest-first; Fullspace's API is oldest-first.
        tups = list(self._saver.list(self._config(thread_id)))
        return [self._from_tuple(t) for t in reversed(tups)]
