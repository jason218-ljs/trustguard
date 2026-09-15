#!/usr/bin/env python3
"""TrustGuard 示例：一个真实的"AI 分析师报告"审查场景。

场景设定：
    某 Agent 基于一份回测报告和一份方法论说明，生成了投资结论。
    我们用三重质疑检查这份结论能否被采纳。

运行：
    python examples/demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from trustguard import Source, TrustGuard  # noqa: E402
from trustguard.report import to_markdown  # noqa: E402

# ---------------------------------------------------------------- 场景数据

SOURCES = [
    Source(
        id="backtest-report",
        text=(
            "回测区间 2024-01-01 至 2026-08-31，样本共 214 个交易日。"
            "策略年化收益 32.4%，基准（沪深300）年化收益 8.1%，最大回撤 12.3%。"
            "报告同时指出：因子在 2025 年二季度出现明显失效，"
            "同期最大回撤扩大至 21.7%。"
        ),
    ),
    Source(
        id="methodology",
        text=(
            "本回测为样本内检验，未做样本外验证，未建模交易摩擦，"
            "也未考虑幸存者偏差。结论不可外推至未来收益。"
        ),
    ),
]

CASES = [
    (
        "① 数字被放大（幻觉）",
        "本策略年化收益 45.2%，显著跑赢基准 8.1%。",
    ),
    (
        "② 抄错一位（转录错误）",
        "策略年化收益 32.4%，最大回撤 12.1%。",
    ),
    (
        "③ 方向写反（矛盾）",
        "优化后最大回撤由 21.7% 提升至 12.3%，风控效果显著。",
    ),
    (
        "④ 算术算错",
        "回撤由 21.7% 降至 12.3%，降低 50%。",
    ),
    (
        "⑤ 样本内外推 + 绝对化（需语义理解）",
        "该因子体系在所有市场环境下必然有效，明年将继续保持 32.4% 的收益。",
    ),
    (
        "⑥ 干净结论（不应误报）",
        "样本内回测显示，策略年化收益 32.4%，基准年化收益 8.1%，最大回撤 12.3%。",
    ),
]


def main() -> int:
    guard = TrustGuard()  # 纯规则模式，无需任何 API key

    print("=" * 72)
    print(" TrustGuard 示例：审查一份 AI 生成的投研结论")
    print(f" 检查模式：{guard.mode}（纯规则，离线运行，未调用任何 LLM）")
    print("=" * 72)

    for title, claim in CASES:
        report = guard.check(claim, SOURCES)
        actionable = [i for i in report.all_issues if i.severity.value != "info"]

        print()
        print("-" * 72)
        print(f" {title}")
        print(f" 结论：{claim}")
        print(f" 判定：{report.verdict.value.upper()}")
        if actionable:
            for issue in actionable:
                print(f"   [{issue.severity.value}] {issue.message}")
        else:
            print("   未发现问题")

    print()
    print("=" * 72)
    print(" 说明：⑤ 类需要语义理解的缺陷在纯规则模式下无法检出——")
    print("       这正是接入 LLM 的意义（见 README 的实测结果一节）。")
    print("=" * 72)

    # 另附一份完整的 Markdown 报告，展示输出形态
    detailed = guard.check(CASES[0][1], SOURCES)
    print()
    print(to_markdown(detailed))

    return 0


if __name__ == "__main__":
    sys.exit(main())
