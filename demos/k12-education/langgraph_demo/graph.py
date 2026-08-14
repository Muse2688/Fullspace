# -*- coding: utf-8 -*-
"""LangGraph 编排：StateGraph 把 8 个共享 agent 连成图，条件边实现 grade/answer 后的分支。

关键：分支决策 100% 来自 shared/routing.py，与 Fullspace 版完全相同 → 功能一致性有保证。
注意：用 add_edge(START, "diagnose")；set_entry_point 在新版已废弃。
"""

from langgraph.graph import StateGraph, START, END

from shared.state import K12State
from shared import agents as A
from shared import routing as R


def build():
    """构建编译后的 app，并返回两个计数列表（节点执行 / 条件路由调用）。"""
    node_calls, route_calls = [], []

    def node(fn):
        def h(state):
            node_calls.append(1)
            return fn(state)
        h.__name__ = fn.__name__
        return h

    def counted_router(rfn):
        def r(state):
            route_calls.append(1)
            return rfn(state)
        return r

    g = StateGraph(K12State)
    for name in ["diagnose", "plan", "teach", "quiz", "grade", "analyze", "answer", "report"]:
        g.add_node(name, node(A.AGENTS[name]))

    # 入口与线性段
    g.add_edge(START, "diagnose")
    g.add_edge("diagnose", "plan")
    g.add_edge("plan", "teach")
    g.add_edge("teach", "quiz")
    g.add_edge("quiz", "grade")
    g.add_edge("analyze", "answer")

    # 两处数据驱动分支（调用 shared/routing.py 的纯函数）
    g.add_conditional_edges("grade",  counted_router(R.after_grade),
                            {"report": "report", "analyze": "analyze"})
    g.add_conditional_edges("answer", counted_router(R.after_answer),
                            {"teach": "teach", "report": "report"})

    g.add_edge("report", END)
    app = g.compile()
    return app, node_calls, route_calls
