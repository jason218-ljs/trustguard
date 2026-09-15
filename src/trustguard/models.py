"""TrustGuard 核心数据模型。

设计原则：**每个问题都必须可追溯**。
一次判定不能只给一个分数，而要能回答三个问题：
    哪段文本触发的？依据是什么？对应哪条规则/哪个来源？

这也是本项目的自我约束——一个用来检查"结论是否可追溯"的工具，
自己首先必须做到可追溯。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Severity(str, Enum):
    """问题严重程度。"""

    INFO = "info"    # 提示：值得注意但不影响采纳
    WARN = "warn"    # 可疑：建议人工复核
    ERROR = "error"  # 确定性问题：不应采纳


class Verdict(str, Enum):
    """整体判定。"""

    PASS = "pass"  # 未发现问题
    WARN = "warn"  # 存在可疑项，需人工复核
    FAIL = "fail"  # 存在确定性问题，不应直接采纳


class CheckName(str, Enum):
    """检查项名称。前三项即「三重质疑」。"""

    PROVENANCE = "provenance"        # 一、数据溯源
    ASSUMPTION = "assumption"        # 二、假设识别
    CONTRADICTION = "contradiction"  # 三、逻辑反向推演
    ARITHMETIC = "arithmetic"        # 附加：算术一致性（纯确定性）


# 严重度 -> 判定 的映射（用于汇总）
_SEVERITY_TO_VERDICT = {
    Severity.INFO: Verdict.PASS,
    Severity.WARN: Verdict.WARN,
    Severity.ERROR: Verdict.FAIL,
}


@dataclass(frozen=True)
class Source:
    """一条可引用的来源材料。

    Attributes:
        id: 来源标识，会在报告里回指（如 "2025-annual-report"）。
        text: 来源原文。校验时会在这段文本里查找证据。
        kind: 来源类型，便于按类型施加不同策略。
    """

    id: str
    text: str
    kind: str = "document"
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NumberMention:
    """从文本中抽取出的一个数字。"""

    raw: str            # 原始写法，如 "1,683" / "13%"
    value: float        # 归一化数值，如 1683.0 / 13.0
    start: int          # 在原文中的起始位置
    end: int            # 结束位置
    unit: str = ""      # 单位/后缀，如 "%" / "s" / "m"
    context: str = ""   # 附近文本，用于人工复核

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw": self.raw,
            "value": self.value,
            "unit": self.unit,
            "context": self.context,
        }


@dataclass(frozen=True)
class Issue:
    """一个具体问题。**必须携带证据**。"""

    check: CheckName
    severity: Severity
    message: str
    evidence: str = ""                              # 触发判定的原文片段
    detail: Dict[str, Any] = field(default_factory=dict)  # 结构化细节

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check": self.check.value,
            "severity": self.severity.value,
            "message": self.message,
            "evidence": self.evidence,
            "detail": self.detail,
        }


@dataclass
class CheckResult:
    """单项检查的结果。"""

    check: CheckName
    issues: List[Issue] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)
    note: str = ""  # 该检查的说明（如"未启用 LLM，使用规则降级实现"）

    @property
    def status(self) -> Verdict:
        """由最严重的问题决定本项判定。"""
        worst = Verdict.PASS
        for issue in self.issues:
            candidate = _SEVERITY_TO_VERDICT[issue.severity]
            if candidate == Verdict.FAIL or (
                candidate == Verdict.WARN and worst == Verdict.PASS
            ):
                worst = candidate
        return worst

    def count(self, severity: Severity) -> int:
        return sum(1 for i in self.issues if i.severity == severity)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check": self.check.value,
            "status": self.status.value,
            "note": self.note,
            "stats": self.stats,
            "issues": [i.to_dict() for i in self.issues],
        }


@dataclass
class Report:
    """一次完整的三重质疑报告。"""

    claim: str
    results: List[CheckResult] = field(default_factory=list)
    sources: List[str] = field(default_factory=list)  # 来源 id 列表
    mode: str = "rule"  # rule | llm | hybrid

    @property
    def verdict(self) -> Verdict:
        """整体判定取各项中最严重的。"""
        worst = Verdict.PASS
        for result in self.results:
            status = result.status
            if status == Verdict.FAIL:
                return Verdict.FAIL
            if status == Verdict.WARN:
                worst = Verdict.WARN
        return worst

    @property
    def all_issues(self) -> List[Issue]:
        return [i for r in self.results for i in r.issues]

    def find(self, check: CheckName) -> Optional[CheckResult]:
        for r in self.results:
            if r.check == check:
                return r
        return None

    def summary(self) -> Dict[str, Any]:
        """给评估脚本使用的扁平摘要。"""
        return {
            "verdict": self.verdict.value,
            "mode": self.mode,
            "n_issues": len(self.all_issues),
            "n_error": sum(1 for i in self.all_issues if i.severity == Severity.ERROR),
            "n_warn": sum(1 for i in self.all_issues if i.severity == Severity.WARN),
            "checks": {r.check.value: r.status.value for r in self.results},
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim": self.claim,
            "sources": self.sources,
            "mode": self.mode,
            "verdict": self.verdict.value,
            "summary": self.summary(),
            "results": [r.to_dict() for r in self.results],
        }
