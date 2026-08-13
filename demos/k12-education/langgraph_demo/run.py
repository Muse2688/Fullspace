# -*- coding: utf-8 -*-
"""运行 LangGraph 版：对一个场景跑完整闭环，返回最终 state + 轨迹 + 计数 + 耗时。"""

import time

from .graph import build


def run(scenario):
    app, node_calls, route_calls = build()
    t0 = time.perf_counter()
    final = app.invoke(dict(scenario), config={"recursion_limit": 50})
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return {
        "framework": "langgraph",
        "state": final,
        "trajectory": final.get("trajectory", []),
        "node_calls": len(node_calls),
        "route_calls": len(route_calls),
        "steps": len(node_calls),
        "elapsed_ms": elapsed_ms,
    }
