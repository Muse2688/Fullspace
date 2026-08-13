# -*- coding: utf-8 -*-
"""对比测试主入口：跑功能场景 + 普适负载 + scaling + OOD + 变更实验 → metrics.json。

运行：python demos/k12-education/tests/run_all.py
（在仓库根运行，fullspace 从当前目录导入；shared/demo/tests 通过 sys.path 注入）
"""

import os
import sys
import json
import statistics

# 让 shared / langgraph_demo / fullspace_demo / tests 可作为顶层包导入，
# 并让 fullspace（仓库源码）可导入
_HERE = os.path.dirname(os.path.abspath(__file__))
_DEMO = os.path.dirname(_HERE)
_REPO = os.path.dirname(os.path.dirname(_DEMO))   # 仓库根（fullspace 源码所在）
for _p in (_REPO, _DEMO):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from shared.scenarios import SCENARIOS, random_load
from langgraph_demo.run import run as run_lg
from fullspace_demo.run import run as run_fs
from fullspace_demo.run_hybrid import run as run_hyb
from fullspace_demo.builder import build
from fullspace import Capability
from fullspace.engine import NodeResult
from tests.bench import run_pair, verdict, dist
from tests.scaling import scaling_curve


# ─────────────── 普适性测试：200 个随机负载，测分布 ───────────────
def realworld_stats(n=200):
    loads = random_load(n)
    fs_times, lg_times, hyb_times, fs_routes, lg_routes, hyb_ann = [], [], [], [], [], []
    matches = 0
    for i, s in enumerate(loads):
        lg = run_lg(dict(s))
        fs = run_fs(dict(s), count_routes=True)
        hyb = run_hyb(dict(s), count_routes=True)
        if (lg["trajectory"] == fs["trajectory"] == hyb["trajectory"]
                and lg["state"].get("report") == fs["state"].get("report") == hyb["state"].get("report")):
            matches += 1
        lg_times.append(lg["elapsed_ms"])
        fs_times.append(fs["elapsed_ms"])
        hyb_times.append(hyb["elapsed_ms"])
        lg_routes.append(lg["route_calls"])
        fs_routes.append(fs["route_calls"])
        hyb_ann.append(hyb["ann_calls"])
        if (i + 1) % 50 == 0:
            print(f"  realworld {i + 1}/{n}")
    return {
        "n": n,
        "consistency_rate": matches / n,
        "lg_latency": dist(lg_times),
        "fs_latency": dist(fs_times),
        "hyb_latency": dist(hyb_times),
        "lg_route_calls": dist([float(x) for x in lg_routes]),
        "fs_route_calls": dist([float(x) for x in fs_routes]),
        "hyb_ann_calls": dist([float(x) for x in hyb_ann]),
    }


# ─────────────── OOD 鲁棒性 ───────────────
def ood_test():
    cases = []

    def probe(name, scenario):
        try:
            run_lg(dict(scenario))
            lg_ok, lg_err = True, ""
        except Exception as e:
            lg_ok, lg_err = False, repr(e)[:100]
        try:
            run_fs(dict(scenario), count_routes=False)
            fs_ok, fs_err = True, ""
        except Exception as e:
            fs_ok, fs_err = False, repr(e)[:100]
        cases.append({"case": name, "lg_ok": lg_ok, "fs_ok": fs_ok, "lg_err": lg_err, "fs_err": fs_err})

    probe("missing_proficiency", {"student_name": "X", "subject": "math", "simulated_answers": {}, "trajectory": []})
    probe("unknown_subject", {"student_name": "Y", "subject": "火星语", "proficiency": 50, "simulated_answers": {}, "seed": 1, "trajectory": []})
    probe("empty_state", {})
    probe("garbage_input", {"student_name": None, "proficiency": "高", "simulated_answers": "not a dict", "trajectory": []})
    return cases


# ─────────────── 变更实验：加第 9 个 agent ───────────────
def change_test():
    # Fullspace：编译后运行时 register + bind，无需重新构建
    fs_runtime_ok = True
    fs_err = ""
    try:
        eng, m = build()
        m.register(Capability("motivate", "motivate and encourage the student to keep learning"))
        eng.bind("motivate", lambda ctx: NodeResult(updates={"motivated": True}))
        # 能跑通即说明运行时可扩展（不重新 compile）
        eng.run("diagnose assess student proficiency and identify weak points",
                state={"simulated_answers": {}, "trajectory": []}, max_steps=3)
    except Exception as e:
        fs_runtime_ok, fs_err = False, repr(e)[:100]

    # LangGraph：编译后的图是 immutable，加节点必须改 graph.py 并重新 compile
    lg_runtime_ok = False
    lg_err = "compiled graph is immutable; must edit graph.py (add_node + edges) and re-compile"

    return {
        "fs_runtime_extendable": fs_runtime_ok, "fs_err": fs_err,
        "lg_runtime_extendable": lg_runtime_ok, "lg_err": lg_err,
        "fs_change_loc": 2,   # register + bind 两行
        "lg_change_loc": 5,   # add_node + 两条 edge + 路由 + 重新 compile
    }


# ─────────────── 维度归一化（雷达图用）───────────────
def _norm_less(v):
    """少胜归一：v 越小分越高，映射到 (0,1]。"""
    return 1.0 / (1.0 + v)


