"""编排层：把三重质疑串成一次完整的可信性检查。

    输入：一段结论（claim） + 可选的来源材料（sources）
    输出：一份报告（Report），含整体判定与逐项问题

整体判定规则（保守）：
    - 任一项判定为 FAIL  → 整体 FAIL（存在确定性问题，不应直接采纳）
    - 任一项判定为 WARN  → 整体 WARN（存在可疑项，建议人工复核）
    - 全部 PASS          → 整体 PASS
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Union

from .checkers import (
    ArithmeticChecker,
    AssumptionChecker,
    ContradictionChecker,
    ProvenanceChecker,
)
from .llm import LLMProvider, provider_from_env
from .models import Report, Source

SourceLike = Union[Source, Dict[str, str], str]


def normalize_sources(sources: Optional[Sequence[SourceLike]]) -> List[Source]:
    """把多种写法统一成 Source 列表。

    允许的写法：
        - Source 对象
        - {"id": "...", "text": "..."}
        - 纯字符串（自动生成 id: src-1, src-2, ...）
    """
    if not sources:
        return []

    normalized: List[Source] = []
    for idx, item in enumerate(sources, start=1):
        if isinstance(item, Source):
            normalized.append(item)
        elif isinstance(item, dict):
            normalized.append(
                Source(
                    id=str(item.get("id") or f"src-{idx}"),
                    text=str(item.get("text", "")),
                    kind=str(item.get("kind", "document")),
                )
            )
        else:
            normalized.append(Source(id=f"src-{idx}", text=str(item)))
    return normalized


class TrustGuard:
    """三重质疑可信性检查器。

    Example:
        guard = TrustGuard()                      # 纯规则，离线可用
        report = guard.check(claim, sources)
        print(report.verdict)
    """

    def __init__(self, llm: Optional[LLMProvider] = None):
        self.llm = llm
        self.checkers = [
            ProvenanceChecker(llm),
            AssumptionChecker(llm),
            ContradictionChecker(llm),
            ArithmeticChecker(llm),
        ]

    @property
    def mode(self) -> str:
        return "hybrid" if self.llm is not None else "rule"

    def check(
        self,
        claim: str,
        sources: Optional[Sequence[SourceLike]] = None,
    ) -> Report:
        """对一条结论执行三重质疑。"""
        normalized = normalize_sources(sources)

        report = Report(
            claim=claim,
            sources=[s.id for s in normalized],
            mode=self.mode,
        )
        for checker in self.checkers:
            report.results.append(checker.check(claim, normalized))

        return report

    def check_many(self, cases: Sequence[Dict]) -> List[Report]:
        """批量检查，便于评估脚本使用。

        每个 case 形如：
            {"id": "...", "claim": "...", "sources": [...]}
        """
        reports: List[Report] = []
        for case in cases:
            reports.append(self.check(case.get("claim", ""), case.get("sources")))
        return reports


def build_guard(mode: str = "auto", **kwargs) -> TrustGuard:
    """按名称构造 guard。

    Args:
        mode:
            "rule"  -> 纯规则，不调用 LLM（默认，离线可跑）
            "hybrid"/"llm" -> 需要 LLM，凭据从环境变量读取
            "auto"  -> 环境变量齐全则用 hybrid，否则降级为 rule
    """
    if mode == "rule":
        return TrustGuard(llm=None)

    if mode == "auto":
        provider = provider_from_env()
        return TrustGuard(llm=provider)

    if mode in ("hybrid", "llm"):
        provider = kwargs.get("llm") or provider_from_env()
        if provider is None:
            raise ValueError(
                f"mode={mode} 需要 LLM，但未提供 provider，"
                "也未检测到环境变量 TRUSTGUARD_LLM_BASE_URL / TRUSTGUARD_LLM_API_KEY"
            )
        return TrustGuard(llm=provider)

    raise ValueError(f"未知 mode：{mode}（可选：auto / rule / hybrid / llm）")
