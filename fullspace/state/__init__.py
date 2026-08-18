"""State model: per-key reducers (LangGraph-compatible) + persistence.

* ``channels``    — reducers (overwrite / add / last_value) + ``merge_updates``.
* ``checkpoint``  — ``Checkpoint`` + ``Checkpointer`` (in-memory + SQLite) for
                    persistence, resume, and time-travel.
* ``trajectory``  — the manifold trajectory as first-class spatial state.
"""

from fullspace.state.channels import StateSpec, add, last_value, merge_updates, overwrite
from fullspace.state.checkpoint import (
    Checkpoint,
    Checkpointer,
    InMemoryCheckpointer,
    MySqlCheckpointer,
    SqliteCheckpointer,
)
from fullspace.state.trajectory import annotate_positions

__all__ = [
    "StateSpec",
    "add",
    "overwrite",
    "last_value",
    "merge_updates",
    "Checkpoint",
    "Checkpointer",
    "InMemoryCheckpointer",
    "SqliteCheckpointer",
    "MySqlCheckpointer",
    "annotate_positions",
]