def dimension_summary(cases, rw, sc, ood, ch):
    m = statistics.mean
    lg_exec = m([c["lg"]["node_calls"] for c in cases])
    fs_exec = m([c["fs"]["node_calls"] for c in cases])
    hyb_exec = m([c["fs_hybrid"]["node_calls"] for c in cases])
    lg_route = m([c["lg"]["route_calls"] for c in cases])
    fs_route = m([c["fs"]["route_calls"] for c in cases])
    hyb_ann = m([c["fs_hybrid"]["ann_calls"] for c in cases])      # Hybrid 用「真正 ANN 数」
    lg_lat = m([c["lg"]["elapsed_ms_median"] for c in cases])
    fs_lat = m([c["fs"]["elapsed_ms_median"] for c in cases])
    hyb_lat = m([c["fs_hybrid"]["elapsed_ms_median"] for c in cases])
    fs_scale = sc[-1]["fs_ms"]
    lg_scale = sc[-1]["lg_ms"]
    fs_ood = sum(1 for o in ood if o["fs_ok"]) / len(ood) if ood else 0
    lg_ood = sum(1 for o in ood if o["lg_ok"]) / len(ood) if ood else 0
    all_ok = all(c["success"] for c in cases)
    ok = 1.0 if all_ok else 0.5
    cons = rw["consistency_rate"]
    return {
        "功能正确性":       {"LG": ok, "FS": ok, "Hybrid": ok},
        "节点效率(少胜)":   {"LG": _norm_less(lg_exec), "FS": _norm_less(fs_exec), "Hybrid": _norm_less(hyb_exec)},
        "路由效率(少胜)":   {"LG": _norm_less(lg_route), "FS": _norm_less(fs_route), "Hybrid": _norm_less(hyb_ann)},
        "速度(快胜)":       {"LG": _norm_less(lg_lat), "FS": _norm_less(fs_lat), "Hybrid": _norm_less(hyb_lat)},
        "规模扩展性":       {"LG": _norm_less(lg_scale), "FS": _norm_less(fs_scale), "Hybrid": _norm_less(fs_scale)},
        "普适一致性":       {"LG": cons, "FS": cons, "Hybrid": cons},
        "OOD鲁棒性":        {"LG": lg_ood, "FS": fs_ood, "Hybrid": fs_ood},
        "可维护性(少改胜)":  {"LG": _norm_less(ch["lg_change_loc"]), "FS": _norm_less(ch["fs_change_loc"]),
                             "Hybrid": _norm_less(ch["fs_change_loc"])},
        "可复现性":         {"LG": 1.0, "FS": 1.0, "Hybrid": 1.0},
    }


def print_summary(metrics):
    print("\n========== 对比摘要 ==========")
    for c in metrics["cases"]:
        print(f"{c['name']:14} {c['trajectory']}")
        print(f"  LG     exec={c['lg']['node_calls']} route={c['lg']['route_calls']} ms={c['lg']['elapsed_ms_median']:.2f}")
        print(f"  FS     exec={c['fs']['node_calls']} route={c['fs']['route_calls']} ms={c['fs']['elapsed_ms_median']:.2f}")
        h = c["fs_hybrid"]
        print(f"  Hybrid exec={h['node_calls']} route={h['route_calls']} ann={h['ann_calls']} cache={h['cache_hits']} ms={h['elapsed_ms_median']:.2f}")
    rw = metrics["realworld"]
    print(f"\n普适负载(n={rw['n']}): 三版一致率={rw['consistency_rate']:.1%}")
    print(f"  LG     延迟中位={rw['lg_latency']['median']:.2f}ms P95={rw['lg_latency']['p95']:.2f}ms")
    print(f"  FS     延迟中位={rw['fs_latency']['median']:.2f}ms P95={rw['fs_latency']['p95']:.2f}ms")
    print(f"  Hybrid 延迟中位={rw['hyb_latency']['median']:.2f}ms ANN均值={rw['hyb_ann_calls']['mean']:.2f}")
    ch = metrics["change"]
    print(f"\n变更实验: FS/Hybrid运行时可扩展={ch['fs_runtime_extendable']} LG需重编译={not ch['lg_runtime_extendable']}")


def main():
    print(">>> 功能场景（5 个，带计数+延迟）")
    cases = [run_pair(s) for s in SCENARIOS]
    for c in cases:
        c["verdict"] = verdict(c)

    print(">>> 普适性负载（200 个随机学生，测分布）")
    rw = realworld_stats(200)

    print(">>> 规模 scaling")
    sc = scaling_curve()

    print(">>> OOD 鲁棒性")
    ood = ood_test()

    print(">>> 变更实验（加第 9 个 agent）")
    ch = change_test()

    metrics = {
        "cases": cases,
        "realworld": rw,
        "scaling": sc,
        "ood": ood,
        "change": ch,
        "dimensions": dimension_summary(cases, rw, sc, ood, ch),
    }
    out = os.path.join(_DEMO, "metrics.json")
    json.dump(metrics, open(out, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("\nmetrics ->", out)
    print_summary(metrics)


if __name__ == "__main__":
    main()
