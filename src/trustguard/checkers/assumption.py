"""第二重质疑：假设识别（Assumption）。

问题：**这个结论依赖哪些没有说明的假设？**

设计取舍（重要）：
    规则层**只标注、不判罪**——命中外推/绝对化/因果信号词时产生 `INFO` 级问题，
    把"这里有隐含假设"这件事显式暴露出来，但不判定它是否构成实质问题。
    真正的判定交给 LLM 层或人工。

    原因：规则无法判断一个假设是否「实质且未被来源支持」。
    与其制造误报，不如诚实降级——**宁可漏报，不可误报**。

    这带来一个可量化的结论：纯规则模式下本项检查的召回率天然偏低，
    接入 LLM 后显著提升。评估脚本会分别报告两种模式的指标。
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Sequence

from ..llm import LLMError, extract_json
from ..models import CheckName, CheckResult, Issue, Severity, Source
from .base import BaseChecker

# 信号词表：不是因为它们"错"，而是因为用它们的地方往往藏着未言明的假设
_SIGNALS: Dict[str, List[str]] = {
    "extrapolation": [  # 外推假设：用过去推未来
        "预计", "预测", "预期", "未来", "有望", "将会", "目标是", "估计", "假设",
        "should reach", "will reach", "forecast", "projected", "expect",
    ],
    "absolute": [  # 绝对化假设：把有条件成立说成普遍成立
        "必然", "一定", "所有", "完全", "毫无", "绝对", "肯定", "从不", "永远",
        "always", "never", "all of", "guaranteed",
    ],
    "causal": [  # 因果假设：把相关性当作因果
        "因此", "所以", "导致", "说明", "表明", "证明了", "可见",
        "therefore", "proves", "causes", "because of",
    ],
}

_LABEL = {
    "extrapolation": "外推假设（以过去/样本推未来/总体）",
    "absolute": "绝对化假设（把有条件成立说成普遍成立）",
    "causal": "因果假设（可能把相关性当作因果）",
}

_LLM_PROMPT = """你是一个论证审查员。请找出下面这段结论所依赖的、**没有明说**的关键假设。

【来源材料】
{sources}

【待审结论】
{claim}

要求：
1. 只列出「实质性的、且不被来源材料支持的」假设，不要列常识或定义；
2. 若某条假设其实被来源支持，不要列出；
3. 每条给出：假设内容、为什么它是未言明的、严重程度。

只输出 JSON：
{{"assumptions": [{{"assumption": "假设内容", "why": "为什么未言明且重要", "severity": "warn|error"}}]}}
若没有实质假设，输出 {{"assumptions": []}}。"""


class AssumptionChecker(BaseChecker):
    """假设识别检查器。"""

    name = CheckName.ASSUMPTION

    def check(self, claim: str, sources: Sequence[Source]) -> CheckResult:
        result = CheckResult(check=self.name)
        sentences = [s.strip() for s in re.split(r"[。！？\n]", claim) if s.strip()]

        counts: Dict[str, int] = {}
        for kind, words in _SIGNALS.items():
            hits = 0
            for sentence in sentences:
                matched = [w for w in words if w in sentence]
                if not matched:
                    continue
                hits += 1
                result.issues.append(
                    Issue(
                        check=self.name,
                        severity=Severity.INFO,  # 只标注，不判罪
                        message=f"此处可能存在{_LABEL[kind]}：{'、'.join(matched)}",
                        evidence=sentence,
                        detail={"signal": kind, "words": matched},
                    )
                )
            counts[kind] = hits

        result.stats = {
            **{f"signal_{k}": v for k, v in counts.items()},
            "signals_total": sum(counts.values()),
            "rule_layer_note": "规则层仅标注疑似假设，实质判定需 LLM 或人工",
        }

        if self.llm_enabled:
            self._llm_pass(claim, sources, result)

        return self._result(result)

    # -- LLM 增强 --------------------------------------------------------

    def _llm_pass(self, claim: str, sources: Sequence[Source], result: CheckResult) -> None:
        source_text = "\n\n".join(f"[{s.id}] {s.text}" for s in sources) or "（未提供来源）"
        prompt = _LLM_PROMPT.format(sources=source_text, claim=claim)

        try:
            payload = extract_json(self.llm.complete(prompt))
        except LLMError as exc:
            result.issues.append(
                Issue(
                    check=self.name,
                    severity=Severity.INFO,
                    message=f"LLM 假设识别未完成：{exc}",
                )
            )
            return

        items = payload.get("assumptions", []) if isinstance(payload, dict) else []
        for item in items:
            severity = Severity.ERROR if item.get("severity") == "error" else Severity.WARN
            result.issues.append(
                Issue(
                    check=self.name,
                    severity=severity,
                    message=f"未言明的假设：{item.get('assumption', '')}".strip(),
                    evidence=str(item.get("why", "")),
                    detail={"source": "llm"},
                )
            )
