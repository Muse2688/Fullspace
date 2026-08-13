# -*- coding: utf-8 -*-
"""规模 scaling 基准：agent 数 1→N 的「纯路由」延迟曲线。

诚实口径（借鉴 fullspace/eval/scaling.py）：
- LangGraph 条件路由是 O(1) dict 查表，与 agent 数无关（静态图预连边）。
- Fullspace 默认用 numpy 暴力 ANN，是 O(N) 点积，随 agent 数线性增长；
  接入 FAISS 后变 O(log N)，会在大规模翻转（本 demo 用 numpy 呈现线性段）。
"""

import time
import statistics

from fullspace import Capability, HashEmbedder, Manifold


def _median(lst):
    return statistics.median(lst) if lst else 0.0


def fs_route_latency(N, repeats=80):
    """Fullspace：注册 N 个能力，测一次 nearest（ANN 路由）延迟。"""
    m = Manifold(HashEmbedder(dim=256))
    m.register_many([
        Capability(f"c{i}", f"capability number {i} handles task type {i}")
        for i in range(max(N, 1))
    ])
    q = "capability number 0 handles task type 0"
    m.nearest(q)  # warm up
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        m.nearest(q)
        times.append((time.perf_counter() - t0) * 1000)
    return _median(times)


def lg_route_latency(N, repeats=80):
    """LangGraph：条件路由 = 一次函数调用 + dict 查表，O(1)，与 N 无关。"""
    mapping = {f"c{i}": i for i in range(max(N, 1))}

    def router(state):
        return "c0"

    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        k = router({})
        _ = mapping[k]
        times.append((time.perf_counter() - t0) * 1000)
    return _median(times)


def scaling_curve(sizes=(8, 16, 32, 64, 128, 256, 512)):
    return [{"N": N, "fs_ms": fs_route_latency(N), "lg_ms": lg_route_latency(N)} for N in sizes]
