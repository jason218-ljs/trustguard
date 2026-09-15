"""确定性抽取与校验层——「刚性任务交给代码」。

这一层**不调用任何 LLM**，只做可以用规则精确判定的工作：
    1. 从文本中抽取数字（含千分位、百分比、万/亿换算、日期排除）
    2. 判断一个数字能否在给定来源中找到（数值等价匹配）
    3. 校验可判定的算术关系（变化率一致性）

设计原则：**宁可漏报，不可误报**。
凡是规则无法精确判定的，一律不报问题，只记录 stats 交给上层。
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .models import Issue, NumberMention, Severity, Source, CheckName

# ---------------------------------------------------------------- 数字抽取

# 支持：1,683 / 1683 / 542.9 / -3.2 / 13% / 0.5
_NUM_RE = re.compile(
    r"(?<![\w.])"
    r"(-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?)"
    r"\s*(%|‰|％|万|亿)?"
)

# 需要在抽取前排除的日期区间（避免把 2026-09-13 拆成三个数字）
_DATE_RES = [
    re.compile(r"\d{4}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*\d{1,2}"),
    re.compile(r"\d{4}\s*年\s*\d{1,2}\s*月(?:\s*\d{1,2}\s*日)?"),
    re.compile(r"\d{4}\s*年"),
]

_SCALE = {"万": 1e4, "亿": 1e8}
_PERCENT_UNITS = {"%", "％", "‰"}

# 低于该值的「无单位纯数字」视为计数/序数（如"3 个环节""第 2 步"），不做溯源要求。
# 注意：带 % 的数字**不受此阈值限制**——百分比一定是断言。
DEFAULT_MIN_VALUE = 100.0


def is_checkable(mention: NumberMention, min_value: float = DEFAULT_MIN_VALUE) -> bool:
    """判断一个数字是否值得做溯源/一致性检查。

    三条启发式，按优先级：
        1. 带百分比单位的 → 一定是断言（32.4% 数值只有 32.4，但绝不能被阈值滤掉）
        2. **带小数点的非整数** → 视为指标而非计数
           （夏普比率 2.31 是断言；"3 个环节"是计数）
        3. 无单位的纯整数 → 低于阈值视为计数，跳过
    """
    if mention.unit in _PERCENT_UNITS:
        return True
    if abs(mention.value - round(mention.value)) > 1e-9:
        return True
    return abs(mention.value) >= min_value


def _date_spans(text: str) -> List[Tuple[int, int]]:
    spans: List[Tuple[int, int]] = []
    for rx in _DATE_RES:
        spans.extend((m.start(), m.end()) for m in rx.finditer(text))
    return spans


def _in_spans(pos: int, spans: Sequence[Tuple[int, int]]) -> bool:
    return any(start <= pos < end for start, end in spans)


def extract_numbers(text: str, context_width: int = 12) -> List[NumberMention]:
    """从文本中抽取所有数字。

    Args:
        text: 待抽取文本。
        context_width: 保留多少字符的上下文，便于人工复核。

    Returns:
        按出现顺序排列的 NumberMention 列表。
    """
    spans = _date_spans(text)
    mentions: List[NumberMention] = []

    for m in _NUM_RE.finditer(text):
        if _in_spans(m.start(), spans):
            continue

        raw_value = m.group(1).replace(",", "")
        try:
            value = float(raw_value)
        except ValueError:
            continue

        unit = m.group(2) or ""
        # 万/亿 换算成绝对值，便于与其它写法等价匹配
        if unit in _SCALE:
            value *= _SCALE[unit]
            unit = ""

        start = max(0, m.start() - context_width)
        end = min(len(text), m.end() + context_width)

        mentions.append(
            NumberMention(
                raw=m.group(0).strip(),
                value=value,
                start=m.start(),
                end=m.end(),
                unit=unit,
                context=text[start:end].replace("\n", " ").strip(),
            )
        )

    return mentions


# ---------------------------------------------------------------- 数值匹配


def _iter_source_numbers(source: Source) -> Iterable[float]:
    for mention in extract_numbers(source.text):
        yield mention.value


def numbers_equal(a: float, b: float, rel_tol: float = 1e-9, abs_tol: float = 1e-9) -> bool:
    """数值等价比较。

    容差刻意收到极小（1e-9）：两个数字要么**归一化后相同**，要么就是不同。
    早期版本用了 1e-3 的相对容差，结果把 542.7 与 542.9 判成"相等"，
    导致「转录抄错一位」这类问题全部漏检——这是实测数据暴露出来的真实缺陷。
    """
    diff = abs(a - b)
    if diff <= abs_tol:
        return True
    return diff <= max(abs(a), abs(b)) * rel_tol


def find_sources_for(value: float, sources: Sequence[Source]) -> List[str]:
    """返回包含该数值的来源 id 列表。

    采用**数值比对**而非字符串比对，因此 "1,683" 与 "1683"、
    "330 万" 与 "3300000" 都能匹配上。
    """
    hits: List[str] = []
    for source in sources:
        for candidate in _iter_source_numbers(source):
            if numbers_equal(value, candidate):
                hits.append(source.id)
                break
    return hits


def unsourced_numbers(
    claim: str,
    sources: Sequence[Source],
    ignore: Sequence[float] = (),
    min_value: float = DEFAULT_MIN_VALUE,
) -> List[NumberMention]:
    """找出在来源中找不到出处的数字。

    Args:
        claim: 待校验的结论文本。
        sources: 可引用的来源。
        ignore: 需要忽略的具体数值（如同一句里已单独处理过的）。
        min_value: 无单位纯数字的过滤阈值；带百分比的数字不受此限制。
    """
    result: List[NumberMention] = []
    for mention in extract_numbers(claim):
        if any(numbers_equal(mention.value, v) for v in ignore):
            continue
        if not is_checkable(mention, min_value):
            continue
        if not find_sources_for(mention.value, sources):
            result.append(mention)
    return result


# ---------------------------------------------------------------- 算术校验

# 数字模式（含可选的百分比单位）。单位用非捕获组，保证 findall 只返回数字本身。
_NUM_PAT = r"(-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?)(?:\s*[%％‰])?"

# 仅匹配「从/由 X ... 到/至/为 Y」这种明确结构，避免误判。
# 注意 X 后面要允许跟单位（否则 "由 40% 提升到 80%" 会因为 % 无法被填充段跨越而匹配失败）。
_RANGE_RE = re.compile(
    r"(?:从|由)\s*"
    + _NUM_PAT
    + r"[^\d]{0,12}?"
    + r"(?:到|至|为|降到|升至|优化到|优化至)\s*"
    + _NUM_PAT
)
_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[%％]")

# 变化率结构的容差：允许的百分点误差
_CHANGE_TOL_PP = 5.0


def derivable_percentages(claim: str, tol_pp: float = 1.0) -> List[float]:
    """找出**由文本自身推导得出**的百分比。

    例如「能耗由 200.0 kWh 降至 150.0 kWh，降低 25%」中的 25%：
    它没有直接出处，但可以由两个已溯源的数字算出来。

    区分「凭空出现的数字」和「由已溯源数字推导出的数字」，
    是避免把正常计算误判为幻觉的关键。
    """
    derived: List[float] = []
    for sentence in re.split(r"[。！？\n]", claim):
        ranges = _RANGE_RE.findall(sentence)
        percents = _PCT_RE.findall(sentence)
        if len(ranges) != 1 or len(percents) != 1:
            continue
        try:
            start_v = float(ranges[0][0].replace(",", ""))
            end_v = float(ranges[0][1].replace(",", ""))
            stated = float(percents[0])
        except (ValueError, IndexError, TypeError):
            continue
        if start_v == 0:
            continue
        actual = abs(end_v - start_v) / abs(start_v) * 100.0
        if abs(actual - stated) <= tol_pp:
            derived.append(stated)
    return derived


def _change_relations(claim: str) -> List[Tuple[float, float, float]]:
    """抽取可判定的「变化关系」：(起点, 终点, 声称的变化率%)。

    识别口径比较克制，只认「从/由 X … 到/至/为 Y」这种明确结构。
    对百分比的取法：先取出句中所有百分比，**剔除与区间端点重合的那些**
    （端点在句中充当边界值，不是变化率），剩下的必须恰好有一个，
    否则视为歧义，直接放弃——宁可漏报，不可误报。
    """
    relations: List[Tuple[float, float, float]] = []

    for sentence in re.split(r"[。！？\n]", claim):
        ranges = _RANGE_RE.findall(sentence)
        if len(ranges) != 1:
            continue
        try:
            start_v = float(ranges[0][0].replace(",", ""))
            end_v = float(ranges[0][1].replace(",", ""))
        except (ValueError, IndexError, TypeError):
            continue
        if start_v == 0:
            continue

        percents = []
        for raw in _PCT_RE.findall(sentence):
            try:
                percents.append(float(raw))
            except ValueError:
                continue

        extra = [
            p for p in percents
            if not (numbers_equal(p, start_v) or numbers_equal(p, end_v))
        ]
        if len(extra) != 1:
            continue

        relations.append((start_v, end_v, extra[0]))

    return relations


def derivable_percentages(claim: str, tol_pp: float = 1.0) -> List[float]:
    """找出**由文本自身推导得出**的百分比。

    例如「能耗由 200.0 kWh 降至 150.0 kWh，降低 25%」中的 25%：
    它没有直接出处，但可以由两个已溯源的数字算出来。

    区分「凭空出现的数字」和「由已溯源数字推导出的数字」，
    是避免把正常计算误判为幻觉的关键。
    """
    derived: List[float] = []
    for start_v, end_v, stated in _change_relations(claim):
        actual = abs(end_v - start_v) / abs(start_v) * 100.0
        if abs(actual - stated) <= tol_pp:
            derived.append(stated)
    return derived


def erroneous_percentages(claim: str, tolerance_pp: float = _CHANGE_TOL_PP) -> List[float]:
    """变化率**算错**的那些百分比。

    这些值已经由算术检查报了 ERROR，溯源检查不应再重复报一次"无出处"——
    同一个缺陷在报告里出现两次只会制造噪音。
    """
    bad: List[float] = []
    for start_v, end_v, stated in _change_relations(claim):
        actual = abs(end_v - start_v) / abs(start_v) * 100.0
        if abs(actual - stated) > tolerance_pp:
            bad.append(stated)
    return bad


def change_rate_issues(
    claim: str,
    tolerance_pp: float = _CHANGE_TOL_PP,
) -> List[Issue]:
    """校验「由 X 变到 Y，变化 Z%」这类表述中变化率是否算得对。

    匹配不到可判定结构时**不报任何问题**，只由 arithmetic_stats 记录。
    """
    issues: List[Issue] = []

    for start_v, end_v, stated in _change_relations(claim):
        actual = abs(end_v - start_v) / abs(start_v) * 100.0
        diff = abs(actual - stated)
        if diff <= tolerance_pp:
            continue

        issues.append(
            Issue(
                check=CheckName.ARITHMETIC,
                severity=Severity.ERROR,
                message=(
                    f"变化率与数值不自洽：由 {start_v:g} 变到 {end_v:g}，"
                    f"实际变化约 {actual:.1f}%，但文中写的是 {stated:g}%"
                ),
                evidence=f"由 {start_v:g} 变到 {end_v:g}，声称变化 {stated:g}%",
                detail={
                    "start": start_v,
                    "end": end_v,
                    "stated_pct": stated,
                    "actual_pct": round(actual, 2),
                    "diff_pp": round(diff, 2),
                },
            )
        )

    return issues


def arithmetic_stats(claim: str) -> Dict[str, int]:
    """统计可校验的算术关系数量，用于报告说明。"""
    return {"checkable_relations": len(_change_relations(claim))}
