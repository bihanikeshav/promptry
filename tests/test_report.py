"""Tests for HTML report generation."""
import pytest
from typer.testing import CliRunner

from promptry.report import render_run_report, render_compare_report


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def run_results():
    """Minimal run results dict matching SuiteResult shape."""
    return {
        "suite_name": "smoke-test",
        "overall_pass": True,
        "overall_score": 0.875,
        "tests": [
            {
                "test_name": "test_basic_quality",
                "passed": True,
                "latency_ms": 123.4,
                "error": None,
                "assertions": [
                    {
                        "assertion_type": "semantic",
                        "passed": True,
                        "score": 0.875,
                    },
                ],
            },
        ],
    }


@pytest.fixture
def run_results_failing():
    """Run results with a failing test."""
    return {
        "suite_name": "rag-qa",
        "overall_pass": False,
        "overall_score": 0.420,
        "tests": [
            {
                "test_name": "test_rag_quality",
                "passed": False,
                "latency_ms": 250.0,
                "error": "Score below threshold",
                "assertions": [
                    {
                        "assertion_type": "semantic",
                        "passed": False,
                        "score": 0.420,
                    },
                    {
                        "assertion_type": "contains",
                        "passed": True,
                        "score": None,
                    },
                ],
            },
        ],
    }


@pytest.fixture
def compare_data():
    """Minimal comparison dict matching ModelCompareReport shape."""
    return {
        "suite_name": "smoke-test",
        "baseline": {
            "model_version": "gpt-4o",
            "run_count": 10,
            "overall_mean": 0.850,
            "overall_std": 0.030,
            "overall_min": 0.800,
            "overall_max": 0.900,
            "avg_cost_per_call": 0.003,
        },
        "candidate": {
            "model_version": "claude-sonnet-4",
            "run_count": 5,
            "overall_mean": 0.920,
            "overall_std": 0.020,
            "overall_min": 0.890,
            "overall_max": 0.950,
            "avg_cost_per_call": 0.002,
        },
        "overall_delta": 0.070,
        "percentile": 95.0,
        "assertion_comparisons": [
            {
                "assertion_type": "semantic",
                "baseline_mean": 0.850,
                "baseline_std": 0.030,
                "candidate_score": 0.920,
                "delta": 0.070,
                "verdict": "better",
            },
        ],
        "cost_ratio": 0.667,
        "score_per_dollar_baseline": 283.0,
        "score_per_dollar_candidate": 460.0,
        "verdict": "switch",
        "verdict_reason": "Candidate scores +0.070 higher. Also 33% cheaper.",
    }


@pytest.fixture
def compare_data_keep():
    """Comparison where baseline wins."""
    return {
        "suite_name": "rag-qa",
        "baseline": {
            "model_version": "gpt-4o",
            "run_count": 10,
            "overall_mean": 0.900,
            "overall_std": 0.020,
            "overall_min": 0.870,
            "overall_max": 0.930,
            "avg_cost_per_call": 0.0,
        },
        "candidate": {
            "model_version": "bad-model",
            "run_count": 3,
            "overall_mean": 0.600,
            "overall_std": 0.050,
            "overall_min": 0.550,
            "overall_max": 0.650,
            "avg_cost_per_call": 0.0,
        },
        "overall_delta": -0.300,
        "percentile": 5.0,
        "assertion_comparisons": [],
        "cost_ratio": None,
        "score_per_dollar_baseline": None,
        "score_per_dollar_candidate": None,
        "verdict": "keep_baseline",
        "verdict_reason": "Candidate scores -0.300 lower.",
    }


# ---------------------------------------------------------------------------
# render_run_report
# ---------------------------------------------------------------------------

class TestRenderRunReport:

    def test_returns_valid_html(self, run_results):
        html = render_run_report(run_results)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_contains_suite_name(self, run_results):
        html = render_run_report(run_results)
        assert "smoke-test" in html

    def test_contains_pass_status(self, run_results):
        html = render_run_report(run_results)
        assert "PASS" in html

    def test_contains_score(self, run_results):
        html = render_run_report(run_results)
        assert "0.875" in html

    def test_contains_test_name(self, run_results):
        html = render_run_report(run_results)
        assert "test_basic_quality" in html

    def test_contains_assertion_type(self, run_results):
        html = render_run_report(run_results)
        assert "semantic" in html

    def test_failing_run_shows_fail(self, run_results_failing):
        html = render_run_report(run_results_failing)
        assert "FAIL" in html
        assert "Score below threshold" in html

    def test_dark_theme_colours(self, run_results):
        html = render_run_report(run_results)
        assert "#111113" in html
        assert "#1a1a1e" in html
        assert "#fb923c" in html

    def test_self_contained_no_external(self, run_results):
        html = render_run_report(run_results)
        assert "<style>" in html
        # no external stylesheet links
        assert "link rel=" not in html.lower()
        assert "script src=" not in html.lower()

    def test_contains_timestamp(self, run_results):
        html = render_run_report(run_results)
        assert "Generated by promptry" in html

    def test_empty_tests_list(self):
        html = render_run_report({
            "suite_name": "empty",
            "overall_pass": True,
            "overall_score": 0.0,
            "tests": [],
        })
        assert "<!DOCTYPE html>" in html
        assert "empty" in html

    def test_assertion_with_none_score(self, run_results_failing):
        html = render_run_report(run_results_failing)
        # The contains assertion has score=None; should render as "-"
        assert "-" in html

    def test_html_escaping(self):
        """Special characters in names should be escaped."""
        html = render_run_report({
            "suite_name": "<script>alert('xss')</script>",
            "overall_pass": True,
            "overall_score": 1.0,
            "tests": [],
        })
        assert "<script>" not in html
        assert "&lt;script&gt;" in html


