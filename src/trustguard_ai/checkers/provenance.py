"""第一重质疑：数据溯源（Provenance）。

问题：**结论里的每个数字，能不能追到出处？**

实现分层：
    - 规则层（始终启用）：数值等价比对。支持千分位、"万/亿"换算，
      因此 "1,683" 与 "1683"、"330 万" 与 "3300000" 都能匹配。
    - LLM 层（可选）：判断"数字在来源里出现过"是否等于"该来源支持这个结论"，
      例如来源说"营收 100 亿"，结论说"利润 100 亿"——数字对得上，但语义不对。
"""
from __future__ import annotations

import json
from typing import Dict, List, Sequence

from ..extract import (
    derivable_percentages,
    erroneous_percentages,
    extract_numbers,
    find_sources_for,
    is_checkable,
    numbers_equal,
)
from ..llm import LLMError, LLMProvider, extract_json
from ..models import CheckName, CheckResult, Issue, Severity, Source
from .base import BaseChecker

_LLM_PROMPT = """你是一个数据溯源审查员。请判断下面这段结论中的数字，是否被给定的来源材料真正支持。

【来源材料】
{sources}

【待审结论】
{claim}

要求：
1. 逐个检查结论中的数字；
2. 判断该数字是否被来源支持，以及「数字出现」是否等于「来源支持这个结论」；
3. 找出"数字对得上但语义不匹配"的情况（例如来源讲营收、结论讲利润）。

只输出 JSON，格式：
{{"unsupported": [{{"number": "数字原文", "reason": "为什么不被支持", "severity": "warn|error"}}]}}
若全部被支持，输出 {{"unsupported": []}}。"""


class ProvenanceChecker(BaseChecker):
    """数据溯源检查器。"""

    name = CheckName.PROVENANCE

    def check(self, claim: str, sources: Sequence[Source]) -> CheckResult:
        result = CheckResult(check=self.name)

        mentions = extract_numbers(claim)
        # 带百分比的数字一定是断言；无单位的纯数字低于阈值视为计数
        candidates = [m for m in mentions if is_checkable(m)]

        # 由文本自身算出来的百分比（如「200.0 降到 150.0，降低 25%」中的 25%）
        # 属于**派生值**，不应被当成"凭空出现的数字"。
        derived = derivable_percentages(claim)
        # 算错的变化率已由算术检查报 ERROR，此处不重复报"无出处"
        already_reported = erroneous_percentages(claim)

        if not sources:
            result.stats = {
                "numbers_total": len(mentions),
                "numbers_checkable": len(candidates),
                "sourced": 0,
                "unsourced": 0,
                "sourced_ratio": None,
            }
            result.issues.append(
                Issue(
                    check=self.name,
                    severity=Severity.INFO,
                    message="未提供来源材料，无法进行数据溯源检查",
                    detail={"numbers_total": len(mentions)},
                )
            )
            return self._result(result)

        sourced, derived_count, unsourced = 0, 0, []
        for mention in candidates:
            if find_sources_for(mention.value, sources):
                sourced += 1
            elif any(numbers_equal(mention.value, d) for d in derived):
                derived_count += 1
            elif any(numbers_equal(mention.value, v) for v in already_reported):
                derived_count += 1  # 已由算术检查报告，此处不重复计数
            else:
                unsourced.append(mention)

        result.stats = {
            "numbers_total": len(mentions),
            "numbers_checkable": len(candidates),
            "sourced": sourced,
            "derived": derived_count,
            "unsourced": len(unsourced),
            "sourced_ratio": round((sourced + derived_count) / len(candidates), 4)
            if candidates
            else None,
        }

        for mention in unsourced:
            result.issues.append(
                Issue(
                    check=self.name,
                    severity=Severity.WARN,
                    message=f"数字 {mention.raw} 在来源材料中找不到出处",
                    evidence=mention.context,
                    detail={
                        "value": mention.value,
                        "unit": mention.unit,
                        "raw": mention.raw,
                    },
                )
            )

        if self.llm_enabled:
            self._llm_pass(claim, sources, result)

        return self._result(result)

    # -- LLM 增强 --------------------------------------------------------

    def _llm_pass(self, claim: str, sources: Sequence[Source], result: CheckResult) -> None:
        source_text = "\n\n".join(f"[{s.id}] {s.text}" for s in sources)
        prompt = _LLM_PROMPT.format(sources=source_text, claim=claim)

        try:
            payload = extract_json(self.llm.complete(prompt))
        except LLMError as exc:
            result.issues.append(
                Issue(
                    check=self.name,
                    severity=Severity.INFO,
                    message=f"LLM 语义复核未完成：{exc}",
                )
            )
            return

        items = payload.get("unsupported", []) if isinstance(payload, dict) else []
        for item in items:
            severity = Severity.ERROR if item.get("severity") == "error" else Severity.WARN
            result.issues.append(
                Issue(
                    check=self.name,
                    severity=severity,
                    message=f"语义未被来源支持：{item.get('reason', '')}".strip(),
                    evidence=str(item.get("number", "")),
                    detail={"source": "llm"},
                )
            )
