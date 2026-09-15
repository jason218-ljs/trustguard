"""第三重质疑：逻辑反向推演（Contradiction）。

问题：**从结论倒推，会不会推出矛盾？**

规则层做三件可精确判定的事：
    1. 方向矛盾：说"提升"但数值下降，或反之；
    2. 区间矛盾：说"从 X 到 Y"但 X > Y；
    3. 疑似抄写错误：某个数字在来源里找不到，但与来源中某个数字**极为接近**
       （相对差 ≤2%）——这通常意味着转录时抄错了一位。

第 3 条故意收得很紧（2% 容差 + 仅针对无出处数字），因为它的产物是 `WARN`
而不是 `ERROR`：它的作用是**提示人工复核**，不是定罪。
"""
from __future__ import annotations

from typing import Dict, List, Sequence, Set

from ..extract import _RANGE_RE, extract_numbers, is_checkable, numbers_equal
from ..llm import LLMError, extract_json
from ..models import CheckName, CheckResult, Issue, Severity, Source
from .base import BaseChecker

_UP_WORDS = ["提升", "提高", "增加", "上升", "增长", "上调", "涨到", "升至"]
_DOWN_WORDS = ["降低", "下降", "减少", "缩短", "下调", "回落", "降到", "降至"]

_LLM_PROMPT = """你是一个逻辑审查员。请对下面这段结论做「反向推演」：假设结论成立，倒推它需要的前提，检查是否与来源材料矛盾。

【来源材料】
{sources}

【待审结论】
{claim}

要求：
1. 从结论倒推其必要前提；
2. 检查这些前提是否与来源材料冲突，或结论内部是否自相矛盾；
3. 只报告**确实存在的矛盾**，不要报告"证据不足"。

只输出 JSON：
{{"contradictions": [{{"detail": "矛盾点", "why": "为什么构成矛盾", "severity": "warn|error"}}]}}
若无矛盾，输出 {{"contradictions": []}}。"""


class ContradictionChecker(BaseChecker):
    """逻辑反向推演检查器。"""

    name = CheckName.CONTRADICTION

    def check(self, claim: str, sources: Sequence[Source]) -> CheckResult:
        result = CheckResult(check=self.name)

        direction, range_conflicts = self._rule_direction(claim)
        near_miss = self._rule_near_miss(claim, sources)

        result.issues.extend(direction)
        result.issues.extend(range_conflicts)
        result.issues.extend(near_miss)

        result.stats = {
            "direction_conflicts": len(direction),
            "range_conflicts": len(range_conflicts),
            "near_miss_suspects": len(near_miss),
        }

        if self.llm_enabled:
            self._llm_pass(claim, sources, result)

        return self._result(result)

    # -- 规则层 ----------------------------------------------------------

    def _rule_direction(self, claim: str, ) -> tuple[List[Issue], List[Issue]]:
        """方向矛盾与区间矛盾。"""
        direction: List[Issue] = []
        ranged: List[Issue] = []

        for sentence in (s.strip() for s in claim.replace("！", "。").replace("？", "。").split("。")):
            if not sentence:
                continue
            pairs = _RANGE_RE.findall(sentence)
            if len(pairs) != 1:
                continue

            raw_start, raw_end = pairs[0]
            try:
                start = float(raw_start.replace(",", ""))
                end = float(raw_end.replace(",", ""))
            except ValueError:
                continue

            ups = [w for w in _UP_WORDS if w in sentence]
            downs = [w for w in _DOWN_WORDS if w in sentence]

            direction_issue_added = False

            if start > end and ups and not downs:
                direction.append(
                    Issue(
                        check=self.name,
                        severity=Severity.ERROR,
                        message=(
                            f"方向矛盾：文中用「{'、'.join(ups)}」，"
                            f"但数值从 {raw_start} 变为 {raw_end}（实为下降）"
                        ),
                        evidence=sentence,
                        detail={"start": start, "end": end, "markers": ups},
                    )
                )
                direction_issue_added = True
            elif end > start and downs and not ups:
                direction.append(
                    Issue(
                        check=self.name,
                        severity=Severity.ERROR,
                        message=(
                            f"方向矛盾：文中用「{'、'.join(downs)}」，"
                            f"但数值从 {raw_start} 变为 {raw_end}（实为上升）"
                        ),
                        evidence=sentence,
                        detail={"start": start, "end": end, "markers": downs},
                    )
                )
                direction_issue_added = True

            # 区间颠倒只在**没有**报出方向矛盾时才报，避免同一处缺陷在报告里出现两次
            if start > end and not downs and not direction_issue_added:
                ranged.append(
                    Issue(
                        check=self.name,
                        severity=Severity.WARN,
                        message=f"区间上下界颠倒：{raw_start} → {raw_end}",
                        evidence=sentence,
                        detail={"start": start, "end": end},
                    )
                )

        return direction, ranged

    def _rule_near_miss(
        self,
        claim: str,
        sources: Sequence[Source],
        rel_tol: float = 0.02,
    ) -> List[Issue]:
        """找出「无出处、但与来源中某个数字极接近」的数字。"""
        if not sources:
            return []

        sourced: Set[float] = set()
        for source in sources:
            for mention in extract_numbers(source.text):
                sourced.add(mention.value)
        if not sourced:
            return []

        issues: List[Issue] = []
        for mention in extract_numbers(claim):
            if not is_checkable(mention):
                continue
            if any(numbers_equal(mention.value, v) for v in sourced):
                continue  # 精确命中，没问题

            closest, best_rel = None, None
            for value in sourced:
                if value == 0:
                    continue
                rel = abs(mention.value - value) / abs(value)
                if 0 < rel <= rel_tol and (best_rel is None or rel < best_rel):
                    closest, best_rel = value, rel

            if closest is not None:
                issues.append(
                    Issue(
                        check=self.name,
                        severity=Severity.WARN,
                        message=(
                            f"疑似转录错误：{mention.raw} 在来源中找不到，"
                            f"但来源中有 {closest:g}（相差 {best_rel * 100:.2f}%）"
                        ),
                        evidence=mention.context,
                        detail={
                            "claim_value": mention.value,
                            "closest_source_value": closest,
                            "rel_diff": round(best_rel, 5),
                        },
                    )
                )

        return issues

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
                    message=f"LLM 反向推演未完成：{exc}",
                )
            )
            return

        items = payload.get("contradictions", []) if isinstance(payload, dict) else []
        for item in items:
            severity = Severity.ERROR if item.get("severity") == "error" else Severity.WARN
            result.issues.append(
                Issue(
                    check=self.name,
                    severity=severity,
                    message=f"反向推演发现矛盾：{item.get('detail', '')}".strip(),
                    evidence=str(item.get("why", "")),
                    detail={"source": "llm"},
                )
            )
