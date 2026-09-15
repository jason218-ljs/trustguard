"""四个检查器的单元测试。"""
from __future__ import annotations

import pytest

from trustguard.checkers import (
    ArithmeticChecker,
    AssumptionChecker,
    ContradictionChecker,
    ProvenanceChecker,
)
from trustguard.llm import ScriptedLLM
from trustguard.models import CheckName, Severity, Source, Verdict


@pytest.fixture
def sources():
    return [
        Source(
            id="backtest",
            text="回测区间 2024-01-01 至 2026-08-31。策略年化收益 32.4%，最大回撤 12.3%。",
        )
    ]


class TestProvenanceChecker:
    def test_flags_unsourced_number(self, sources):
        result = ProvenanceChecker().check("策略年化收益 45.2%。", sources)
        assert result.status == Verdict.WARN
        assert any("45.2" in i.message for i in result.issues)

    def test_passes_when_all_sourced(self, sources):
        result = ProvenanceChecker().check("策略年化收益 32.4%，最大回撤 12.3%。", sources)
        assert result.status == Verdict.PASS

    def test_ignores_small_counts(self, sources):
        """小整数是计数，不是断言。"""
        result = ProvenanceChecker().check("流程共 3 个环节。", sources)
        assert result.status == Verdict.PASS

    def test_percentage_is_always_checked(self, sources):
        result = ProvenanceChecker().check("覆盖率 97.5%。", sources)
        assert result.status == Verdict.WARN

    def test_derived_percentage_not_flagged(self):
        """由区间两端算出的百分比是派生值，不应报无出处。"""
        sources = [Source(id="s", text="改造前能耗 200.0 kWh，改造后 150.0 kWh。")]
        result = ProvenanceChecker().check("能耗由 200.0 kWh 降至 150.0 kWh，降低 25%。", sources)
        assert result.status == Verdict.PASS
        assert result.stats["derived"] == 1

    def test_no_sources_reports_info_only(self):
        result = ProvenanceChecker().check("收益 45.2%。", [])
        assert result.status == Verdict.PASS
        assert all(i.severity == Severity.INFO for i in result.issues)
        assert result.stats["sourced_ratio"] is None

    def test_stats_shape(self, sources):
        result = ProvenanceChecker().check("收益 45.2%，回撤 12.3%。", sources)
        assert set(result.stats) >= {
            "numbers_total", "numbers_checkable", "sourced", "derived",
            "unsourced", "sourced_ratio",
        }

    def test_llm_layer_adds_semantic_issue(self, sources):
        """数字对得上但语义不匹配时，由 LLM 层补上。"""
        llm = ScriptedLLM(
            ['{"unsupported": [{"number": "32.4%", "reason": "来源讲的是营收", "severity": "warn"}]}']
        )
        result = ProvenanceChecker(llm).check("策略年化收益 32.4%。", sources)
        assert result.status == Verdict.WARN
        assert any(i.detail.get("source") == "llm" for i in result.issues)

    def test_llm_failure_degrades_gracefully(self, sources):
        """LLM 抛错时应降级为 INFO，而不是让整次检查失败。"""
        llm = ScriptedLLM([])  # 用尽即抛 LLMError
        result = ProvenanceChecker(llm).check("策略年化收益 32.4%。", sources)
        assert result.status == Verdict.PASS
        assert any("LLM" in i.message for i in result.issues)


class TestAssumptionChecker:
    def test_rule_layer_only_marks(self):
        """规则层刻意只标注不判罪——避免误报。"""
        result = AssumptionChecker().check("该因子必然长期有效。", [])
        assert result.status == Verdict.PASS
        assert result.stats["signal_absolute"] >= 1
        assert all(i.severity == Severity.INFO for i in result.issues)

    def test_detects_extrapolation_signal(self):
        result = AssumptionChecker().check("预计明年收益可达 40%。", [])
        assert result.stats["signal_extrapolation"] >= 1

    def test_detects_causal_signal(self):
        result = AssumptionChecker().check("因此该策略有效。", [])
        assert result.stats["signal_causal"] >= 1

    def test_no_signal(self):
        result = AssumptionChecker().check("系统运行稳定。", [])
        assert result.stats["signals_total"] == 0

    def test_llm_layer_raises_real_issue(self):
        llm = ScriptedLLM(
            ['{"assumptions": [{"assumption": "样本内结论可外推", '
            '"why": "来源明确写了不可外推", "severity": "error"}]}']
        )
        result = AssumptionChecker(llm).check("预计明年收益 40%。", [])
        assert result.status == Verdict.FAIL

    def test_llm_empty_result(self):
        llm = ScriptedLLM(['{"assumptions": []}'])
        result = AssumptionChecker(llm).check("系统运行稳定。", [])
        assert result.status == Verdict.PASS


class TestContradictionChecker:
    def test_direction_conflict_up(self):
        sources = [Source(id="s", text="优化前 542.9 s，优化后 270.8 s。")]
        result = ContradictionChecker().check("耗时由 542.9 s 提升至 270.8 s。", sources)
        assert result.status == Verdict.FAIL
        assert result.stats["direction_conflicts"] == 1

    def test_direction_conflict_down(self):
        sources = [Source(id="s", text="期初 8.2 次，期末 12.5 次。")]
        result = ContradictionChecker().check("周转率由 8.2 次下降至 12.5 次。", sources)
        assert result.status == Verdict.FAIL

    def test_consistent_direction_passes(self):
        sources = [Source(id="s", text="优化前 542.9 s，优化后 270.8 s。")]
        result = ContradictionChecker().check("耗时由 542.9 s 降至 270.8 s。", sources)
        assert result.status == Verdict.PASS

    def test_near_miss_typo_detected(self):
        sources = [Source(id="s", text="平均耗时 542.9 s。")]
        result = ContradictionChecker().check("平均耗时 542.7 s。", sources)
        assert result.stats["near_miss_suspects"] == 1
        assert result.status == Verdict.WARN

    def test_exact_match_is_not_near_miss(self):
        sources = [Source(id="s", text="平均耗时 542.9 s。")]
        result = ContradictionChecker().check("平均耗时 542.9 s。", sources)
        assert result.stats["near_miss_suspects"] == 0

    def test_no_sources_no_near_miss(self):
        result = ContradictionChecker().check("耗时 542.7 s。", [])
        assert result.stats["near_miss_suspects"] == 0

    def test_llm_layer(self):
        llm = ScriptedLLM(
            ['{"contradictions": [{"detail": "来源称因子已失效", '
            '"why": "结论却称表现最佳", "severity": "error"}]}']
        )
        result = ContradictionChecker(llm).check("该因子表现最佳。", [])
        assert result.status == Verdict.FAIL


class TestArithmeticChecker:
    def test_detects_mismatch(self):
        result = ArithmeticChecker().check("由 200.0 降至 150.0，降低 50%。", [])
        assert result.status == Verdict.FAIL

    def test_correct_relation_passes(self):
        result = ArithmeticChecker().check("由 200.0 降至 150.0，降低 25%。", [])
        assert result.status == Verdict.PASS

    def test_never_uses_llm(self):
        llm = ScriptedLLM(['{"contradictions": []}'])
        result = ArithmeticChecker(llm).check("系统稳定。", [])
        assert "不使用 LLM" in result.note
        assert llm.calls == []

    def test_no_relation_records_info(self):
        result = ArithmeticChecker().check("系统稳定。", [])
        assert result.stats["checkable_relations"] == 0
