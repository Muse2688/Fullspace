# -*- coding: utf-8 -*-
"""共享状态 schema。LangGraph 用作 StateGraph 的 schema；Fullspace 用普通 dict（TypedDict 仅作类型提示）。"""

from typing import TypedDict

# 最多补讲次数（answer→teach 回环的有界上限，防止无限循环）
MAX_RETEACH = 1


class K12State(TypedDict, total=False):
    # —— 输入（由 scenario 提供）——
    student_id: str
    student_name: str
    grade_level: int            # 年级 1..12
    subject: str                # "math" / "english" / ...
    proficiency: int            # 0..100，先验水平
    simulated_answers: dict     # question_id -> 学生选项（scenario 预生成）
    seed: int                   # 可复现种子

    # —— diagnose 产出 ——
    diagnosis: dict             # {topic: mastery_0_100}
    weak_points: list           # 弱点 topic 列表，按严重度升序
    level: str                  # beginner | intermediate | advanced

    # —— plan 产出 ——
    learning_plan: list         # 有序 topic 队列
    current_topic: str
    plan_idx: int

    # —— teach 产出 ——
    lesson: dict
    teach_count: int            # teach 运行次数（回环计数）
    remediation_topic: str      # 补讲子主题（由 analyze 写入）

    # —— quiz 产出 ——
    quiz: list                  # [{id, topic, prompt, options, answer, difficulty}]

    # —— grade 产出 ——
    answers: dict
    grading: dict               # {qid: {correct, student, key}}
    score: float                # 0..100
    correct_count: int
    wrong_count: int

    # —— analyze 产出 ——
    errors: list                # [{question_id, misconception, severity, remediation_topic}]

    # —— answer 产出 ——
    qa_log: list
    needs_reteach: bool

    # —— report 产出（终点）——
    report: dict

    # —— 元数据 ——
    trajectory: list            # 已访问 agent 序列（两框架都维护，便于比对）
