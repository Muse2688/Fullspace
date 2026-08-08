"""Per-key reducers for state merging (LangGraph channel/reducer model).

Each state key may have its own reducer controlling how a node's update
combines with the existing value. Default is ``overwrite`` (last-write-wins),
which matches the pre-Phase-2 behaviour and keeps everything backward
compatible. Use ``add`` for append-list channels (e.g. a message history).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

# A reducer maps (previous_value_or_None, incoming_value) -> merged_value.
Reducer = Callable[[Optional[Any], Any], Any]

# A StateSpec is just a mapping of state-key -> reducer.
StateSpec = dict


def overwrite(prev: Any, new: Any) -> Any:
    """Last-write-wins (the default)."""
    return new


def last_value(prev: Any, new: Any) -> Any:
    """Keep the previous value when the update is None; otherwise overwrite."""
    return new if new is not None else prev


def add(prev: Any, new: Any) -> Any:
    """Append: lists concatenate; scalars collect into a growing list."""
    base = (
        list(prev)
        if isinstance(prev, list)
        else ([] if prev is None else [prev])
    )
    if new is None:
        return base
    if isinstance(new, list):
        return base + new
    return base + [new]


def merge_updates(state: dict, updates: dict, spec: Optional[StateSpec] = None) -> dict:
    """Merge ``updates`` into ``state`` using per-key reducers from ``spec``.

    Keys without an explicit reducer use ``overwrite``.
    """
    spec = spec or {}
    for key, value in updates.items():
        reducer = spec.get(key, overwrite)
        state[key] = reducer(state.get(key), value)
    return state