# ---------------------------------------------------------------------------
# render_compare_report
# ---------------------------------------------------------------------------

class TestRenderCompareReport:

    def test_returns_valid_html(self, compare_data):
        html = render_compare_report(compare_data)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_contains_model_names(self, compare_data):
        html = render_compare_report(compare_data)
        assert "gpt-4o" in html
        assert "claude-sonnet-4" in html

    def test_contains_scores(self, compare_data):
        html = render_compare_report(compare_data)
        assert "0.850" in html
        assert "0.920" in html

    def test_contains_verdict_switch(self, compare_data):
        html = render_compare_report(compare_data)
        assert "SWITCH" in html

    def test_contains_verdict_keep(self, compare_data_keep):
        html = render_compare_report(compare_data_keep)
        assert "KEEP BASELINE" in html

    def test_contains_assertion_comparison(self, compare_data):
        html = render_compare_report(compare_data)
        assert "semantic" in html
        assert "better" in html

    def test_contains_cost_analysis(self, compare_data):
        html = render_compare_report(compare_data)
        assert "Cost" in html
        assert "$0.003" in html or "0.0030" in html
        assert "$0.002" in html or "0.0020" in html

    def test_no_cost_section_when_none(self, compare_data_keep):
        html = render_compare_report(compare_data_keep)
        # cost_ratio is None, so cost analysis section should not appear
        assert "Cost Analysis" not in html

    def test_contains_verdict_reason(self, compare_data):
        html = render_compare_report(compare_data)
        assert "33% cheaper" in html

    def test_dark_theme_colours(self, compare_data):
        html = render_compare_report(compare_data)
        assert "#111113" in html
        assert "#fb923c" in html

    def test_self_contained(self, compare_data):
        html = render_compare_report(compare_data)
        assert "<style>" in html
        assert "link rel=" not in html.lower()

    def test_no_assertions_section_when_empty(self, compare_data_keep):
        html = render_compare_report(compare_data_keep)
        assert "Per-Assertion" not in html


# ---------------------------------------------------------------------------
# CLI --output integration
# ---------------------------------------------------------------------------

class TestCLIOutput:

    @pytest.fixture(autouse=True)
    def isolated_db(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PROMPTRY_DB", str(tmp_path / "test.db"))
        from promptry.config import reset_config
        from promptry.storage import reset_storage
        reset_storage()
        reset_config()
        yield
        reset_storage()
        reset_config()

    def test_run_output_writes_html(self, tmp_path, monkeypatch):
        """The --output flag on `run` should write an HTML file."""
        from promptry.cli import app

        # Create a minimal suite module
        mod_file = tmp_path / "suite_mod.py"
        mod_file.write_text(
            "from promptry import suite, assert_contains\n"
            "@suite('html-test')\n"
            "def test_html():\n"
            "    assert_contains('hello world', ['hello'])\n",
            encoding="utf-8",
        )
        monkeypatch.syspath_prepend(str(tmp_path))

        report_path = tmp_path / "report.html"
        cli_runner = CliRunner()
        result = cli_runner.invoke(
            app,
            ["run", "html-test", "--module", "suite_mod", "--output", str(report_path)],
        )

        assert report_path.exists(), f"Report file not created. CLI output:\n{result.output}"
        content = report_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "html-test" in content
        assert "Report written to" in result.output

    def test_compare_output_writes_html(self, tmp_path, monkeypatch):
        """The --output flag on `compare` should write an HTML file."""
        from promptry.cli import app
        from promptry.storage import Storage

        # Seed eval runs for two models
        db_path = tmp_path / "test.db"
        monkeypatch.setenv("PROMPTRY_DB", str(db_path))
        from promptry.config import reset_config
        from promptry.storage import reset_storage
        reset_storage()
        reset_config()

        storage = Storage(db_path=db_path)

        for _ in range(3):
            run_id = storage.save_eval_run(
                suite_name="cmp-suite",
                prompt_name=None,
                prompt_version=None,
                model_version="model-a",
                overall_pass=True,
                overall_score=0.85,
            )
            storage.save_eval_result(
                run_id=run_id,
                test_name="t1",
                assertion_type="semantic",
                passed=True,
                score=0.85,
                details=None,
                latency_ms=100.0,
            )

        for _ in range(2):
            run_id = storage.save_eval_run(
                suite_name="cmp-suite",
                prompt_name=None,
                prompt_version=None,
                model_version="model-b",
                overall_pass=True,
                overall_score=0.90,
            )
            storage.save_eval_result(
                run_id=run_id,
                test_name="t1",
                assertion_type="semantic",
                passed=True,
                score=0.90,
                details=None,
                latency_ms=80.0,
            )
        storage.close()

        report_path = tmp_path / "compare.html"
        cli_runner = CliRunner()
        result = cli_runner.invoke(
            app,
            ["compare", "cmp-suite", "--candidate", "model-b", "--baseline", "model-a", "--output", str(report_path)],
        )

        assert report_path.exists(), f"Report file not created. CLI output:\n{result.output}"
        content = report_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "model-a" in content
        assert "model-b" in content
