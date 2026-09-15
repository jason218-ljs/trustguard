#!/usr/bin/env python3
"""TrustGuard 评估脚本。

在一份人工标注的 bad-case 数据集上度量检查器的实际效果。

指标定义：
    拦截率 (recall)   应被拦截的样本中，实际被拦截的比例
    误报率 (FPR)      不应被拦截的样本中，被误拦截的比例
    精确率 (precision) 拦截结果中，判对了的比例
    F1                precision 与 recall 的调和平均

判定口径：报告的 verdict 为 WARN 或 FAIL 即视为「已拦截」。

用法：
    python eval/run_eval.py                     # 默认纯规则模式
    python eval/run_eval.py --mode auto         # 有 LLM 凭据则用 hybrid
    python eval/run_eval.py --mode rule --show-misses
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from trustguard import Source, TrustGuard, build_guard  # noqa: E402
from trustguard.models import Verdict  # noqa: E402

DEFAULT_CASES = ROOT / "data" / "bad_cases.jsonl"

FLAGGED = {Verdict.WARN, Verdict.FAIL}


def load_cases(path: Path) -> List[Dict]:
    cases: List[Dict] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path.name} 第 {line_no} 行不是合法 JSON：{exc}")
    return cases


def evaluate(guard: TrustGuard, cases: List[Dict]) -> Tuple[Dict, List[Dict]]:
    tp = fp = tn = fn = 0
    details: List[Dict] = []
    per_type: Dict[str, Dict[str, int]] = {}

    for case in cases:
        sources = [Source(id=s["id"], text=s["text"]) for s in case.get("sources", [])]
        report = guard.check(case.get("claim", ""), sources)

        flagged = report.verdict in FLAGGED
        should = bool(case.get("should_flag"))

        if should and flagged:
            tp += 1
            outcome = "TP"
        elif should and not flagged:
            fn += 1
            outcome = "FN"
        elif not should and flagged:
            fp += 1
            outcome = "FP"
        else:
            tn += 1
            outcome = "TN"

        ctype = case.get("type", "unknown")
        bucket = per_type.setdefault(ctype, {"n": 0, "flagged": 0, "should_flag": 0})
        bucket["n"] += 1
        bucket["flagged"] += int(flagged)
        bucket["should_flag"] += int(should)

        details.append(
            {
                "id": case.get("id"),
                "type": ctype,
                "should_flag": should,
                "flagged": flagged,
                "outcome": outcome,
                "verdict": report.verdict.value,
                "n_issues": len(report.all_issues),
                "messages": [i.message for i in report.all_issues if i.severity.value != "info"],
            }
        )

    total = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    accuracy = (tp + tn) / total if total else 0.0

    metrics = {
        "mode": guard.mode,
        "total": total,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "fpr": round(fpr, 4),
        "accuracy": round(accuracy, 4),
        "per_type": per_type,
    }
    return metrics, details


def render(metrics: Dict, details: List[Dict], show_misses: bool) -> str:
    lines = []
    lines.append("=" * 62)
    lines.append(f" TrustGuard 评估结果（mode = {metrics['mode']}）")
    lines.append("=" * 62)
    lines.append("")

    lines.append("混淆矩阵")
    lines.append(f"  真阳 TP = {metrics['tp']:<4} 假阳 FP = {metrics['fp']}")
    lines.append(f"  假阴 FN = {metrics['fn']:<4} 真阴 TN = {metrics['tn']}")
    lines.append("")

    lines.append("核心指标")
    lines.append(f"  拦截率 Recall     = {metrics['recall']:.1%}   （应拦的拦住了多少）")
    lines.append(f"  误报率 FPR        = {metrics['fpr']:.1%}   （不该拦的误拦了多少）")
    lines.append(f"  精确率 Precision  = {metrics['precision']:.1%}")
    lines.append(f"  F1                = {metrics['f1']:.1%}")
    lines.append(f"  准确率 Accuracy   = {metrics['accuracy']:.1%}")
    lines.append("")

    lines.append("按缺陷类型拆分")
    lines.append(f"  {'type':<28}{'样本':>5}{'应拦':>6}{'实拦':>6}  命中率")
    for ctype, b in sorted(metrics["per_type"].items()):
        should = b["should_flag"]
        rate = f"{b['flagged'] / should:.0%}" if should else "—"
        lines.append(f"  {ctype:<28}{b['n']:>5}{should:>6}{b['flagged']:>6}  {rate}")
    lines.append("")

    if show_misses:
        misses = [d for d in details if d["outcome"] in ("FN", "FP")]
        if misses:
            lines.append("漏报 / 误报明细")
            for d in misses:
                tag = "漏报" if d["outcome"] == "FN" else "误报"
                lines.append(f"  [{tag}] {d['id']} ({d['type']}) verdict={d['verdict']}")
                if d["messages"]:
                    lines.append(f"          {d['messages'][0][:70]}")
            lines.append("")
        else:
            lines.append("无漏报 / 误报。")
            lines.append("")

    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="TrustGuard 评估")
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="数据集路径（JSONL）")
    parser.add_argument(
        "--mode", default="rule", choices=["rule", "auto", "hybrid", "llm"],
        help="检查模式；rule=纯规则（默认，无需凭据）",
    )
    parser.add_argument("--show-misses", action="store_true", help="列出漏报与误报明细")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出指标")
    args = parser.parse_args(argv)

    cases = load_cases(Path(args.cases))
    if not cases:
        print("数据集为空", file=sys.stderr)
        return 2

    guard = build_guard(args.mode)
    metrics, details = evaluate(guard, cases)

    if args.json:
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    else:
        print(render(metrics, details, args.show_misses))

    return 0


if __name__ == "__main__":
    sys.exit(main())
