# -*- coding: utf-8 -*-
"""分支业务规则（纯函数）。两框架共用同一份，保证 grade/answer 后的分支决策完全一致。"""


def after_grade(state):
    """grade 之后：全对→report，有错→analyze。"""
    return "report" if state.get("wrong_count", 0) == 0 else "analyze"


def after_answer(state):
    """answer 之后：需要补讲且未超上限→teach，否则→report。"""
    return "teach" if state.get("needs_reteach") else "report"


# Fullspace 入口 task 文本（与 diagnose 的 capability 描述高度重叠，确保 ANN 命中）
ENTRY_TASK = "diagnose assess student proficiency and identify weak points"
