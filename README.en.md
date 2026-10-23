# TrustGuard

[![PyPI](https://img.shields.io/pypi/v/trustguard-ai.svg)](https://pypi.org/project/trustguard-ai/)
[![Python](https://img.shields.io/pypi/pyversions/trustguard-ai.svg)](https://pypi.org/project/trustguard-ai/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-97%20passed-brightgreen.svg)](#)

**English** | [中文](README.md)

**Find out which numbers in an AI-generated conclusion were made up.**

Give it a claim plus the source material it cites, and TrustGuard points out — line by line — which number has no provenance, which sentence contradicts the source, and which percentage change is arithmetically wrong. **Every issue carries its evidence span, so a human can verify it directly.**

```bash
pip install trustguard-ai     # installs the `tguard` command
tguard demo
```

Zero runtime dependencies · **pure-rule mode runs fully offline with no API key** · 97 unit tests · 30 hand-labelled cases

---

## See it in 30 seconds

Real, untruncated output of `tguard demo` (the tool is Chinese-first — shown as-is):

```text
[trustguard] verdict=warn mode=rule errors=0 warnings=1

**Verdict: ⚠️ WARN (suspicious items found, human review recommended)**

## Claim under review
> The portfolio delivered significant excess return this quarter: AlphaForge's selected
> holdings returned 32.4% annualised, well above the 8.1% benchmark, showing the factor
> system is persistently effective in the A-share market. Next year's return is expected
> to reach 40%+.

## 1. Data provenance — WARN
stats: numbers_total=3 | sourced=2 | unsourced=1 | sourced_ratio=0.6667

- ⚠️ **Number 40% has no source in the provided material**
  - evidence: `... Next year's return is expected to reach 40%+.`

## 2. Assumption surfacing — PASS
annotations (not defects, for human reference only)
- ℹ️ possible extrapolation assumption (past/sample → future/population): "expected"
- ℹ️ possible causal assumption (correlation read as causation): "showing"
```

> The original output is in Chinese; the block above is a translated excerpt of the real run, not a mock-up.

Note what it does **not** do: it never returns a single "trust score: 0.73". A score cannot guide action, so it only reports concrete, evidence-backed issues.

---

## What it catches

The dangerous failure of an LLM doing analysis is not "it can't answer" — it's **"it answered wrong and nobody caught it."**

| Failure mode | Example | Handled by |
|---|---|---|
| **Hallucinated number** | Backtest says 32.4%, the write-up says 45.2% | rules |
| **Transcription error** | Source says 542.9, the claim says 542.7 — tiny gap, conclusion destroyed | rules |
| **Direction conflict** | The value went down, the text says "improved" | rules |
| **Arithmetic error** | 200 → 150, described as "a 50% decrease" | rules |
| **Semantic drift** | Source says "revenue 8.23B", claim says "profit 8.23B" — right number, wrong meaning | LLM |
| **Hidden assumption** | In-sample backtest results used to predict next year's return | annotated, never judged |

All of these share one property: **the numbers look professional, but they don't survive a follow-up question.**

---

## How it differs from RAGAS / DeepEval / LangSmith

Not a replacement — a different division of labour:

| Tool | Problem it solves | Input | Output |
|---|---|---|---|
| **RAGAS** | RAG retrieval & generation quality | question / answer / contexts | metric scores (faithfulness, relevancy…) |
| **DeepEval** | LLM outputs as unit-test assertions | test case + assertion | pass / fail + score |
| **LangSmith / Langfuse** | tracing, observability, regression | trace data | trace views + eval results |
| **Guardrails AI / NeMo Guardrails** | I/O guardrails (format, safety, policy) | a single text | block / rewrite |
| **TrustGuard** | **number-level consistency** between a claim and its given sources | `claim` + `sources` | **evidence-backed concrete issues** + verdict |

Two substantive differences:

1. **The default mode calls no model at all.** Most tools above are LLM-judge-centric: they need a key, cost money, and are non-deterministic. TrustGuard's `rule` mode is plain deterministic code — same input, same output, forever. That makes it usable as a CI gate.
2. **It outputs verifiable issues, not scores.** `Number 40% has no source | evidence: "…reach 40%+"` is a statement a human can check in two seconds. A score is not.

> **Honest note: there is no head-to-head benchmark in this repo.** The input contracts differ (those tools evaluate the quality of a RAG pipeline's retrieval/generation; TrustGuard checks consistency between a claim and given sources), so running them on one metric set would produce a misleading comparison. This is a known gap, not a hidden one.

---

## Results

Measured on `data/bad_cases.jsonl`: **30 hand-labelled cases (20 defective + 10 clean)**, 11 defect types.

| Configuration | Recall | FPR | Precision | F1 | Accuracy |
|---|---|---|---|---|---|
| **Pure rules** (no API key) | 75.0% | **0.0%** | **100.0%** | 85.7% | 83.3% |
| **Hybrid, naive LLM** | **100.0%** | 60.0% | 76.9% | 87.0% | 80.0% |
| **Hybrid, calibrated** | **100.0%** | **10.0%** | **95.2%** | **97.6%** | 96.7% |

> Hybrid runs use `deepseek-chat` at `temperature=0`.
> Reproduce: `python eval/run_eval.py --mode rule --show-misses`

**The most informative row is the middle one.** Naively wiring an LLM into every checker lifts recall from 75% to 100% — and pushes false positives from 0% to 60%. F1 barely moves (85.7% → 87.0%). The extra tokens bought nothing; they just converted misses into false alarms.

Attribution showed the entire effect came from **one dimension**: *unstated assumptions*. It contributed **zero recall** (two other checkers already caught every semantic defect) while producing **every false positive**. Instructing the model to skip generic methodological preconditions made it *worse* (6 → 9 false positives).

So that dimension was demoted to an advisory `info` channel — by measurement, not by preference. After calibration: **100% recall at 10% FPR**.

### The one remaining false positive is probably my label, not the tool

The single false positive after calibration is `gc-10`. After re-reading it word by word, the most likely explanation is that **the ground truth is wrong**:

```
source[plan]: The next phase plans to extend the adaptive threshold to 21 industries.
claim       : Based on existing backtest results, the next phase will extend the threshold to 21 industries.
```

The number (21) does have a source, so it was originally labelled `clean`. **But the stated basis — "based on existing backtest results" — does not exist in the source**, which only says "plans to". The tool flagging that basis as unsupported is **correct**.

The `clean` label was left in place rather than quietly fixed to improve the numbers. **On 30 cases, one questionable label moves FPR by 10 percentage points** — which is exactly why sample size is listed as a limitation.

---

## Install & usage

### From PyPI

```bash
pip install trustguard-ai
tguard demo
```

### From source (to reproduce the metrics)

```bash
git clone https://github.com/jason218-ljs/trustguard.git
cd trustguard
pip install -e ".[dev]"

pytest                          # 97 tests, all offline
python eval/run_eval.py         # reproduce the table above
tguard demo                     # see a full example
```

**None of the above requires an API key.**

### CLI

```bash
# Built-in example, no configuration
tguard demo

# Check a claim against source material
tguard check \
  --claim "The strategy returned 45.2% annualised, max drawdown 12.3%." \
  --source "backtest=Backtest shows 32.4% annualised, max drawdown 12.3%."

# Read from files (@ prefix)
tguard check --claim @claim.md --source @report.txt

# JSON output for piping into other tools
tguard check --claim "..." --source "..." --json

# CI gate: exit 1 when the verdict reaches WARN
tguard check --claim @claim.md --source @data.txt --fail-on warn

# Write the report to a file
tguard check --claim @claim.md --source @data.txt --out report.md
```

Exit codes: `0` below threshold · `1` threshold reached (usable as a CI gate) · `2` usage/runtime error.

### As a library

```python
from trustguard_ai import TrustGuard, Source

guard = TrustGuard()          # pure rules, offline
report = guard.check(
    claim="The strategy returned 45.2% annualised.",
    sources=[Source(id="backtest", text="Backtest shows 32.4% annualised.")],
)

print(report.verdict)         # Verdict.WARN
for issue in report.all_issues:
    print(issue.severity.value, issue.message, "|", issue.evidence)
```

Output:

```
warn 数字 45.2% 在来源材料中找不到出处 | 本策略年化收益 45.2%。
```

### Connecting a real LLM (optional)

Any **OpenAI-compatible** endpoint works (DeepSeek / DashScope / Ollama / vLLM):

```bash
export TRUSTGUARD_LLM_BASE_URL="https://api.deepseek.com/v1"
export TRUSTGUARD_LLM_API_KEY="sk-..."
export TRUSTGUARD_LLM_MODEL="deepseek-chat"

tguard check --claim @claim.md --source @data.txt --mode auto
```

Without credentials, `--mode auto` **degrades to pure rules instead of failing**. Requires `pip install "trustguard-ai[llm]"`. Credentials are read from environment variables only — never written to any file or report.

---

## Known limitations (honest list)

A tool that checks whether conclusions survive follow-up questions should itself survive them:

1. **Heavily source-dependent.** Without source material, only arithmetic checks run; the rest honestly report "cannot check" rather than silently passing.
2. **Derived values are only covered for interval change rates.** Sums, products and ratios derived from sourced numbers are still flagged as unsourced.
3. **The assumption dimension does not judge — it only surfaces.** Both layers emit `info`-level annotations that never affect the verdict. This is a measured conclusion, not an oversight. **It means the tool will never return FAIL merely because a conclusion rests on an unstated assumption — a human has to read the annotations.**
4. **Hybrid metrics are model-bound.** 100%/10% was measured on `deepseek-chat`; switching models requires re-running the evaluation. Rule mode is model-independent.
5. **Only 30 cases**, so confidence intervals are wide — especially for categories with a single sample. Evidence: one questionable ground-truth label shifts FPR by 10 percentage points.
6. **Chinese-first.** English coverage is limited (one English sample is kept for regression).
7. **Numeric matching is exact after normalisation.** No unit conversion (`kWh` vs `MJ` will not match).
8. **No head-to-head benchmark against comparable tools** (see the note above).

---

## Deep dive

### The triple challenge

**1. Data provenance — can every number be traced to a source?**

Each number in the claim is extracted and looked up in the source material. Thousands separators and magnitude words are normalised, so `1,683` matches `1683` and `3.3M` matches `3300000`.

Key design: **distinguish a number that appears from nowhere from one derived from already-sourced numbers.** In "energy fell from 200.0 kWh to 150.0 kWh, a 25% decrease", the 25% has no direct source — but it is computed, so it must not be reported as a hallucination.

**2. Assumption surfacing — what unstated premises does the conclusion rest on?**

Flags extrapolation (`expected` / `next year`), absolute claims (`necessarily` / `all`), and causal claims (`therefore` / `shows`).

Key design: **this dimension only annotates, never judges — neither the rule layer nor the LLM layer judges.**

Rules cannot tell whether an assumption is "material and unsupported by the source", so hard-judging only manufactures false positives. I assumed an LLM could supply that judgement — **measurement says it cannot**: it lists methodological preconditions that any study takes for granted (e.g. "the data definition is unchanged before and after"), and its self-assessed severity is uncalibrated. Wiring it in raised false positives without adding recall; correcting it via prompt made things worse.

So on the evidence this dimension was **demoted to an advisory channel** (`info`-level annotations that do not affect the verdict). The model's self-assessed severity is preserved in `detail.raw_severity` for human reference.

**3. Reverse logical deduction — does the conclusion contradict itself?**

- **Direction conflict**: claims "improved" while the numbers fell
- **Inverted range**: "from X to Y" where X > Y
- **Suspected transcription error**: a number with no source that differs from some source number by **less than 2%**

**Plus: arithmetic consistency (pure determinism)**

Validates the change rate in "from X to Y, a change of Z%". These errors can be **decided exactly**, which makes them the natural property of code.

### The design claim

> **Deterministic tasks belong to code. Semantic tasks belong to models. Some things should not be auto-judged at all.**

| Layer | Handles | Why |
|---|---|---|
| **Deterministic** (rules) | Numeric comparison, arithmetic, direction conflicts, near-miss typo detection | These are *exactly decidable* → zero false positives, explainable, reproducible |
| **Semantic** (LLM) | Semantic drift, hidden assumptions, real conflicts with source | These need language understanding → delegated, with the deterministic layer validating its inputs |
| **Advisory** (neither) | Unstated assumptions | No natural stopping condition; model self-assessment is uncalibrated → surface it, don't judge it |

Every *exactly decidable* defect category is caught at **100% with zero false positives, no latency, and no API key**. All five rule-mode misses fall in categories that require semantic understanding.

> **"Verifiable out of the box" beats "more capable" in engineering.** Anyone can clone this and run the full test suite and evaluation without signing up for any service.

### Layout

```
src/trustguard_ai/
  models.py         # Source / Issue / CheckResult / Report
  extract.py        # deterministic layer: number extraction, equivalent matching, arithmetic
  llm.py            # pluggable LLM adapter (can be empty)
  pipeline.py       # orchestrates the triple challenge and aggregates the verdict
  report.py         # Markdown / JSON rendering
  cli.py            # command-line entry point
  checkers/
    provenance.py   # 1. data provenance
    assumption.py   # 2. assumption surfacing
    contradiction.py# 3. reverse logical deduction
    arithmetic.py   # +  arithmetic consistency
data/bad_cases.jsonl      # 30 labelled cases, 11 defect types
eval/run_eval.py          # confusion matrix + per-category hit rate
tests/                    # 97 unit tests
.github/workflows/ci.yml  # CI: tests + evaluation
```

~1,790 lines of source, ~569 lines of tests.

---

## Deliberate non-choices

These say more about the project than what it does:

| Choice | Reason |
|---|---|
| **No single "trust score"** | A 0.73 score can't guide action. Only concrete, evidence-backed issues are reported — each traceable to the source text |
| **Degrade on LLM failure, never abort** | A failed semantic check logs one INFO; deterministic conclusions still stand |
| **Small integers are not judged** | "3 stages" is a count, not a claim. Distinguished by decimal point / `%` |
| **Numeric tolerance tightened to 1e-9** | An early 0.1% relative tolerance treated `542.7` and `542.9` as equal and **missed every transcription error** — found by measurement, fixed, regression test added |
| **Skip on ambiguity rather than guess** | Multiple candidate percentages in one sentence → skipped, not guessed |

---

## Disclaimer

- An independent open-source tool. Unrelated to any internship or coursework; code and data are original.
- The dataset is **synthetic** — no real enterprise, personal, or commercial data.
- Output is a **prompt for human review**, not a final determination of correctness, and **not investment advice**.

MIT License.
