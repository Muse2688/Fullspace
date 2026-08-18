"""Bidirectional interop with the LangChain/LangGraph ecosystem.

This is the "load-bearing wall" for replacing LangGraph rather than sitting
beside it:

* ``as_capability``           — embed a compiled LangGraph app as a Fullspace
                                capability (LG -> FS).
* ``as_langgraph_node``       — expose a Fullspace engine as a LangGraph node (FS -> LG).
* ``FullspaceRunnable``       — expose a Fullspace engine as a langchain Runnable,
                                usable in LangChain chains, LangServe, etc.
* ``LangGraphCheckpointer``   — use any LangGraph checkpoint saver
                                (Sqlite/Postgres/...) as Fullspace's persistence
                                backend.
* ``export_trajectory_to_neo4j`` — write run trajectories into Neo4j for
                                lineage/observability analysis.
"""

from fullspace.interop.checkpoint import LangGraphCheckpointer
from fullspace.interop.fs_to_lg import as_langgraph_node
from fullspace.interop.lg_to_fs import as_capability
from fullspace.interop.neo4j import export_trajectory_to_neo4j
from fullspace.interop.runnable import FullspaceRunnable

__all__ = [
    "as_capability",
    "as_langgraph_node",
    "FullspaceRunnable",
    "LangGraphCheckpointer",
    "export_trajectory_to_neo4j",
]
