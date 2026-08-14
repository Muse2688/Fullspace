# -*- coding: utf-8 -*-
"""8 个教学 agent 的纯函数实现。签名统一 (state: dict) -> dict（partial updates）。
不含任何路由知识——路由由两个框架各自实现。两框架共用这一份，保证只对比「编排」。"""

import hashlib

from .knowledge_base import LESSONS, QUESTION_BANK, ALL_TOPICS
from .state import MAX_RETEACH


def _stable_hash(text):
    """确定性哈希（跨进程可复现，避免 Python 内建 hash 的 PYTHONHASHSEED 随机化）。"""
    return int.from_bytes(hashlib.md5(text.encode("utf-8")).digest()[:4], "little")


def _traj(state, name):
    return state.get("trajectory", []) + [name]


# 1. 学情诊断
def diagnose(state):
    """起点：据 proficiency 算各 topic 掌握度与弱点。"""
    prof = state.get("proficiency", 50)
    diagnosis = {t: max(0, min(100, prof + (_stable_hash(t) % 21) - 10)) for t in ALL_TOPICS}
    weak = sorted([t for t in ALL_TOPICS if diagnosis[t] < 60], key=lambda t: diagnosis[t])
    level = "beginner" if prof < 40 else "intermediate" if prof < 75 else "advanced"
    return {"diagnosis": diagnosis, "weak_points": weak, "level": level,
            "trajectory": _traj(state, "diagnose")}


# 2. 学习规划
def plan(state):
    """据弱点排学习计划，选第一个 topic。"""
    weak = state.get("weak_points") or list(ALL_TOPICS)
    learning_plan = weak[:3]
    return {"learning_plan": learning_plan, "plan_idx": 0,
            "current_topic": learning_plan[0],
            "trajectory": _traj(state, "plan")}


# 3. 知识点讲解
def teach(state):
    """讲解 current_topic（或 remediation_topic）。"""
    topic = state.get("remediation_topic") or state.get("current_topic")
    lesson = LESSONS.get(topic, {"topic": topic, "explanation": "(暂无讲义)",
                                 "key_points": [], "examples": []})
    return {"lesson": lesson, "teach_count": state.get("teach_count", 0) + 1,
            "current_topic": topic,
            "trajectory": _traj(state, "teach")}


# 4. 练习出题
def quiz(state):
    """为 current_topic 出 3 题。"""
    topic = state.get("current_topic")
    questions = QUESTION_BANK.get(topic, [])[:3]
    return {"quiz": questions, "trajectory": _traj(state, "quiz")}


# 5. 作业批改
def grade(state):
    """比对 simulated_answers 与 quiz 答案。"""
    q = state.get("quiz", [])
    sim = state.get("simulated_answers", {})
    grading, correct, wrong = {}, 0, 0
    for item in q:
        sid = item["id"]
        ok = (sim.get(sid) == item["answer"])
        grading[sid] = {"correct": ok, "student": sim.get(sid), "key": item["answer"]}
        correct += ok
        wrong += (not ok)
    score = (correct / len(q) * 100) if q else 0.0
    return {"answers": sim, "grading": grading, "score": score,
            "correct_count": correct, "wrong_count": wrong,
            "trajectory": _traj(state, "grade")}


# 6. 错题分析
def analyze(state):
    """分类每道错题的错因 + 补讲主题。difficulty<=2 视为 fundamental（基础不牢）。"""
    grading = state.get("grading", {})
    quiz = {it["id"]: it for it in state.get("quiz", [])}
    errors = []
    for sid, g in grading.items():
        if not g["correct"]:
            diff = quiz.get(sid, {}).get("difficulty", 3)
            sev = "fundamental" if diff <= 2 else "careless"
            errors.append({"question_id": sid, "misconception": sev, "severity": sev,
                           "remediation_topic": quiz.get(sid, {}).get("topic", state.get("current_topic"))})
    rem = errors[0]["remediation_topic"] if errors else state.get("current_topic")
    return {"errors": errors, "remediation_topic": rem,
            "trajectory": _traj(state, "analyze")}


# 7. 答疑解惑
def answer(state):
    """为每条错题生成 Q&A；存在 fundamental 错因且未超补讲上限则置 needs_reteach。"""
    errors = state.get("errors", [])
    qa = [{"q": f"为什么 {e['question_id']} 错了？",
           "a": f"属于 {e['misconception']} 类错误，建议复习 {e['remediation_topic']}。"}
          for e in errors]
    has_fund = any(e["severity"] == "fundamental" for e in errors)
    teach_count = state.get("teach_count", 0)
    needs_reteach = has_fund and teach_count < (1 + MAX_RETEACH)
    return {"qa_log": qa, "needs_reteach": needs_reteach,
            "trajectory": _traj(state, "answer")}


# 8. 学情报告（终点）
def report(state):
    """汇总为最终学情报告。"""
    r = {
        "student": state.get("student_name"),
        "subject": state.get("subject"),
        "level": state.get("level"),
        "score": state.get("score", 0.0),
        "weak_points": state.get("weak_points", []),
        "error_count": len(state.get("errors", [])),
        "qa_count": len(state.get("qa_log", [])),
        "teach_count": state.get("teach_count", 0),
        "recommendation": "巩固 " + (state.get("remediation_topic") or "基础"),
    }
    return {"report": r, "trajectory": _traj(state, "report")}


# agent 名 -> 函数 的映射（两框架注册时用）
AGENTS = {
    "diagnose": diagnose, "plan": plan, "teach": teach, "quiz": quiz,
    "grade": grade, "analyze": analyze, "answer": answer, "report": report,
}
