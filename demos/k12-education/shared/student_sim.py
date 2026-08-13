# -*- coding: utf-8 -*-
"""确定性学生答题模拟器：proficiency × difficulty → 对错。在 scenario 构建时预生成 simulated_answers，
让 agent 保持纯函数、可复现。"""

import random


def _wrong_option(question: dict, rng: random.Random) -> str:
    """从错误选项中确定性挑一个。"""
    wrong = [o for o in question["options"] if o != question["answer"]]
    return rng.choice(wrong) if wrong else question["answer"]


def simulate_answers(quiz: list, proficiency: int, seed: int) -> dict:
    """根据熟练度与题目难度，确定性生成学生的作答。

    规则：difficulty <= proficiency/20 则答对，否则答错；再加一点可复现的噪声。
    """
    rng = random.Random(seed)
    threshold = proficiency / 20.0          # 0..5 的难度门槛
    out = {}
    for q in quiz:
        correct = q["difficulty"] <= threshold
        # 10% 概率在“恰好够得着”的题上翻转（仍由 seed 决定，可复现）
        if rng.random() < 0.10 and q["difficulty"] <= threshold + 1:
            correct = not correct
        out[q["id"]] = q["answer"] if correct else _wrong_option(q, rng)
    return out
