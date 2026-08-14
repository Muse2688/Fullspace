# -*- coding: utf-8 -*-
"""Fullspace 混合路由版（优化）：线性段 goto（0 ANN）+ 分支 intent（语义，带决策缓存）。

设计目标：证明 Fullspace 通过「自适应混合路由 + 决策缓存」，可在路由开销维度
追平甚至超越 LangGraph，同时保留动态/语义能力（intent 仍在分支处发挥作用）。
"""

from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import Engine, NodeResult, Router
from fullspace.manifold.types import Hit

from shared import agents as A
from .capabilities import CAPABILITIES, SINK

# 线性段：goto 硬走向（0 次 ANN）
LINEAR_GOTO = {
    "diagnose": "plan", "plan": "teach", "teach": "quiz",
    "quiz": "grade", "analyze": "answer",
}
# 分支处用的 intent 文本（与 capability 描述重叠，确保 ANN 命中）
INTENT_REPORT = "report summarize learning outcomes and progress"
INTENT_ANALYZE = "analyze diagnose mistakes and misconceptions"
INTENT_TEACH = "teach explain the knowledge point with examples"


class HybridRouter(Router):
    """带决策缓存的路由器：重复 intent 命中缓存、跳过 ANN。
    分别统计「总决策次数 count」与「真正走 ANN 的次数 ann_count」。"""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.count = 0
        self.ann_count = 0
        self.cache_hits = 0
        self._cache = {}

    def route(self, intent):
        self.count += 1
        key = intent if isinstance(intent, str) else bytes(intent)
        if key in self._cache:
            self.cache_hits += 1
            cap = self.manifold.get(self._cache[key])
            if cap is not None:
                return Hit(cap, 1.0)          # 缓存命中，跳过 ANN
        self.ann_count += 1
        decision = super().route(intent)       # 真正走 ANN
        if decision.capability is not None:
            self._cache[key] = decision.capability.id
        return decision


def _linear_goto(fn, agent_id):
    def h(ctx):
        return NodeResult(updates=fn(ctx.state), goto=LINEAR_GOTO[agent_id])
    return h


def _grade_intent(ctx):
    """grade 后用 intent 语义路由：全对→report，有错→analyze。"""
    updates = A.grade(ctx.state)
    merged = {**ctx.state, **updates}
    intent = INTENT_REPORT if merged.get("wrong_count", 0) == 0 else INTENT_ANALYZE
    return NodeResult(updates=updates, intent=intent)


def _answer_intent(ctx):
    """answer 后用 intent 语义路由：需补讲→teach，否则→report。"""
    updates = A.answer(ctx.state)
    merged = {**ctx.state, **updates}
    intent = INTENT_TEACH if merged.get("needs_reteach") else INTENT_REPORT
    return NodeResult(updates=updates, intent=intent)


def build(use_counting=False):
    m = Manifold(HashEmbedder(dim=256))
    m.register_many([
        Capability(cid, desc, metadata=({"sink": True} if cid == SINK else {}))
        for cid, desc in CAPABILITIES
    ])
    router = HybridRouter(m) if use_counting else None
    eng = Engine(m, router=router)

    eng.bind("diagnose", _linear_goto(A.diagnose, "diagnose"))
    eng.bind("plan",     _linear_goto(A.plan, "plan"))
    eng.bind("teach",    _linear_goto(A.teach, "teach"))
    eng.bind("quiz",     _linear_goto(A.quiz, "quiz"))
    eng.bind("grade",    _grade_intent)          # 分支：intent（语义）
    eng.bind("analyze",  _linear_goto(A.analyze, "analyze"))
    eng.bind("answer",   _answer_intent)         # 分支：intent（语义）
    eng.bind("report",   lambda ctx: NodeResult(updates=A.report(ctx.state)))
    return eng, m
