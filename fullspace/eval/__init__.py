"""Dual-track evaluation harness: Fullspace vs LangGraph.

Measures, on identical workflows expressed in both frameworks:

* ``success``        — does it produce the expected trajectory/answer?
* ``node_executions`` — how many node functions ran?
* ``routing_calls``  — how many "where next" decisions? (fs: ANN queries; lg: conditional-edge routers)
* ``elapsed_ms``     — wall-clock (noisy for tiny graphs; indicative only)
* ``deterministic``  — same input -> same trajectory across two runs

and an **expressiveness** verdict per pattern (can LangGraph express it at all?).

Run:  python -m fullspace.eval
"""

from fullspace.eval.cases import CASES, CaseResult, run_all
from fullspace.eval.metrics import Metrics, format_table

__all__ = ["CASES", "CaseResult", "run_all", "Metrics", "format_table"]
