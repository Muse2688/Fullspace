# -*- coding: utf-8 -*-
"""运行 Fullspace 混合路由版：返回最终 state + 轨迹 + 总决策数 + 真正 ANN 数 + 缓存命中。"""

import time

from shared.routing import ENTRY_TASK
from .builder_hybrid import build


def run(scenario, count_routes=False):
    eng, m = build(use_counting=count_routes)
    t0 = time.perf_counter()
    res = eng.run(ENTRY_TASK, state=dict(scenario), max_steps=30)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    if count_routes and hasattr(eng.router, "count"):
        routing_calls = 1 + eng.router.count        # 入口 ANN + 总决策数
        ann_calls = 1 + eng.router.ann_count        # 入口 ANN + 真正 ANN 数（缓存后更少）
        cache_hits = eng.router.cache_hits
    else:
        routing_calls = ann_calls = cache_hits = None
    return {
        "framework": "fullspace-hybrid",
        "state": res.state,
        "trajectory": res.trajectory,
        "node_calls": res.steps,
        "route_calls": routing_calls,
        "ann_calls": ann_calls,
        "cache_hits": cache_hits,
        "steps": res.steps,
        "elapsed_ms": elapsed_ms,
        "terminated_by": res.terminated_by,
    }
