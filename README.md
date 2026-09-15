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

**关键设计：这一维度只标注、不判罪——规则层和 LLM 层都不判。**

规则无法判断一个假设是否"实质且不被来源支持"，硬判只会制造误报。而我原以为 LLM 能补上这个判断力，**实测证明不能**（详见第四节）：它会连「改造前后数据口径相同」这类任何研究都默认成立的方法论前提一起列出，且对"是否构成缺陷"的自我评定未经校准。接入后召回没增加、误报大涨；改用提示词纠正，反而更差。

所以最终按证据把这一维度**退化为提示通道**（输出 `info` 级标注项，不影响判定），模型自评的严重程度保留在 `detail.raw_severity` 里供人工参考。

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

在 `data/bad_cases.jsonl`（**30 条人工标注样本**：20 条含缺陷 + 10 条干净）上的实测指标。

三种配置的对比 —— 这张表是本项目最有信息量的部分：

| 配置 | 拦截率 Recall | 误报率 FPR | 精确率 Precision | F1 | 准确率 |
|---|---|---|---|---|---|
| **纯规则**（无需密钥） | 75.0% | **0.0%** | **100.0%** | 85.7% | 83.3% |
| **hybrid（朴素接入 LLM）** | **100.0%** | 60.0% | 76.9% | 87.0% | 80.0% |
| **hybrid（校准后）** | **100.0%** | **10.0%** | **95.2%** | **97.6%** | 96.7% |

> hybrid 模式使用 `deepseek-chat`（`temperature=0`）。
> 复现：`python eval/run_eval.py --mode rule --show-misses`
> 　　／ `python eval/run_eval.py --mode hybrid --show-misses`（需配置 LLM 凭据）

### 为什么第一版 hybrid 是「坏」的

朴素地把三个检查器都接上 LLM 后，**召回从 75% 涨到 100%，但误报从 0% 涨到 60%，F1 几乎没动（85.7% → 87.0%）**。

换句话说：**多花的 LLM 调用没有换来净收益，只是把「漏报」换成了「误报」。**

逐条归因后发现问题**全部集中在「假设识别」这一个维度**：

| 样本 | 由哪个检查器命中 |
|---|---|
| 5 条语义类缺陷（语义错位 / 样本内外推 / 绝对化断言 / 与来源冲突） | `provenance` **和** `contradiction` **双双命中** |
| 10 条干净样本中的 6 条误报 | **只有 `assumption` 报错** |

也就是说：**假设维度对召回贡献为 0，却贡献了全部误报。**

### 由此得出的设计决定：假设维度只标注，不判罪

「找出未言明的假设」这个任务**没有天然的停止条件**——任何结论都依赖无穷多隐含前提。模型总能列出若干条（实测中它会把「改造前后数据口径相同」「回测存在幸存者偏差风险」这类**任何研究都默认成立的方法论前提**也列出来），而且它对「这条假设是否构成缺陷」的自我评定是**未经校准**的。

我还试过用提示词纠正它（明确要求「不要列常识或定义，只列结论所必需且来源不支持的假设」）——**结果误报从 6 条升到 9 条，反而更差**。

因此最终决定：**假设检查器只产出「标注项」（`info` 级），不参与整体判定**，作为人工复核的提示通道。模型自评的严重程度保留在输出的 `detail.raw_severity` 里，供人参考，但不影响 verdict。

> 这与规则层原本的取向一致（"宁可漏报，不可误报"），只是当时以为 LLM 能补上判定能力，**实测证明不能**。

### 按缺陷类型拆分（校准后的 hybrid）

| 缺陷类型 | 样本 | 规则模式 | 校准后 hybrid |
|---|---|---|---|
| 幻觉数字 `hallucinated_number` | 5 | **100%** | **100%** |
| 幻觉百分比 `hallucinated_pct` | 2 | **100%** | **100%** |
| 转录错误 `transcription_error` | 2 | **100%** | **100%** |
| 方向矛盾 `direction_conflict` | 2 | **100%** | **100%** |
| 算术错误 `arithmetic_error` | 2 | **100%** | **100%** |
| 无出处指标 `unsourced_metric` | 2 | **100%** | **100%** |
| 语义错位 `semantic_mismatch` | 2 | 0% | **100%** ← LLM 补上 |
| 样本内外推 `extrapolation` | 1 | 0% | **100%** ← LLM 补上 |
| 绝对化断言 `absolute_claim` | 1 | 0% | **100%** ← LLM 补上 |
| 与来源冲突 `contradiction_with_source` | 1 | 0% | **100%** ← LLM 补上 |
| 干净样本 `clean` | 10 | 误报 0 | 误报 1 |

### 剩下那 1 个误报：很可能是我的标注错了，不是工具的错

校准后仅剩的误报是 `gc-10`，我逐字复核后的结论是——**大概率是我这条 ground truth 标错了**：

```
来源[plan]：下一阶段计划把自适应阈值扩展至 21 个行业。
结论      ：基于现有回测结果，下一阶段将把阈值扩展至 21 个行业。
```

