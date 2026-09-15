# TrustGuard · LLM Agent 输出的可信性检查器

> 把「人机边界协议」的三重质疑机制，变成一段可执行、可测试、可量化的代码
>
> **数据溯源** → **假设识别** → **逻辑反向推演**

`Python` · 零运行时依赖 · 97 个单元测试 · 30 条标注数据集 · **纯规则模式即可离线运行，无需任何 API key**

---

## 一、要解决的问题

让大模型做分析，最大的风险不是"答不出来"，而是**答错了没人发现**：

| 失败模式 | 例子 |
|---|---|
| **幻觉数字** | 回测报告写 32.4%，结论写成 45.2% |
| **转录错误** | 来源是 542.9，抄成 542.7——差一点点，但结论全偏 |
| **语义错位** | 来源讲"营收 82.3 亿"，结论写成"利润 82.3 亿"——数字对得上，意思全错 |
| **隐藏假设** | 用样本内回测结论，去预测明年的收益 |
| **方向矛盾** | 数值明明是下降，文中写"提升" |
| **算术错误** | 由 200 降到 150，却写"降低 50%" |

这些问题的共同点是：**数字看起来都很专业，但经不起追问**。

TrustGuard 的作用就是在上游把这些拦下来——**任何 AI 输出在被采纳前，先过三重质疑**。

---

## 二、三重质疑机制

### 第一重：数据溯源 —— 每个数字都能追到出处吗？

把结论里的数字逐个抽出，回到来源材料里找。支持千分位与量级换算，因此 `1,683` 与 `1683`、`330 万` 与 `3300000` 都能匹配。

**关键设计：区分「凭空出现的数字」和「由已溯源数字推导出的数字」。**
「能耗由 200.0 kWh 降至 150.0 kWh，降低 25%」里的 25% 没有直接出处，但它是算出来的——不能当成幻觉。

### 第二重：假设识别 —— 结论依赖哪些没说出口的前提？

标注外推假设（`预计` / `未来`）、绝对化假设（`必然` / `所有`）、因果假设（`因此` / `说明`）。

**关键设计：规则层只标注、不判罪。** 规则无法判断一个假设是否"实质且不被来源支持"，硬判只会制造误报。

### 第三重：逻辑反向推演 —— 从结论倒推，会不会推出矛盾？

- **方向矛盾**：说"提升"但数值下降
- **区间颠倒**：说"从 X 到 Y"但 X > Y
- **疑似转录错误**：某个数字无出处，但与来源中某个数字**只差不到 2%**

### 附加：算术一致性（纯确定性）

校验「由 X 变到 Y，变化 Z%」中的变化率是否算得对。这一类错误可以被**精确判定**，最适合交给代码。

---

## 三、核心设计：刚性任务交给代码，柔性任务交给模型

这是整个项目最重要的架构决策，也是它想证明的主张：

| 层次 | 负责什么 | 为什么 |
|---|---|---|
| **确定性层**（代码/规则） | 数值比对、算术校验、方向矛盾、近似匹配 | 这些**可以被精确判定**。交给代码 → 零误报、可解释、可复现 |
| **语义层**（LLM） | 语义错位、隐藏假设、与来源的实质冲突 | 这些**需要理解语义**。交给模型 → 但由确定性层兜底校验它的输入 |

因此 TrustGuard 有两种运行模式：

| 模式 | 需要 API key | 说明 |
|---|---|---|
| `rule`（默认） | ❌ **不需要** | 纯规则，离线可跑，用于测试与评估 |
| `hybrid` | ✅ 需要 | 规则 + LLM 语义增强 |

> **工程上"开箱可验证"比"功能更强"更重要。** 任何人都能 clone 下来跑通全部测试与评估，不需要注册任何服务。

---

## 四、实测结果

在 `data/bad_cases.jsonl`（**30 条人工标注样本**：20 条含缺陷 + 10 条干净）上的实测指标：

### 总体（纯规则模式）

| 指标 | 数值 |
|---|---|
| **拦截率 Recall** | **75.0%** |
| **误报率 FPR** | **0.0%** |
| **精确率 Precision** | **100.0%** |
| **F1** | **85.7%** |
| 准确率 Accuracy | 83.3% |

### 按缺陷类型拆分

