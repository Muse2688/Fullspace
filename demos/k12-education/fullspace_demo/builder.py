# -*- coding: utf-8 -*-
"""Fullspace 编排：Manifold + 8 Capability + Engine。

编排策略（诚实混合）：
- 线性段用 intent（软路由，每跳 1 次 ANN）——展示 FS 独有的 capability-space 路由；
- 两处分支用 goto（硬路由，精确、数据驱动）——分支结果来自 shared/routing.py，与 LG 完全一致。
"""

from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import Engine, NodeResult, Router

from shared import agents as A
from shared import routing as R
from .capabilities import CAPABILITIES, SINK, LINEAR_INTENT


def _linear_handler(fn, agent_id):
    """线性段：跑纯函数 → 用 intent 软路由到下一个 agent。"""
    def h(ctx):
        return NodeResult(updates=fn(ctx.state), intent=LINEAR_INTENT[agent_id])
    return h


def _branch_handler(fn, route_fn):
    """分支段：跑纯函数 → 用 shared route_fn 决定 goto（硬路由）。"""
    def h(ctx):
        updates = fn(ctx.state)
        merged = {**ctx.state, **updates}
        return NodeResult(updates=updates, goto=route_fn(merged))
    return h


class CountingRouter(Router):
    """计数 ANN 路由调用次数（借鉴 fullspace/eval/cases.py 的 _CountingRouter）。"""
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.count = 0

    def route(self, intent):
        self.count += 1
        return super().route(intent)


def build(router=None, use_counting=False):
    """构建 Engine。use_counting=True 时挂载 CountingRouter 用于测试计数。"""
    m = Manifold(HashEmbedder(dim=256))
    m.register_many([
        Capability(cid, desc, metadata=({"sink": True} if cid == SINK else {}))
        for cid, desc in CAPABILITIES
    ])
    if router is None and use_counting:
        router = CountingRouter(m)
    eng = Engine(m, router=router)

    eng.bind("diagnose", _linear_handler(A.diagnose, "diagnose"))
    eng.bind("plan",     _linear_handler(A.plan,     "plan"))
    eng.bind("teach",    _linear_handler(A.teach,    "teach"))
    eng.bind("quiz",     _linear_handler(A.quiz,     "quiz"))
    eng.bind("grade",    _branch_handler(A.grade,    R.after_grade))
    eng.bind("analyze",  _linear_handler(A.analyze,  "analyze"))
    eng.bind("answer",   _branch_handler(A.answer,   R.after_answer))
    eng.bind("report",   lambda ctx: NodeResult(updates=A.report(ctx.state)))
    return eng, m
