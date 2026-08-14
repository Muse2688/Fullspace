# -*- coding: utf-8 -*-
"""基准工具：跑两版（带计数 + 延迟分布），计算单场景指标。"""

import statistics


def _p95(lst):
    if not lst:
        return 0.0
    s = sorted(lst)
    return s[min(len(s) - 1, int(len(s) * 0.95))]


def dist(lst):
    """一个数值列表的分布统计（普适性测试用：测分布而非单点）。"""
    if not lst:
        return {"n": 0, "mean": 0, "median": 0, "p95": 0, "stdev": 0, "min": 0, "max": 0}
    return {
        "n": len(lst),
        "mean": statistics.mean(lst),
        "median": statistics.median(lst),
        "p95": _p95(lst),
        "stdev": statistics.pstdev(lst) if len(lst) > 1 else 0.0,
        "min": min(lst),
        "max": max(lst),
    }


def _median(lst):
    return statistics.median(lst) if lst else 0.0


def run_pair(scenario, repeats=5):
    """对一个场景跑 LangGraph + Fullspace，返回对比指标（功能一致性 + 计数 + 延迟中位/P95）。"""
    from langgraph_demo.run import run as run_lg
    from fullspace_demo.run import run as run_fs
    from fullspace_demo.run_hybrid import run as run_hyb

    sc = dict(scenario)
    # 功能 + 计数（单次）
    lg = run_lg(dict(sc))
    fs = run_fs(dict(sc), count_routes=True)
    hyb = run_hyb(dict(sc), count_routes=True)

    # 延迟：warm 1 次 + repeats 次取中位
    run_lg(dict(sc))  # warm up
    lg_times = [run_lg(dict(sc))["elapsed_ms"] for _ in range(repeats)]
    run_fs(dict(sc))
    fs_times = [run_fs(dict(sc))["elapsed_ms"] for _ in range(repeats)]
    run_hyb(dict(sc))
    hyb_times = [run_hyb(dict(sc))["elapsed_ms"] for _ in range(repeats)]

    same_traj = lg["trajectory"] == fs["trajectory"] == hyb["trajectory"]
    same_report = (lg["state"].get("report") == fs["state"].get("report")
                   == hyb["state"].get("report"))
    return {
        "name": sc.get("student_id"),
        "subject": sc.get("subject"),
        "proficiency": sc.get("proficiency"),
        "trajectory": lg["trajectory"],
        "fs_trajectory": fs["trajectory"],
        "trajectory_match": same_traj,
        "report_match": same_report,
        "success": bool(same_traj and same_report),
        "terminated_by": fs.get("terminated_by"),
        "lg": {
            "steps": lg["steps"], "node_calls": lg["node_calls"],
            "route_calls": lg["route_calls"],
            "elapsed_ms_median": _median(lg_times), "elapsed_ms_p95": _p95(lg_times),
        },
        "fs": {
            "steps": fs["steps"], "node_calls": fs["node_calls"],
            "route_calls": fs["route_calls"],
            "elapsed_ms_median": _median(fs_times), "elapsed_ms_p95": _p95(fs_times),
        },
        "fs_hybrid": {
            "steps": hyb["steps"], "node_calls": hyb["node_calls"],
            "route_calls": hyb["route_calls"], "ann_calls": hyb["ann_calls"],
            "cache_hits": hyb["cache_hits"],
            "elapsed_ms_median": _median(hyb_times), "elapsed_ms_p95": _p95(hyb_times),
        },
    }


def verdict(case):
    """逐轴裁决：correctness / exec / route / latency。返回 dict，correctness 为 'pass'/'fail'，其余 'FS'/'LG'/'tie'。"""
    out = {}
    # success 要求三版轨迹与产出完全一致，只有通过/不通过，无胜者可言
    out["correctness"] = "pass" if case["success"] else "fail"
    out["exec"] = _less_is_better(case["lg"]["node_calls"], case["fs"]["node_calls"])
    out["route"] = _less_is_better(case["lg"]["route_calls"], case["fs"]["route_calls"])
    out["latency"] = _less_is_better(case["lg"]["elapsed_ms_median"], case["fs"]["elapsed_ms_median"])
    return out


def _less_is_better(lg_val, fs_val):
    if lg_val == fs_val:
        return "tie"
    return "LG" if lg_val < fs_val else "FS"