数字（21）确实有出处，所以我最初把它标为 `clean`。**但结论里「基于现有回测结果」这个依据，在来源中根本不存在**——来源只说"计划"，没说依据是回测。工具指出「该依据在来源中不存在」是**对的**。

我保留了这个 `clean` 标注、没有事后改标签去美化指标。**在 30 条样本上，1 条标签存疑就足以让 FPR 相差 10 个百分点**——这正是下面"已知局限"里强调样本规模的原因。

### 这张表说明了什么

1. **所有可被精确判定的缺陷，规则层 100% 命中，且零误报**——这部分不需要模型，也不需要密钥。
2. **模型真正补上的，恰好是规则做不到的那 5 条语义类缺陷**，且校准后召回 100%、误报 10%。
3. **"接入 LLM 就一定更好"是错的**：不区分「刚性/柔性」和「判定/提示」，接入 LLM 会把 F1 从 85.7% 拉到 87.0% —— 几乎白干；分清之后才到 97.6%。

> 这个项目不只是"能查错"，它还**量化地指出了「代码该做什么、模型该做什么、以及什么东西本来就不该被自动判罪」的分界线**。

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

任何 **OpenAI 兼容**接口都可以（DeepSeek / 百炼 / 本地 Ollama / vLLM）：

```bash
# DeepSeek（本文指标即在此模型上测得）
export TRUSTGUARD_LLM_BASE_URL="https://api.deepseek.com/v1"
export TRUSTGUARD_LLM_API_KEY="sk-..."
export TRUSTGUARD_LLM_MODEL="deepseek-chat"

# 或阿里云百炼
# export TRUSTGUARD_LLM_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
# export TRUSTGUARD_LLM_MODEL="qwen-plus"

trustguard check --claim @"..." --source @"..." --mode auto
```

未配置凭据时，`--mode auto` 会**自动降级为纯规则**，而不是报错。

> 需要 `requests`（`pip install "trustguard[llm]"`）。走代理的环境请同时设置 `HTTPS_PROXY`。
> **凭据只从环境变量读取，不会写入任何文件或报告。**

---

## 八、已知局限（诚实清单）

一个用来检查"结论是否经得起追问"的工具，自己首先要经得起追问：

1. **强依赖来源材料。** 未提供来源时，只有算术校验能工作，其余检查会如实报告"无法检查"而不是假装通过。
2. **派生值只覆盖"区间变化率"这一种形式。** 由来源数字做求和、乘积、比值得到的值，目前仍会被判为"无出处"。
3. **假设维度不判罪，只作提示。** 规则层与 LLM 层都只产出 `info` 级标注项，不参与 verdict。原因是实测得出：任何结论都依赖无穷多隐含前提，"列出未言明的假设"没有天然停止条件，模型的严重程度自评未经校准——见第四节。**这意味着本项目不会因为"结论依赖某个未言明的假设"而判 FAIL，需要人工看标注项。**
4. **hybrid 模式的指标绑定具体模型。** 上面的 100%/10% 是在 `deepseek-chat` 上测得；换模型需要重跑评估，指标会变。规则模式则与模型无关。
5. **数据集仅 30 条**，规模偏小，单项指标的置信区间较宽；尤其是只有 1 条样本的类型（如 `extrapolation`），其 0%/100% 更多是说明性质而非统计结论。**证据：那 1 条存疑的 ground truth（`gc-10`）就让 FPR 相差 10 个百分点。**
6. **以中文场景为主**，英文表述的规则覆盖有限（数据集里保留了 1 条英文样本用于回归）。
7. **数值匹配是精确匹配**（归一化后），不做单位换算（`kWh` 与 `MJ` 之间不会互相识别）。

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

代码约 **1,790 行**（`src/`），测试约 **569 行**。

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

**Measured on a hand-labelled dataset of 30 cases (20 defective + 10 clean).** Pure-rule mode reaches **75.0% recall at 0.0% false-positive rate** (100% precision, F1 85.7%) — every *exactly decidable* defect category is caught at 100%, and all five misses fall in categories that require semantic understanding.

Naively enabling the LLM layer raises recall to 100% but pushes the false-positive rate to 60% (F1 barely moves, 85.7% → 87.0%): the extra calls merely converted misses into false alarms. Attribution showed the entire effect came from **one dimension** — "unstated assumptions", which contributed *zero* recall (two other checkers already caught every semantic defect) while producing *every* false positive. Telling the model to ignore generic methodological preconditions made it *worse* (6 → 9 false positives).

So that dimension was demoted to an advisory `info` channel by measurement, not by preference. The calibrated hybrid reaches **100% recall at 10.0% FPR (95.2% precision, F1 97.6%)** — and the one remaining false positive is arguably a mislabelled ground truth rather than a tool error (documented in §4).

The project therefore not only catches errors, it **quantifies the boundary between what code should do, what models should do, and what should not be auto-judged at all**.

Zero runtime dependencies, 97 unit tests, fully reproducible offline: `pytest && python eval/run_eval.py`.

MIT licensed. Built independently; the dataset is synthetic and contains no real enterprise or personal data.
