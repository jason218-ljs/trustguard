"""附加检查：算术一致性（纯确定性）。

这是唯一一个**完全不用 LLM、也完全不需要来源材料**的检查——
它只验证文本自身的算术自洽性。

目前覆盖：「由 X 变到 Y，变化 Z%」这类表述中变化率是否算得对。
这类错误很常见（尤其是手写或模型生成的报告），而且**可以被精确判定**，
因此放在确定性层最合适。

匹配不到可判定结构时**不报任何问题**，只记录 stats。
"""
from __future__ import annotations

from typing import Sequence

from ..extract import arithmetic_stats, change_rate_issues
from ..models import CheckName, CheckResult, Severity, Source, Issue
from .base import BaseChecker


class ArithmeticChecker(BaseChecker):
    """算术一致性检查器。"""

    name = CheckName.ARITHMETIC

    def check(self, claim: str, sources: Sequence[Source]) -> CheckResult:
        result = CheckResult(check=self.name)

        issues = change_rate_issues(claim)
        result.issues.extend(issues)
        result.stats = {
            **arithmetic_stats(claim),
            "mismatches": len(issues),
        }

        if not issues and result.stats["checkable_relations"] == 0:
            result.issues.append(
                Issue(
                    check=self.name,
                    severity=Severity.INFO,
                    message="未发现可判定的算术关系，跳过算术校验",
                )
            )

        # 算术校验是纯确定性的，接不接 LLM 都一样
        result.note = "纯确定性检查，不使用 LLM"
        return result
