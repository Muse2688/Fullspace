"""Metrics + comparison/reporting for the eval harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Metrics:
    """Measurements from one framework on one case."""

    framework: str  # "fullspace" | "langgraph"
    success: bool
    actual_path: list[str]
    node_executions: int
    routing_calls: int
    elapsed_ms: float
    deterministic: bool = True
    notes: str = ""


@dataclass
class CaseResult:
    """Outcome of one eval case across both frameworks."""

    name: str
    pattern: str
    task: str
    expected_path: list[str]
    fs: Optional[Metrics]
    lg: Optional[Metrics]  # None => LangGraph cannot express this pattern
    lg_expressible: bool

    def verdict(self) -> str:
        if not self.lg_expressible:
            return "FS WINS - expressiveness (LG cannot express)"
        assert self.fs is not None and self.lg is not None
        parts = []
        # Correctness
        if self.fs.success and self.lg.success:
            parts.append("correctness: tie")
        elif self.fs.success and not self.lg.success:
            parts.append("correctness: FS")
        else:
            parts.append("correctness: LG")
        # Node executions (fewer is better)
        if self.fs.node_executions < self.lg.node_executions:
            parts.append("exec: FS")
        elif self.fs.node_executions > self.lg.node_executions:
            parts.append("exec: LG")
        else:
            parts.append("exec: tie")
        # Routing calls (fewer is better)
        if self.fs.routing_calls < self.lg.routing_calls:
            parts.append("route: FS")
        elif self.fs.routing_calls > self.lg.routing_calls:
            parts.append("route: LG")
        else:
            parts.append("route: tie")
        return "; ".join(parts)


def format_table(results: list[CaseResult]) -> str:
    """Render results as a readable per-pattern block (no fixed column widths)."""
    lines: list[str] = []

    def line(m: Optional[Metrics], label: str) -> str:
        if m is None:
            return f"    {label:<10}: -- (inexpressible by LangGraph)"
        det = "det" if m.deterministic else "NONDET"
        ok = "ok" if m.success else "FAIL"
        return (
            f"    {label:<10}: {ok:<4} path={m.actual_path} "
            f"exec={m.node_executions} route={m.routing_calls} {det}"
        )

    for r in results:
        lines.append(f"== {r.pattern} ==")
        lines.append(f"    task     : {r.task!r}")
        lines.append(f"    expected : {r.expected_path}")
        lines.append(line(r.fs, "Fullspace"))
        lines.append(line(r.lg, "LangGraph"))
        lines.append(f"    verdict  : {r.verdict()}")
        if r.fs and r.fs.notes:
            lines.append(f"    notes    : {r.fs.notes}")
        lines.append("")
    return "\n".join(lines)
