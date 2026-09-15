"""编排层、报告渲染、CLI 与 LLM 工具函数的测试。"""
from __future__ import annotations

import json

import pytest

from trustguard import Source, TrustGuard, build_guard, normalize_sources
from trustguard.cli import main as cli_main
from trustguard.llm import LLMError, OpenAICompatLLM, ScriptedLLM, extract_json
from trustguard.models import CheckName, Severity, Verdict
from trustguard.report import to_json, to_markdown, to_summary_line


class TestPipeline:
    def test_rule_mode_needs_no_credentials(self):
        guard = TrustGuard()
        assert guard.mode == "rule"
        assert len(guard.checkers) == 4

    def test_check_returns_report_with_all_checks(self):
        report = TrustGuard().check("收益 45.2%。", [Source(id="s", text="收益 32.4%。")])
        assert len(report.results) == 4
        assert report.find(CheckName.PROVENANCE) is not None

    def test_verdict_is_worst_of_all_checks(self):
        report = TrustGuard().check("由 200.0 降至 150.0，降低 50%。", [])
        assert report.verdict == Verdict.FAIL

    def test_clean_claim_passes(self):
        sources = [Source(id="s", text="策略年化收益 32.4%，最大回撤 12.3%。")]
        report = TrustGuard().check("策略年化收益 32.4%，最大回撤 12.3%。", sources)
        assert report.verdict == Verdict.PASS

    def test_summary_shape(self):
        report = TrustGuard().check("收益 45.2%。", [Source(id="s", text="收益 32.4%。")])
        summary = report.summary()
        assert summary["verdict"] == "warn"
        assert summary["mode"] == "rule"
        assert set(summary["checks"]) == {
            "provenance", "assumption", "contradiction", "arithmetic",
        }

    def test_check_many(self):
        reports = TrustGuard().check_many(
            [
                {"id": "a", "claim": "收益 45.2%。", "sources": [{"id": "s", "text": "收益 32.4%。"}]},
                {"id": "b", "claim": "系统稳定。", "sources": []},
            ]
        )
        assert len(reports) == 2


class TestNormalizeSources:
    def test_source_objects(self):
        result = normalize_sources([Source(id="a", text="t")])
        assert result[0].id == "a"

    def test_dicts(self):
        result = normalize_sources([{"id": "b", "text": "t"}])
        assert result[0].id == "b"

    def test_plain_strings_get_generated_ids(self):
        result = normalize_sources(["foo", "bar"])
        assert [s.id for s in result] == ["src-1", "src-2"]

    def test_none_and_empty(self):
        assert normalize_sources(None) == []
        assert normalize_sources([]) == []

    def test_missing_id_falls_back(self):
        result = normalize_sources([{"text": "t"}])
        assert result[0].id == "src-1"


class TestBuildGuard:
    def test_rule_mode(self):
        assert build_guard("rule").mode == "rule"

    def test_auto_without_credentials_degrades_to_rule(self, monkeypatch):
        monkeypatch.delenv("TRUSTGUARD_LLM_BASE_URL", raising=False)
        monkeypatch.delenv("TRUSTGUARD_LLM_API_KEY", raising=False)
        assert build_guard("auto").mode == "rule"

    def test_hybrid_without_credentials_raises(self, monkeypatch):
        monkeypatch.delenv("TRUSTGUARD_LLM_BASE_URL", raising=False)
        monkeypatch.delenv("TRUSTGUARD_LLM_API_KEY", raising=False)
        with pytest.raises(ValueError, match="需要 LLM"):
            build_guard("hybrid")

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="未知 mode"):
            build_guard("nonsense")

    def test_hybrid_with_explicit_provider(self):
        guard = build_guard("hybrid", llm=ScriptedLLM(['{"assumptions": []}']))
        assert guard.mode == "hybrid"


