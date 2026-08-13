# K12 教育 8-Agent 对比 Demo（LangGraph vs Fullspace vs Fullspace-Hybrid）

用同一个 K12 教育业务、同一套 8 个教学 agent 的业务逻辑，分别用**三种编排方式**实现，跑一套反 cherry-picking 的普适性测试，产出多维可视化 HTML 报告。

## 三版实现（同一个业务，只换编排）

| 版本 | 编排方式 | 路由开销 |
|---|---|---|
| **LangGraph** | StateGraph 静态条件边 | 条件边，O(1) 查表 |
| **Fullspace** | 全程 `intent` 软路由 | 每跳 1 次 ANN |
| **Fullspace-Hybrid** | 线性段 `goto` + 分支 `intent` + 决策缓存 | goto 免费 + intent 的 ANN 可缓存命中 |

> Hybrid 版用于验证「自适应混合路由」能否让 Fullspace 在路由开销维度追平 LangGraph。

## 8 个教学 agent（业务骨架，三版共用）

学情诊断 → 学习规划 → 知识点讲解 → 练习出题 → 作业批改 →（分支）→ 错题分析 → 答疑解惑 → 学情报告。

- grade 后**全对** → 直接 report
- grade 后**错题多** → analyze → answer →（需要补讲则回 teach）→ report

## 设计原则

- **业务共享，编排分离**：`shared/` 是 8 个 agent 的纯函数 + 分支规则，三版共用同一份，只对比「编排」差异。
- **纯函数模拟 + 预留 LLM**：离线、可复现、零成本；`shared/llm_adapter.py` 一行切换到真实模型。
- **测分布而非单点，测混合而非挑拣**：200 个随机负载 + 真实比例混合 + P95/方差。

## 目录结构

```
demos/k12-education/
├─ shared/              # 8 agent 纯函数 + 场景 + 分支规则 + LLM 适配（三版共用）
├─ langgraph_demo/      # StateGraph + 条件边
├─ fullspace_demo/
│  ├─ builder.py        # Fullspace 纯 intent 版
│  ├─ run.py
│  ├─ builder_hybrid.py # Fullspace 混合路由版（goto + intent + 缓存）★
│  └─ run_hybrid.py
├─ tests/               # bench / scaling / run_all（三版对比）
├─ report/              # plotly 三维 HTML 报告
├─ metrics.json         # 测试结果（运行后生成）
└─ report.html          # 可视化报告（运行后生成）
```

## 运行

```bash
# 在仓库根目录（Fullspace/）运行
pip install -r demos/k12-education/requirements.txt
python demos/k12-education/tests/run_all.py          # 跑三版测试 → metrics.json（~40s）
python demos/k12-education/report/generate_report.py # → report.html（浏览器打开）
```

## 关键发现（实测）

| 指标 | LangGraph | Fullspace（纯 intent） | Fullspace-Hybrid |
|---|---|---|---|
| 功能正确性 | 三版 100% 一致 | 三版 100% 一致 | 三版 100% 一致 |
| 路由开销·回环场景 | 4 次条件边 | 9 次 ANN | **4 次 ANN（追平 LG）** |
| 延迟中位（普适 200） | 2.30 ms | 0.36 ms | **0.15 ms（最快）** |
| 运行时可加 agent | 需重新编译 | 可以 | 可以 |

**结论**：混合路由让 Fullspace 在路由开销上追平 LangGraph，延迟反而最低，且仍保留运行时扩展能力。证明 Fullspace 的「路由次数多」是默认策略选择、不是本质劣势。

## 报告包含

① 三维雷达图（9 维总览）② 各场景三维柱状图 ③ 规模 scaling 折线 ④ 普适负载延迟分布 ⑤ 逐场景三维裁决表 + OOD/变更附录。

## 诚实声明

静态小图上 LangGraph 预连边为 0 路由决策，Fullspace 每跳 1 次 ANN——这是动态/软路由的代价。Fullspace 的结构性优势是**表达力**（运行时可加 agent、OOD 软降级）；延迟优势要在**大规模 + FAISS** 时才翻转。Hybrid 版则进一步证明：通过混合路由，Fullspace 可在确定流程上补齐这个代价。请结合场景选型。
