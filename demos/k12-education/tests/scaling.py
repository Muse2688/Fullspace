# -*- coding: utf-8 -*-
"""规模 scaling 基准：agent 数 1→N 的「纯路由」延迟曲线。

诚实口径（借鉴 fullspace/eval/scaling.py）：
- LangGraph 条件路由是 O(1) 函数调用 + dict 查表，与 agent 数无关（静态图预连边）。
  这里测的是真实图里真实使用的 shared/routing.py 路由函数 + N 路分支映射，
  并用批内计时（每次测 1000 连 calls）避开 perf_counter 分辨率下限。
- Fullspace 默认用 numpy 暴力 ANN，是 O(N) 点积，随 agent 数线性增长；
  接入增量 ANN 索引（fullspace[ann-usearch]）后变次线性，会在大规模翻转。
"""

import time
import statistics

from fullspace import Capability, HashEmbedder, Manifold

from shared.routing import after_grade


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


def lg_route_latency(N, repeats=80, batch=1000):
    """LangGraph：真实条件路由（shared/routing.after_grade + N 路映射），O(1)。

    单次调用低于 perf_counter 分辨率，故每次测一批 batch 个连续调用取均值，
    数字才有信息量（而不是恒等于计时器下限）。
    """
    # N 路分支映射表：dict 大小随 N 增长（含真实路由目标 report/analyze/teach）
    others = [f"c{i}" for i in range(max(N - 3, 0))]
    mapping = {k: k for k in others + ["report", "analyze", "teach"]}
    state = {"score": 100, "wrong_count": 0, "needs_reteach": False}
    after_grade(state)  # warm up
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        for _ in range(batch):
            k = after_grade(state)
            _ = mapping[k]
        times.append((time.perf_counter() - t0) * 1000 / batch)
    return _median(times)


def scaling_curve(sizes=(8, 16, 32, 64, 128, 256, 512)):
    return [{"N": N, "fs_ms": fs_route_latency(N), "lg_ms": lg_route_latency(N)} for N in sizes]
