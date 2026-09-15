"""报告渲染：把 Report 输出为 Markdown 或 JSON。

Markdown 报告刻意做成**可直接贴进 PR 评论或周报**的形式——
工具的输出如果没人看，就等于没有输出。
"""
from __future__ import annotations

import json
from typing import Any, Dict

from .models import Report, Severity, Verdict

_VERDICT_LABEL = {
    Verdict.PASS: "✅ PASS（未发现问题）",
    Verdict.WARN: "⚠️ WARN（存在可疑项，建议人工复核）",
    Verdict.FAIL: "❌ FAIL（存在确定性问题，不应直接采纳）",
}

_SEVERITY_ICON = {
    Severity.ERROR: "❌",
    Severity.WARN: "⚠️",
    Severity.INFO: "ℹ️",
}

_CHECK_LABEL = {
    "provenance": "一、数据溯源",
    "assumption": "二、假设识别",
    "contradiction": "三、逻辑反向推演",
    "arithmetic": "附、算术一致性",
}


def to_json(report: Report, *, indent: int = 2) -> str:
    """输出 JSON 报告（便于接入 CI / 其它工具）。"""
    return json.dumps(report.to_dict(), ensure_ascii=False, indent=indent)


def to_markdown(report: Report) -> str:
    """输出 Markdown 报告。"""
    lines = []
    lines.append("# TrustGuard 可信性报告")
    lines.append("")
    lines.append(f"**判定：{_VERDICT_LABEL[report.verdict]}**")
    lines.append("")
    lines.append(
        f"- 检查模式：`{report.mode}`"
        + ("（规则 + LLM）" if report.mode == "hybrid" else "（纯规则，未调用 LLM）")
    )
    lines.append(f"- 来源材料：{len(report.sources)} 份"
                 + (f"（{', '.join(report.sources)}）" if report.sources else ""))
    lines.append(f"- 问题总数：{len(report.all_issues)}")
    lines.append("")

    lines.append("## 待审结论")
    lines.append("")
    for para in report.claim.split("\n"):
        lines.append(f"> {para}" if para.strip() else ">")
    lines.append("")

    for result in report.results:
        label = _CHECK_LABEL.get(result.check.value, result.check.value)
        status = {Verdict.PASS: "PASS", Verdict.WARN: "WARN", Verdict.FAIL: "FAIL"}[result.status]
        lines.append(f"## {label} — {status}")
        lines.append("")

        if result.note:
            lines.append(f"_{result.note}_")
            lines.append("")

        if result.stats:
            stats = " ｜ ".join(f"{k}={v}" for k, v in result.stats.items())
            lines.append(f"统计：{stats}")
            lines.append("")

        actionable = [i for i in result.issues if i.severity != Severity.INFO]
        notes = [i for i in result.issues if i.severity == Severity.INFO]

        if not actionable and not notes:
            lines.append("未发现问题。")
            lines.append("")
            continue

        for issue in actionable:
            lines.append(f"- {_SEVERITY_ICON[issue.severity]} **{issue.message}**")
            if issue.evidence:
                lines.append(f"  - 证据：`{issue.evidence}`")
        if notes:
            lines.append("")
            lines.append("<details><summary>标注项（不构成问题，仅供人工参考）</summary>")
            lines.append("")
            for issue in notes:
                lines.append(f"- ℹ️ {issue.message}")
                if issue.evidence:
                    lines.append(f"  - 原文：`{issue.evidence}`")
            lines.append("")
            lines.append("</details>")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def to_summary_line(report: Report) -> str:
    """单行摘要，适合放进 CI 日志。"""
    return (
        f"[trustguard] verdict={report.verdict.value} "
        f"mode={report.mode} "
        f"errors={sum(1 for i in report.all_issues if i.severity == Severity.ERROR)} "
        f"warnings={sum(1 for i in report.all_issues if i.severity == Severity.WARN)}"
    )
