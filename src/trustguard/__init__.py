"""TrustGuard —— LLM Agent 输出的可信性检查器。

三重质疑机制（把"人机边界协议"落到可执行的代码上）：

    一、数据溯源      结论里的每个数字，能不能追到出处？
    二、假设识别      这个结论依赖哪些没有说明的假设？
    三、逻辑反向推演  从结论倒推，会不会推出矛盾？

快速开始：
    >>> from trustguard import TrustGuard, Source
    >>> guard = TrustGuard()                      # 纯规则，离线可用，无需 API key
    >>> report = guard.check(
    ...     "组合年化收益 32.4%，预计明年可达 40%。",
    ...     [Source(id="report", text="回测显示组合年化收益 32.4%。")],
    ... )
    >>> report.verdict.value
    'warn'
"""
from .models import (
    CheckName,
    CheckResult,
    Issue,
    NumberMention,
    Report,
    Severity,
    Source,
    Verdict,
)
from .pipeline import TrustGuard, build_guard, normalize_sources
from .report import to_json, to_markdown, to_summary_line

__version__ = "0.1.0"

__all__ = [
    "TrustGuard",
    "build_guard",
    "normalize_sources",
    "Source",
    "Severity",
    "Verdict",
    "CheckName",
    "Issue",
    "CheckResult",
    "Report",
    "NumberMention",
    "to_json",
    "to_markdown",
    "to_summary_line",
    "__version__",
]