| 缺陷类型 | 样本 | 规则模式命中率 |
|---|---|---|
| 幻觉数字 `hallucinated_number` | 5 | **100%** |
| 幻觉百分比 `hallucinated_pct` | 2 | **100%** |
| 转录错误 `transcription_error` | 2 | **100%** |
| 方向矛盾 `direction_conflict` | 2 | **100%** |
| 算术错误 `arithmetic_error` | 2 | **100%** |
| 无出处指标 `unsourced_metric` | 2 | **100%** |
| 语义错位 `semantic_mismatch` | 2 | **0%** ← 需语义理解 |
| 样本内外推 `extrapolation` | 1 | **0%** ← 需语义理解 |
| 绝对化断言 `absolute_claim` | 1 | **0%** ← 需语义理解 |
| 与来源冲突 `contradiction_with_source` | 1 | **0%** ← 需语义理解 |
| 干净样本 `clean` | 10 | 误报 **0** |

### 这张表说明了什么

**所有可被精确判定的缺陷，规则层 100% 命中，且零误报。**
**漏掉的 5 条全部集中在「需要理解语义才能判断」的类别**——这正是 LLM 应当介入的地方，也是 `hybrid` 模式要补的缺口。

> 换句话：**这个项目不只是"能查错"，它还量化地指出了"代码该做什么、模型该做什么"的分界线。**
> 复现命令：`python eval/run_eval.py --mode rule --show-misses`

---

## 五、快速开始

```bash
git clone https://github.com/jason218-ljs/trustguard.git
cd trustguard
pip install -e ".[dev]"

pytest                                   # 97 个测试，全部离线可跑
python eval/run_eval.py                  # 复现上表指标
trustguard demo                          # 看一个完整示例
```

**无需任何 API key。**

---

## 六、命令行用法

```bash
# 内置示例（无需任何配置）
trustguard demo

# 检查一段结论
trustguard check \
  --claim "本策略年化收益 45.2%，最大回撤 12.3%。" \
  --source "backtest=回测显示年化收益 32.4%，最大回撤 12.3%。"

# 从文件读（@ 前缀）
trustguard check --claim @claim.md --source @backtest-report.txt

# JSON 输出，便于接入其它工具
trustguard check --claim "..." --source "..." --json

# 接入 CI：判定达到 WARN 就以退出码 1 结束
trustguard check --claim @claim.md --source @data.txt --fail-on warn

# 写入报告文件
trustguard check --claim @claim.md --source @data.txt --out report.md
```

退出码：`0` 未达阈值 ｜ `1` 达到阈值（可用于 CI 卡点）｜ `2` 用法或运行错误。

---

## 七、作为库使用

```python
from trustguard import TrustGuard, Source

guard = TrustGuard()          # 纯规则，离线可用
report = guard.check(
    claim="本策略年化收益 45.2%。",
    sources=[Source(id="backtest", text="回测显示年化收益 32.4%。")],
)

print(report.verdict)          # Verdict.WARN
for issue in report.all_issues:
    print(issue.severity.value, issue.message, "|", issue.evidence)
```

输出：

```
warn 数字 45.2% 在来源材料中找不到出处 | 本策略年化收益 45.2%。
```

### 接入真实 LLM（可选）

任何 **OpenAI 兼容**接口都可以（百炼 / DeepSeek / 本地 Ollama / vLLM）：

```bash
export TRUSTGUARD_LLM_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
export TRUSTGUARD_LLM_API_KEY="sk-..."
export TRUSTGUARD_LLM_MODEL="qwen-plus"

trustguard check --claim @"..." --source @"..." --mode auto
```

未配置凭据时，`--mode auto` 会**自动降级为纯规则**，而不是报错。

---

## 八、已知局限（诚实清单）

一个用来检查"结论是否经得起追问"的工具，自己首先要经得起追问：

