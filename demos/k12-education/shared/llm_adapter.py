# -*- coding: utf-8 -*-
"""LLM 适配层：默认纯函数后端（离线、可复现），可一行切换到真实 LLM。

本 demo 的 agent 默认用纯函数产出确定性结果，保证对比可复现。
若要接真实 LLM：把下面的 LLM_BACKEND 改为 LlmBackend(openai.Client())，
并在 agents.py 里把硬编码文本替换为 LLM_BACKEND.generate(...) 即可，签名不变。
"""


class PureFnBackend:
    name = "pure"

    def generate(self, prompt: str, **kw) -> str:
        return ""  # 纯函数 agent 不需要调用


class LlmBackend:
    name = "llm"

    def __init__(self, client, model="gpt-4o-mini"):
        self.client = client
        self.model = model

    def generate(self, prompt: str, **kw) -> str:
        return self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        ).choices[0].message.content


# 全局开关。默认纯函数。切换：LLM_BACKEND = LlmBackend(openai.Client())
LLM_BACKEND = PureFnBackend()
