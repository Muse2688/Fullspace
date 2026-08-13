# -*- coding: utf-8 -*-
"""8 个 Capability 的描述文案 + intent 字符串常量。

设计要点：HashEmbedder 靠字面 token 重叠打分，所以线性段 handler 发出的 intent
必须与「下一个 capability 的描述」高度重叠，才能稳定命中 top-1。
"""

# (id, description)
CAPABILITIES = [
    ("diagnose", "diagnose assess student proficiency and identify weak points"),
    ("plan",     "plan build a personalized study plan"),
    ("teach",    "teach explain the knowledge point with examples"),
    ("quiz",     "quiz generate practice questions"),
    ("grade",    "grade mark the answers and score"),
    ("analyze",  "analyze diagnose mistakes and misconceptions"),
    ("answer",   "answer resolve student questions and doubts"),
    ("report",   "report summarize learning outcomes and progress"),
]

SINK = "report"

# 线性段：每个 agent 执行后发出的 intent = 下一个 agent 的 description（保证 ANN 命中）
LINEAR_INTENT = {
    "diagnose": "plan build a personalized study plan",
    "plan":     "teach explain the knowledge point with examples",
    "teach":    "quiz generate practice questions",
    "quiz":     "grade mark the answers and score",
    "analyze":  "answer resolve student questions and doubts",
    # grade / answer 是分支（用 goto），report 是 sink（自然终止）
}
