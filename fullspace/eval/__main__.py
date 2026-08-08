"""CLI: run the dual-track eval and print a comparison.

    python -m fullspace.eval
"""

from __future__ import annotations

from fullspace.eval.cases import run_all
from fullspace.eval.metrics import format_table


def main() -> None:
    results = run_all()
    print(format_table(results))
    print()

    # Honest summary.
    fs_correct = sum(1 for r in results if r.fs and r.fs.success)
    lg_correct = sum(1 for r in results if r.lg and r.lg.success)
    fs_only = sum(1 for r in results if not r.lg_expressible)
    total = len(results)

    print("summary")
    print("-------")
    print(f"  patterns total              : {total}")
    print(f"  Fullspace correct           : {fs_correct}/{total}")
    print(f"  LangGraph correct (mirrored): {lg_correct}/{sum(1 for r in results if r.lg_expressible)}")
    print(f"  Fullspace-only expressive   : {fs_only}  (LangGraph cannot express)")
    print()
    print("reading the table:")
    print("  - exec = node function executions (fewer is better)")
    print("  - route = 'where next' decisions: fs=ANN queries, lg=conditional-edge routers")
    print("  - On purely-static mirrored patterns LangGraph's pre-wired edges cost 0 routing")
    print("    decisions; Fullspace pays one ANN query per hop. That overhead is the price of")
    print("    dynamic/soft routing, and is recovered at scale via a sublinear ANN index.")
    print()
    print("  See `python -m fullspace.eval.scaling` for the latency-axis flip: with FAISS,")
    print("  Fullspace routing is ~80-120x faster than O(N) routing at N=5k-20k.")


if __name__ == "__main__":
    main()
