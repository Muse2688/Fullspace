# Fullspace

**能力流形 Agent 运行时 —— 在高维能力空间中路由自主智能体，而非依赖硬连线的图。**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![CI](https://github.com/Muse2688/Fullspace/actions/workflows/ci.yml/badge.svg)](https://github.com/Muse2688/Fullspace/actions/workflows/ci.yml)

> 🌐 **语言：** [English](README.md) · [简体中文](README.zh-CN.md)

---

## 为什么是 Fullspace

主流 agent 框架沿袭了一个 60 年的老抽象：**图**。你声明节点、连线，再由路由器
逐个评估条件分支决定走向。它能用，却封死了 agent 的上限：

- **拓扑在编译期就冻结**，运行时无法生长。
- **路由是离散枚举**，条件边只能返回你预先声明的名字——不能插值、不能优雅降级。
- **每个分支都要一次路由决策**，扩展到 *N* 个专家后，每步路由成本 *O(N)*。

Fullspace 用**能力空间路由**取代连线。每个能力是高维语义流形中的一个点；"下一步
去哪"由一次最近邻查询回答，而非遍历一张连线图。你导航的 3D **球面**只是该空间的
人机投影——**路由从不使用投影**，正因为图没有内在维度。

> **核心命题：能力空间路由胜过边连线。** 用一次向量查询定位正确能力（而非预连 *N*
> 条边、每分支评估一次路由器），是 Fullspace 全部优势的单一来源。

## 特性

| | 特性 | 含义 |
|---|---|---|
| 🧭 | **能力空间路由** | 按语义邻近度软路由——无需枚举节点名 |
| ✨ | **动态物化** | 无匹配时按需生成能力（拓扑涌现） |
| 🌊 | **多模态执行** | 离散（图等价）、场扩散、波前三种流动策略 |
| ⚡ | **无屏障并行** | 每步激活一个邻域——无超步同步屏障 |
| 🛡️ | **OOD 优雅降级** | 始终路由到最近能力，无需显式 fallback 接线 |
| 🔁 | **双向 LangGraph 互操作** | LangGraph 子图作为区域嵌入；Fullspace 导出为 LangGraph 节点；作为 langchain `Runnable` 运行 |
| 💾 | **持久化与时间旅行** | 内存 + SQLite 检查点；恢复；检查点历史 |
| 📈 | **次线性扩展** | 接入 FAISS 获得 *O(log N)* 路由 |
| 🔄 | **流式与异步** | `stream`/`astream` 逐步产出事件；支持 `async def` 节点（对标 LangGraph stream） |
| 🚀 | **embedding 缓存** | 缓存重复 intent 的 embedding（循环场景调用数降 20×） |
| 🔬 | **确定可复现** | 可设种子，同输入同轨迹 |

## 工作原理

```
                          能力流形
        （高维 embedding；3D 球面是其导航投影）

            ·search        ·calc              ·summarize
               \             |                   /
                \            |                  /
   任务 ─► embed ─► ANN ─► 最近区域 ─► 运行节点
                /            |                  \
               /             |                   \
            ·translate     ·code                ·plan

   ┌──────────────────────────────────────────────────────────────┐
   │  定位 ─► 运行 ─► (状态 Δ + 意图向量) ─► 路由 ─► ...            │
   │           命中 汇点 / halt / 预算 即终止                       │
   └──────────────────────────────────────────────────────────────┘
```

**流动策略**决定每步激活多少能力（离散→1；场/波前→邻域）。**混合路由器**默认做一次
粗粒度最近邻跳转，仅在真正歧义的路口升级到 LLM 消解，并在近失配时**物化**新能力。
完整设计见 [docs/architecture.md](docs/architecture.md)。

## 安装

> `fullspace` **已发布到 PyPI**（当前 `0.1.0`），直接用 pip 安装：

```bash
# 核心（零重依赖）
pip install fullspace
pip install faiss-cpu          # + 规模化次线性 ANN
```

需要 LangGraph 互操作/评测、测试、mypy 等 extras，或想改源码贡献代码，可克隆仓库做可编辑安装：

```bash
git clone https://github.com/Muse2688/Fullspace.git
cd Fullspace
pip install -e ".[langgraph,dev]"
```

> Fullspace 默认极轻量：仅需 NumPy。FAISS、sentence-transformers、UMAP、LangGraph
> 都是**可选**扩展——按需安装，Fullspace 会自动启用。

## 快速开始

```python
from fullspace import Capability, HashEmbedder, Manifold
from fullspace.engine import Engine, NodeResult

manifold = Manifold(HashEmbedder())
manifold.register_many([
    Capability("search",    "search the web for information"),
    Capability("calc",      "perform arithmetic and math calculations"),
    Capability("summarize", "summarize a long document into key points"),
    Capability("end",       "final answer output", metadata={"sink": True}),
])

agent = Engine(manifold)
agent.bind("search",    lambda ctx: NodeResult(updates={"found": "..."},
                                              intent="summarize a long document into key points"))
agent.bind("summarize", lambda ctx: NodeResult(updates={"summary": "..."}, goto="end"))
agent.bind("end",       lambda ctx: NodeResult(updates={"answer": "..."}))

result = agent.run("search the web for information")
print(result.trajectory)   # ['search', 'summarize', 'end']
```

将 `HashEmbedder` 换成 `SentenceTransformersEmbedder` 或 `OpenAIEmbedder`，把纯函数
handler 换成 LLM 驱动的，即可从"可运行机制"走向"生产级语义"。

## 基准测试（对照真实 LangGraph）

Fullspace 在相同工作流上与已安装的 LangGraph 直接对比（`python -m fullspace.eval`）：

| 维度 | 结果 |
|---|---|
| 镜像模式（线性/分支/循环/ReAct）的正确性与节点执行数 | **平手** |
| **表达力**——动态物化 | **Fullspace 胜**（LangGraph 无法表达） |
| **OOD 鲁棒性**——无 fallback 接线 | **Fullspace 胜**（LangGraph 报错） |
| **规模化路由延迟**——FAISS，`eval.scaling` | **Fullspace 胜**（*N*=5k–20k 时约 80–123×） |
| **无屏障并行** | **Fullspace 胜** |
| 生态兼容性 | **Fullspace 胜**（双向互操作 + `Runnable`） |
| 微型静态图的路由开销 | LangGraph（预连边免费；规模化后被反超） |

评测 harness 是事实来源——宣称任何胜出前请先跑它。方法论与 scaling 曲线：
`python -m fullspace.eval.scaling`。

## 示例

| 示例 | 模式 |
|---|---|
| [`linear_pipeline`](fullspace/examples/linear_pipeline.py) | `A → B → C`（图等价） |
| [`branching`](fullspace/examples/branching.py) | 任务相关的软路由 |
| [`react_agent`](fullspace/examples/react_agent.py) | ReAct 循环（思考→行动→观察） |
| [`interrupt_resume`](fullspace/examples/interrupt_resume.py) | 人在回路 / 容错 |
| [`streaming`](fullspace/examples/streaming.py) | 同步/异步流式（`async def` 处理器） |

```bash
python -m fullspace.examples.react_agent
python -m fullspace.viz            # 交互式 3D 能力球 → fullspace_sphere.html
```

## 对比 Demo

仓库附带一个 K12 教育对比 demo（[`demos/k12-education/`](demos/k12-education/)）：用同一套 8 个教学
agent，分别用 **LangGraph**、**Fullspace**、**Fullspace 混合路由版**实现，跑 200 个随机负载的多维对比
测试（功能一致性、路由开销、延迟、规模 scaling、OOD、变更实验），产出交互式 HTML 报告。实测表明，
混合路由版（线性 goto + 分支 intent + 决策缓存）能在路由开销上追平 LangGraph，同时保留运行时扩展
能力。详见该目录的 README。

## 路线图

- [x] 流形基底、ANN 索引、3D 投影
- [x] 引擎：离散 / 场 / 波前流动策略、混合路由
- [x] 状态：每键 reducer、检查点、恢复、时间旅行
- [x] 双向 LangGraph 互操作与 langchain `Runnable`
- [x] 双轨评测 harness + FAISS scaling
- [x] 流式 + 异步（`stream` / `astream` / `ainvoke`，`async def` 节点）
- [x] 重复 intent 的 embedding 缓存
- [ ] 投机预热与邻近前缀缓存*（随真实 LLM 集成落地）*
- [ ] 连续导航流动策略
- [ ] 参考集成：OpenAI、Anthropic、sentence-transformers

## 参与贡献

欢迎贡献。代码库全量类型检查（`mypy` 零错误），68 个测试覆盖。提 PR 前请运行
`pip install -e ".[langgraph,dev]" && pytest -q`。

## 引用

如 Fullspace 对你的工作有所启发，请引用：

```bibtex
@software{fullspace,
  title  = {Fullspace: A Capability-Manifold Agent Runtime},
  author = {Fullspace},
  year   = {2026},
  url    = {https://github.com/Muse2688/Fullspace},
  note   = {Capability-space routing as a successor to graph-based agent orchestration}
}
```

概念脉络：图结构 agent 运行时源自 **Pregel** 整体同步模型（Malewicz 等，2010）。
Fullspace 将 agent 路由重新表述为连续**能力流形**上的最近邻检索——与混合专家
（mixture-of-experts）和稠密检索相关——使拓扑能在运行时涌现，而非静态声明。

## 许可证

[MIT](LICENSE) © Fullspace