1. **强依赖来源材料。** 未提供来源时，只有算术校验能工作，其余检查会如实报告"无法检查"而不是假装通过。
2. **派生值只覆盖"区间变化率"这一种形式。** 由来源数字做求和、乘积、比值得到的值，目前仍会被判为"无出处"。这是当前误报的主要来源。
3. **假设识别的规则层召回率天然为 0**（只标注不判罪）。这是刻意的取舍：宁可漏报，不可误报。该类别需要 LLM 或人工。
4. **数据集仅 30 条**，规模偏小，单项指标的置信区间较宽；尤其是只有 1 条样本的类型（如 `extrapolation`），其 0%/100% 更多是说明性质而非统计结论。
5. **以中文场景为主**，英文表述的规则覆盖有限（数据集里保留了 1 条英文样本用于回归）。
6. **数值匹配是精确匹配**（归一化后），不做单位换算（`kWh` 与 `MJ` 之间不会互相识别）。

---

## 九、目录结构

```
.
├── src/trustguard/
│   ├── models.py              # 数据模型：Source / Issue / CheckResult / Report
│   ├── extract.py             # 确定性层：数字抽取、等价匹配、算术校验
│   ├── llm.py                 # LLM 接入抽象（可插拔，可为空）
│   ├── pipeline.py            # 编排三重质疑并汇总判定
│   ├── report.py              # Markdown / JSON 报告渲染
│   ├── cli.py                 # 命令行入口
│   └── checkers/              # 四个检查器
│       ├── provenance.py      #   一、数据溯源
│       ├── assumption.py      #   二、假设识别
│       ├── contradiction.py   #   三、逻辑反向推演
│       └── arithmetic.py      #   附、算术一致性
├── data/bad_cases.jsonl       # 30 条标注数据集（11 种缺陷类型）
├── eval/run_eval.py           # 评估脚本（混淆矩阵 + 分类别命中率）
├── tests/                     # 97 个单元测试
└── .github/workflows/ci.yml   # CI：测试 + 评估
```

代码约 **1,782 行**（`src/`），测试约 **559 行**。

---

## 十、设计取舍说明

几个刻意的"不这么做"，它们比"做了什么"更能说明这个项目的工程取向：

| 取舍 | 原因 |
|---|---|
| **不输出单一"可信度分数"** | 一个 0.73 的分数无法指导行动。本项目只输出**带证据的具体问题**，每条都能指回原文 |
| **LLM 失败时降级而非中断** | 语义检查失败只记录一条 INFO，确定性结论仍然有效 |
| **规则层对小整数不判罪** | "共 3 个环节"里的 3 是计数，不是断言。用"是否带小数点 / 是否带 %"来区分指标与计数 |
| **数值匹配容差收到 1e-9** | 早期用 0.1% 相对容差，导致 `542.7` 与 `542.9` 被判为相等，转录错误类缺陷**全部漏检**——这是实测数据暴露出来的真实缺陷，已修正并加了回归测试 |
| **歧义时放弃而非猜测** | 句中出现多个候选百分比时视为歧义直接跳过，不猜 |

---

## 声明

- 本项目为个人独立完成的**开源工具**，与任何实习或课程项目无关，代码与数据均为原创。
- 数据集为**人工构造的样例**，不含任何真实企业数据、个人数据或商业信息。
- 工具输出**仅作为人工复核的提示**，不构成对任何结论正确性的最终判定，**不构成投资建议**。
- MIT License，欢迎自由使用与修改。

---

## English Summary

**TrustGuard** is a trustworthiness guard for LLM agent outputs. It implements a **triple-challenge** check — *data provenance*, *assumption identification*, and *reverse logical deduction* — as executable, testable, quantifiable code.

**The central design claim:** deterministic tasks belong to code, semantic tasks belong to models. Numeric comparison, arithmetic validation, directional conflicts and near-miss typo detection can be **decided exactly** — so they run as pure rules with zero false positives, no latency and no API key. Semantic mismatches, hidden assumptions and real conflicts with sources need language understanding — those are delegated to an LLM, with the deterministic layer validating its inputs.

**Measured on a hand-labelled dataset of 30 cases (20 defective + 10 clean), pure-rule mode achieves 75.0% recall at 0.0% false-positive rate (100% precision, F1 85.7%).** Every defect category that is *exactly decidable* is caught at 100%; all five misses fall in categories that require semantic understanding — which is precisely where the LLM layer is meant to help. The project therefore not only catches errors, it **quantifies the boundary between what code should do and what models should do**.

Zero runtime dependencies, 97 unit tests, fully reproducible offline: `pytest && python eval/run_eval.py`.

MIT licensed. Built independently; the dataset is synthetic and contains no real enterprise or personal data.
