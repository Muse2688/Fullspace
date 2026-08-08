"""Tests for the eval harness."""

from __future__ import annotations

from fullspace.eval.cases import run_all


def test_all_fullspace_cases_succeed():
    results = run_all()
    assert len(results) == 6
    for r in results:
        assert r.fs is not None
        assert r.fs.success, f"{r.name}: fs failed (path {r.fs.actual_path})"
        assert r.fs.deterministic, f"{r.name}: fs not deterministic"


def test_mirrored_patterns_langgraph_succeeds_except_ood():
    # On every mirrored pattern LangGraph also succeeds, EXCEPT the OOD case
    # where it is expected to error (that is Fullspace's robustness win).
    results = run_all()
    for r in results:
        if not r.lg_expressible:
            continue
        if r.name == "ood_robustness":
            assert r.lg is not None and r.lg.success is False
        else:
            assert r.lg is not None and r.lg.success, f"{r.name}: lg failed"
            assert r.lg.deterministic, f"{r.name}: lg not deterministic"


def test_dynamic_spawn_is_fullspace_only():
    results = {r.name: r for r in run_all()}
    ds = results["dynamic_spawn"]
    assert ds.lg_expressible is False
    assert ds.lg is None
    assert ds.fs.success
    assert ds.fs.actual_path == ["a", "dyn", "end"]


def test_node_execution_parity_on_linear():
    results = {r.name: r for r in run_all()}
    lin = results["linear"]
    assert lin.fs.node_executions == lin.lg.node_executions == 3


def test_react_loop_node_execution_parity():
    results = {r.name: r for r in run_all()}
    rl = results["react_loop"]
    # The canonical agent loop: identical 7 node executions in both frameworks.
    assert rl.fs.node_executions == rl.lg.node_executions == 7
    assert rl.fs.success and rl.lg.success


def test_ood_robustness_fullspace_wins():
    results = {r.name: r for r in run_all()}
    ood = results["ood_robustness"]
    assert ood.fs.success is True          # degrades to nearest, no fallback wiring
    assert ood.lg.success is False         # errors without an explicit default branch
