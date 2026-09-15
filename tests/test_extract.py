"""确定性抽取层的单元测试。"""
from __future__ import annotations

import pytest

from trustguard.extract import (
    arithmetic_stats,
    change_rate_issues,
    derivable_percentages,
    extract_numbers,
    find_sources_for,
    is_checkable,
    numbers_equal,
)
from trustguard.models import Source, Severity


class TestExtractNumbers:
    def test_plain_integer(self):
        values = [m.value for m in extract_numbers("共 1683 个文件")]
        assert 1683.0 in values

    def test_thousands_separator(self):
        values = [m.value for m in extract_numbers("交付代码 7,131 行")]
        assert 7131.0 in values

    def test_decimal(self):
        values = [m.value for m in extract_numbers("平均 542.9 s")]
        assert 542.9 in values

    def test_percentage_keeps_unit(self):
        mentions = extract_numbers("占比 32.4%")
        pct = [m for m in mentions if m.unit == "%"]
        assert len(pct) == 1
        assert pct[0].value == 32.4

    def test_full_width_percent(self):
        mentions = extract_numbers("覆盖率 95％")
        assert any(m.unit == "％" for m in mentions)

    def test_wan_scale(self):
        values = [m.value for m in extract_numbers("参数量 720 亿")]
        assert 720e8 in values

    def test_date_excluded(self):
        """日期不应被拆成多个数字断言。"""
        values = [m.value for m in extract_numbers("截止 2026-09-13 完成")]
        assert 2026.0 not in values
        assert 9.0 not in values
        assert 13.0 not in values

    def test_chinese_date_excluded(self):
        values = [m.value for m in extract_numbers("于 2026 年 8 月完成")]
        assert 2026.0 not in values

    def test_negative_number(self):
        values = [m.value for m in extract_numbers("收益 -3.2%")]
        assert -3.2 in values

    def test_context_captured(self):
        mentions = extract_numbers("交付代码 7,131 行，其中问题一 1,683 行")
        target = [m for m in mentions if m.value == 1683.0][0]
        assert "问题一" in target.context


class TestIsCheckable:
    def test_percentage_always_checkable(self):
        """32.4% 的数值虽然小于 100，但它是断言，不能被阈值滤掉。"""
        mention = [m for m in extract_numbers("32.4%")][0]
        assert is_checkable(mention) is True

    def test_small_integer_is_count(self):
        mention = [m for m in extract_numbers("共 3 个环节")][0]
        assert is_checkable(mention) is False

    def test_large_integer_is_checkable(self):
        mention = [m for m in extract_numbers("1,683 行")][0]
        assert is_checkable(mention) is True

    def test_small_decimal_is_metric(self):
        """夏普比率 2.31 是指标，不是计数。"""
        mention = [m for m in extract_numbers("夏普比率 2.31")][0]
        assert is_checkable(mention) is True


class TestNumbersEqual:
    def test_exact_match(self):
        assert numbers_equal(1683.0, 1683.0)

    def test_near_miss_is_not_equal(self):
        """542.7 与 542.9 必须判为不同——早期容差过松导致转录错误全部漏检。"""
        assert not numbers_equal(542.7, 542.9)

    def test_float_representation(self):
        assert numbers_equal(0.1 + 0.2, 0.3)


class TestFindSources:
    def test_numeric_equivalence(self):
        """千分位写法不同也应匹配。"""
        sources = [Source(id="s1", text="交付代码 7131 行")]
        assert find_sources_for(7131.0, sources) == ["s1"]

    def test_scale_equivalence(self):
        """3300000 与 330 万 应匹配。"""
        sources = [Source(id="s1", text="共 330 万条")]
        assert find_sources_for(3_300_000.0, sources) == ["s1"]

    def test_not_found(self):
        sources = [Source(id="s1", text="收益 32.4%")]
        assert find_sources_for(45.2, sources) == []


class TestChangeRate:
    def test_detects_arithmetic_error(self):
        issues = change_rate_issues("能耗由 200.0 降至 150.0，降低 50%。")
        assert len(issues) == 1
        assert issues[0].severity == Severity.ERROR

    def test_correct_rate_passes(self):
        assert change_rate_issues("能耗由 200.0 降至 150.0，降低 25%。") == []

    def test_percent_with_unit_on_start(self):
        """起点带 % 也要能匹配（早期正则会因 % 跨越失败）。"""
        issues = change_rate_issues("命中率由 40% 提升到 80%，提升了 30%。")
        assert len(issues) == 1
        assert issues[0].detail["actual_pct"] == pytest.approx(100.0)

    def test_ambiguous_case_skipped(self):
        """变化率与端点重合时视为歧义，不报问题。"""
        assert change_rate_issues("命中率由 40% 提升到 80%，提升了 40%。") == []

    def test_no_relation_no_issue(self):
        assert change_rate_issues("系统运行稳定。") == []

    def test_stats_counts_relations(self):
        assert arithmetic_stats("由 10 到 20，提升了 100%。")["checkable_relations"] == 1


class TestDerivablePercentages:
    def test_recognizes_derived_value(self):
        """由 200 和 150 算出来的 25%，属于派生值而非幻觉。"""
        assert derivable_percentages("能耗由 200.0 降至 150.0，降低 25%。") == [25.0]

    def test_wrong_value_is_not_derived(self):
        assert derivable_percentages("能耗由 200.0 降至 150.0，降低 50%。") == []
