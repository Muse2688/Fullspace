# -*- coding: utf-8 -*-
"""静态知识库：按 topic 索引的讲义与题库。两框架的 agent 共用同一份，保证业务逻辑一致。"""

# 讲义：topic -> {explanation, key_points, examples}
LESSONS = {
    "fractions": {
        "explanation": "分数表示部分与整体的关系，分母表示总份数，分子表示取的份数。",
        "key_points": ["同分母相加：分母不变，分子相加", "通分后再比较或运算"],
        "examples": ["1/2 + 1/2 = 1", "3/4 > 1/2"],
    },
    "equations": {
        "explanation": "方程是含有未知数的等式，通过等式性质求解未知数。",
        "key_points": ["两边同加/同减/同乘/同除保持等式", "移项变号"],
        "examples": ["x + 3 = 7  =>  x = 4", "2x = 10  =>  x = 5"],
    },
    "geometry": {
        "explanation": "几何研究形状、大小与位置，常见量有周长、面积、角度。",
        "key_points": ["三角形内角和 180°", "长方形面积 = 长 × 宽"],
        "examples": ["长 4 宽 3 的长方形面积 = 12", "直角三角形两锐角和 90°"],
    },
    "vocabulary": {
        "explanation": "词汇是语言的基本单位，通过词根、词缀和语境理解含义。",
        "key_points": ["前缀改变词义", "后缀改变词性"],
        "examples": ["un- 表否定：happy→unhappy", "-ly 表副词：quick→quickly"],
    },
    "grammar": {
        "explanation": "语法规定句子结构与时态，主谓一致是核心。",
        "key_points": ["一般现在时第三人称单数加 s", "进行时用 be + doing"],
        "examples": ["He plays.", "She is reading."],
    },
}

# 题库：topic -> [题目]。每题 {id, topic, prompt, options, answer(正确选项), difficulty(1..5)}
QUESTION_BANK = {
    "fractions": [
        {"id": "f1", "topic": "fractions", "prompt": "1/2 + 1/2 = ?",
         "options": ["1/4", "1", "2", "0"], "answer": "1", "difficulty": 1},
        {"id": "f2", "topic": "fractions", "prompt": "3/4 和 1/2 哪个大？",
         "options": ["3/4", "1/2", "相等", "无法比较"], "answer": "3/4", "difficulty": 2},
        {"id": "f3", "topic": "fractions", "prompt": "2/3 + 1/3 = ?",
         "options": ["1", "3/3", "1/3", "2/6"], "answer": "1", "difficulty": 2},
        {"id": "f4", "topic": "fractions", "prompt": "把 6/8 约分",
         "options": ["3/4", "2/3", "1/2", "6/4"], "answer": "3/4", "difficulty": 4},
    ],
    "equations": [
        {"id": "e1", "topic": "equations", "prompt": "x + 3 = 7，x = ?",
         "options": ["3", "4", "10", "21"], "answer": "4", "difficulty": 1},
        {"id": "e2", "topic": "equations", "prompt": "2x = 10，x = ?",
         "options": ["5", "12", "20", "8"], "answer": "5", "difficulty": 2},
        {"id": "e3", "topic": "equations", "prompt": "x - 5 = 2，x = ?",
         "options": ["7", "3", "-3", "10"], "answer": "7", "difficulty": 2},
        {"id": "e4", "topic": "equations", "prompt": "3x + 1 = 10，x = ?",
         "options": ["3", "4", "11/3", "9"], "answer": "3", "difficulty": 4},
    ],
    "geometry": [
        {"id": "g1", "topic": "geometry", "prompt": "长 4 宽 3 的长方形面积？",
         "options": ["12", "7", "14", "1"], "answer": "12", "difficulty": 1},
        {"id": "g2", "topic": "geometry", "prompt": "三角形内角和？",
         "options": ["90°", "180°", "360°", "270°"], "answer": "180°", "difficulty": 1},
        {"id": "g3", "topic": "geometry", "prompt": "直角三角形两锐角和？",
         "options": ["180°", "90°", "45°", "270°"], "answer": "90°", "difficulty": 3},
        {"id": "g4", "topic": "geometry", "prompt": "半径 2 的圆面积（π取3）？",
         "options": ["12", "4", "6", "24"], "answer": "12", "difficulty": 5},
    ],
    "vocabulary": [
        {"id": "v1", "topic": "vocabulary", "prompt": "unhappy 的含义？",
         "options": ["不开心", "开心", "快乐", "兴奋"], "answer": "不开心", "difficulty": 1},
        {"id": "v2", "topic": "vocabulary", "prompt": "quickly 的词性？",
         "options": ["副词", "名词", "形容词", "动词"], "answer": "副词", "difficulty": 2},
        {"id": "v3", "topic": "vocabulary", "prompt": "'re' 前缀通常表示？",
         "options": ["再次", "否定", "相反", "之后"], "answer": "再次", "difficulty": 3},
        {"id": "v4", "topic": "vocabulary", "prompt": "'bene' 词根的含义？",
         "options": ["好", "坏", "快", "慢"], "answer": "好", "difficulty": 5},
    ],
    "grammar": [
        {"id": "gr1", "topic": "grammar", "prompt": "He ___ (play) basketball.",
         "options": ["plays", "play", "playing", "played"], "answer": "plays", "difficulty": 1},
        {"id": "gr2", "topic": "grammar", "prompt": "She is ___ a book.",
         "options": ["reading", "reads", "read", "to read"], "answer": "reading", "difficulty": 2},
        {"id": "gr3", "topic": "grammar", "prompt": "第三人称单数一般现在时动词？",
         "options": ["加 s", "加 ed", "加 ing", "不变"], "answer": "加 s", "difficulty": 2},
        {"id": "gr4", "topic": "grammar", "prompt": "虚拟语气 If I ___ a bird...",
         "options": ["were", "was", "am", "be"], "answer": "were", "difficulty": 5},
    ],
}

ALL_TOPICS = list(QUESTION_BANK.keys())
