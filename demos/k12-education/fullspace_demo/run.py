# -*- coding: utf-8 -*-
"""运行 Fullspace 版：对一个场景跑完整闭环，返回最终 state + 轨迹 + 计数 + 耗时。

路由计数：FS 的 routing_calls = 1（入口 ANN 定位）+ router.route 调用次数。
"""

import time

from shared.routing import ENTRY_TASK
from .builder import build


def run(scenario, count_routes=False):
    eng, m = build(use_counting=count_routes)
    t0 = time.perf_counter()
    res = eng.run(ENTRY_TASK, state=dict(scenario), max_steps=30)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    _r = getattr(eng.router, "count", None)
    routing_calls = (1 + _r) if _r is not None else None
    return {
        "framework": "fullspace",
        "state": res.state,
        "trajectory": res.trajectory,
        "node_calls": res.steps,
        "route_calls": routing_calls,
        "steps": res.steps,
        "elapsed_ms": elapsed_ms,
        "terminated_by": res.terminated_by,
    }