class TestReport:
    @pytest.fixture
    def report(self):
        return TrustGuard().check(
            "策略年化收益 45.2%。",
            [Source(id="backtest", text="策略年化收益 32.4%。")],
        )

    def test_markdown_contains_verdict(self, report):
        md = to_markdown(report)
        assert "WARN" in md
        assert "数据溯源" in md
        assert "45.2" in md

    def test_markdown_mentions_mode(self, report):
        assert "纯规则" in to_markdown(report)

    def test_json_roundtrip(self, report):
        payload = json.loads(to_json(report))
        assert payload["verdict"] == "warn"
        assert payload["sources"] == ["backtest"]

    def test_summary_line(self, report):
        line = to_summary_line(report)
        assert "verdict=warn" in line
        assert "mode=rule" in line


class TestExtractJson:
    def test_plain_json(self):
        assert extract_json('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_fenced_without_language(self):
        assert extract_json('```\n{"a": 1}\n```') == {"a": 1}

    def test_json_embedded_in_prose(self):
        assert extract_json('好的，结果如下：{"a": 1} 以上。') == {"a": 1}

    def test_array(self):
        assert extract_json("[1, 2]") == [1, 2]

    def test_invalid_raises(self):
        with pytest.raises(LLMError):
            extract_json("完全不是 JSON")


class TestScriptedLLM:
    def test_returns_in_order(self):
        llm = ScriptedLLM(["a", "b"])
        assert llm.complete("x") == "a"
        assert llm.complete("y") == "b"

    def test_exhausted_raises(self):
        llm = ScriptedLLM([])
        with pytest.raises(LLMError):
            llm.complete("x")

    def test_records_calls(self):
        llm = ScriptedLLM(["a"])
        llm.complete("prompt-1")
        assert llm.calls == ["prompt-1"]


class TestOpenAICompatLLM:
    def test_requires_base_url(self):
        with pytest.raises(LLMError, match="base_url"):
            OpenAICompatLLM(base_url="", api_key="k")

    def test_requires_api_key(self):
        with pytest.raises(LLMError, match="api_key"):
            OpenAICompatLLM(base_url="http://x", api_key="")

    def test_strips_trailing_slash(self):
        llm = OpenAICompatLLM(base_url="http://x/v1/", api_key="k")
        assert llm.base_url == "http://x/v1"


class TestCli:
    def test_demo_exits_zero(self, capsys):
        assert cli_main(["demo"]) == 0
        assert "TrustGuard" in capsys.readouterr().out

    def test_no_command_prints_help(self, capsys):
        assert cli_main([]) == 0
        assert "usage" in capsys.readouterr().out.lower()

    def test_check_with_sources(self, capsys):
        code = cli_main(["check", "--claim", "收益 45.2%。", "--source", "report=收益 32.4%。"])
        assert code == 0  # 默认 --fail-on fail，WARN 不触发
        assert "WARN" in capsys.readouterr().out

    def test_check_fail_on_warn_returns_one(self):
        code = cli_main(
            ["check", "--claim", "收益 45.2%。", "--source", "report=收益 32.4%。",
             "--fail-on", "warn"]
        )
        assert code == 1

    def test_check_fail_on_never_always_zero(self):
        code = cli_main(
            ["check", "--claim", "由 200.0 降至 150.0，降低 50%。", "--fail-on", "never"]
        )
        assert code == 0

    def test_check_json_output(self, capsys):
        cli_main(["check", "--claim", "收益 45.2%。", "--source", "s=收益 32.4%。", "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["verdict"] == "warn"

    def test_check_empty_claim_returns_two(self, capsys):
        assert cli_main(["check", "--claim", "   "]) == 2

    def test_missing_source_file_returns_two(self):
        assert cli_main(["check", "--claim", "x", "--source", "@not-exist-file.txt"]) == 2

    def test_out_writes_file(self, tmp_path, capsys):
        target = tmp_path / "report.md"
        cli_main(["check", "--claim", "收益 45.2%。", "--source", "s=收益 32.4%。",
                  "--out", str(target)])
        assert "45.2" in target.read_text(encoding="utf-8")
