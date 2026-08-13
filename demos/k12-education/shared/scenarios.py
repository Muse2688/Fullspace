# -*- coding: utf-8 -*-
"""测试场景：固定场景（功能对齐测试）+ 随机负载生成器（普适性测试）。"""

import random

from .knowledge_base import QUESTION_BANK, ALL_TOPICS
from .student_sim import simulate_answers


def make_scenario(name, student_name, subject, proficiency, seed=0, extra=None):
    """构造一个场景的初始 state，预生成全题库的模拟作答。"""
    all_q = [q for t in ALL_TOPICS for q in QUESTION_BANK[t]]
    sim = simulate_answers(all_q, proficiency, seed)
    s = {
        "student_id": name,
        "student_name": student_name,
        "subject": subject,
        "proficiency": proficiency,
        "seed": seed,
        "simulated_answers": sim,
        "trajectory": [],
    }
    if extra:
        s.update(extra)
    return s


# 固定场景：覆盖不同路径形态（全对直达 / 错但无回环 / fundamental 回环 / 低水平）
SCENARIOS = [
    make_scenario("s1_advanced", "Alice", "math", 95, seed=1),       # 高水平，多半全对直达
    make_scenario("s2_average", "Bob", "math", 55, seed=2),          # 中等，有错
    make_scenario("s3_struggling", "Carol", "math", 30, seed=3),     # 低水平，fundamental 回环
    make_scenario("s4_english", "Dave", "english", 45, seed=4),      # 英语科目
    make_scenario("s5_beginner", "Eve", "math", 15, seed=5),         # 极低水平
]


def random_load(n=200, seed=42):
    """随机负载生成器：n 个多样化学生请求（随机学科/水平/种子），用于普适性测试。

    原则：测分布而非单点——不同 proficiency 跨度覆盖从全对到全错的各种路径形态。
    """
    rng = random.Random(seed)
    subjects = ["math", "english"]
    names = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Grace", "Heidi"]
    out = []
    for i in range(n):
        prof = rng.randint(10, 95)
        subj = rng.choice(subjects)
        nm = f"{rng.choice(names)}_{i}"
        out.append(make_scenario(f"r{i}", nm, subj, prof, seed=rng.randint(0, 10 ** 6)))
    return out
