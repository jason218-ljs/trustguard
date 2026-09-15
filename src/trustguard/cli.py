"""命令行入口。

    trustguard check --claim "..." --source a.txt --source b.txt
    trustguard check --claim @claim.md --source @data.txt --json
    trustguard demo

退出码：
    0  判定未达到 --fail-on 阈值
    1  判定达到阈值（便于接入 CI 卡点）
    2  用法或运行错误
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from .models import Report, Source, Verdict
from .pipeline import TrustGuard, build_guard
from .report import to_json, to_markdown, to_summary_line

_THRESHOLD = {
    "never": 99,
    "warn": 1,
    "fail": 2,
}
_VERDICT_RANK = {Verdict.PASS: 0, Verdict.WARN: 1, Verdict.FAIL: 2}

_DEMO_CLAIM = """本季度组合取得显著超额收益：AlphaForge 系统选出的标的组合年化收益 32.4%，
显著高于基准 8.1%，说明该因子体系在 A 股市场长期有效，预计明年收益可达 40% 以上。"""

_DEMO_SOURCES = [
    Source(
        id="backtest-report",
        text=(
            "回测区间 2024-01-01 至 2026-08-31。组合年化收益 32.4%，"
            "基准（沪深300）年化收益 8.1%。样本内共 214 个交易日。"
            "报告同时指出：因子在 2025 年二季度出现明显失效，"
            "区间最大回撤 21.7%。"
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


def _read_text_arg(value: str) -> str:
    """支持 `@文件名` 从文件读取。"""
    if value.startswith("@"):
        path = Path(value[1:])
        if not path.exists():
            raise ValueError(f"文件不存在：{path}")
        return path.read_text(encoding="utf-8")
    return value


def _build_sources(paths: Sequence[str]) -> List[Source]:
    sources: List[Source] = []
    for idx, raw in enumerate(paths, start=1):
        if raw.startswith("@"):
            path = Path(raw[1:])
            if not path.exists():
                raise ValueError(f"来源文件不存在：{path}")
            sources.append(
                Source(id=path.stem or f"src-{idx}", text=path.read_text(encoding="utf-8"))
            )
        elif "=" in raw:
            name, text = raw.split("=", 1)
            sources.append(Source(id=name.strip() or f"src-{idx}", text=text.strip()))
        else:
            sources.append(Source(id=f"src-{idx}", text=raw))
    return sources


def _cmd_check(args: argparse.Namespace) -> int:
    claim = _read_text_arg(args.claim) if args.claim else sys.stdin.read()
    if not claim.strip():
        print("错误：未提供结论文本", file=sys.stderr)
        return 2

    sources = _build_sources(args.source or [])
    guard = build_guard(args.mode)
    report = guard.check(claim, sources)

    output = to_json(report) if args.json else to_markdown(report)

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        print(f"报告已写入 {args.out}")
    else:
        print(output)

    print(to_summary_line(report), file=sys.stderr)

    return 1 if _VERDICT_RANK[report.verdict] >= _THRESHOLD[args.fail_on] else 0


def _cmd_demo(args: argparse.Namespace) -> int:
    guard = TrustGuard()  # 纯规则，无需任何凭据
    report = guard.check(_DEMO_CLAIM, _DEMO_SOURCES)
    print(to_markdown(report))
    print(to_summary_line(report), file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trustguard",
        description="LLM Agent 输出的可信性检查器——三重质疑：数据溯源 / 假设识别 / 逻辑反向推演",
    )
    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check", help="对一段结论执行三重质疑")
    check.add_argument("--claim", "-c", help="结论文本；用 @文件名 可从文件读取；省略则读 stdin")
    check.add_argument(
        "--source", "-s", action="append", default=[],
        help="来源材料：@文件名 / id=文本 / 直接文本；可重复",
    )
    check.add_argument(
        "--mode", default="auto", choices=["auto", "rule", "hybrid", "llm"],
        help="auto=有凭据则用 LLM，否则纯规则（默认）",
    )
    check.add_argument("--json", action="store_true", help="输出 JSON 而非 Markdown")
    check.add_argument("--out", help="把报告写入文件")
    check.add_argument(
        "--fail-on", default="fail", choices=["never", "warn", "fail"],
        help="判定达到该级别时以退出码 1 结束（便于 CI 卡点）",
    )
    check.set_defaults(func=_cmd_check)

    demo = sub.add_parser("demo", help="跑一个内置示例（无需任何配置）")
    demo.set_defaults(func=_cmd_demo)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not getattr(args, "command", None):
        parser.print_help()
        return 0

    try:
        return args.func(args)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
