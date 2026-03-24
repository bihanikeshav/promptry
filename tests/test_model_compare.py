"""Tests for model comparison."""
import pytest

from promptry.evaluator import suite, clear_suites, run_context
from promptry.assertions import assert_contains
from promptry.model_compare import (
    compare_models,
    format_model_compare,
    _mean,
    _std,
    _percentile_rank,
)
from promptry.storage.sqlite import SQLiteStorage


@pytest.fixture
def storage(tmp_path):
    return SQLiteStorage(db_path=tmp_path / "test.db")


def _seed_runs(storage, suite_name, model_version, scores):
    """Create eval runs with the given scores."""
    run_ids = []
    for score in scores:
        run_id = storage.save_eval_run(
            suite_name=suite_name,
            model_version=model_version,
            overall_pass=score >= 0.7,
            overall_score=score,
        )
        # add some assertion results
        storage.save_eval_result(
            run_id=run_id,
            test_name="test_main",
            assertion_type="semantic",
            passed=score >= 0.7,
            score=score,
        )
        storage.save_eval_result(
            run_id=run_id,
            test_name="test_main",
            assertion_type="json_valid",
            passed=True,
            score=1.0,
        )
        run_ids.append(run_id)
    return run_ids


class TestStatHelpers:

    def test_mean(self):
        assert _mean([1, 2, 3]) == pytest.approx(2.0)

    def test_mean_empty(self):
        assert _mean([]) == 0.0

    def test_std(self):
        # std of [2, 4, 4, 4, 5, 5, 7, 9] = 2.0
        assert _std([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(2.0, abs=0.2)

    def test_std_single(self):
        assert _std([5.0]) == 0.0

    def test_percentile_rank(self):
        # 0.9 is above 80% of [0.7, 0.8, 0.85, 0.88, 0.92]
        pctl = _percentile_rank(0.9, [0.7, 0.8, 0.85, 0.88, 0.92])
        assert 60 < pctl < 90

    def test_percentile_rank_empty(self):
        assert _percentile_rank(0.5, []) == 50.0


class TestCompareModels:

    def test_basic_comparison(self, storage):
        _seed_runs(storage, "test-suite", "gpt-4o", [0.85, 0.87, 0.89, 0.86, 0.88])
        _seed_runs(storage, "test-suite", "claude-sonnet", [0.92])

        report = compare_models(
            suite_name="test-suite",
            candidate="claude-sonnet",
            baseline="gpt-4o",
            storage=storage,
        )

        assert report.suite_name == "test-suite"
        assert report.baseline.model_version == "gpt-4o"
        assert report.candidate.model_version == "claude-sonnet"
        assert report.baseline.run_count == 5
        assert report.candidate.run_count == 1
        assert report.overall_delta > 0  # candidate is better
        assert report.percentile > 50  # candidate is above median

    def test_auto_detect_baseline(self, storage):
        _seed_runs(storage, "test-suite", "gpt-4o", [0.85, 0.87, 0.89])
        _seed_runs(storage, "test-suite", "claude-sonnet", [0.92])

        report = compare_models(
            suite_name="test-suite",
            candidate="claude-sonnet",
            storage=storage,
        )

        # should auto-detect gpt-4o as baseline (most runs)
        assert report.baseline.model_version == "gpt-4o"

    def test_worse_candidate(self, storage):
        _seed_runs(storage, "test-suite", "gpt-4o", [0.90, 0.92, 0.91, 0.89])
        _seed_runs(storage, "test-suite", "cheap-model", [0.60])

        report = compare_models(
            suite_name="test-suite",
            candidate="cheap-model",
            baseline="gpt-4o",
            storage=storage,
        )

        assert report.overall_delta < 0
        assert report.verdict == "keep_baseline"

    def test_comparable_models(self, storage):
        _seed_runs(storage, "test-suite", "gpt-4o", [0.88, 0.89, 0.87, 0.90])
        _seed_runs(storage, "test-suite", "gpt-4o-mini", [0.88])

        report = compare_models(
            suite_name="test-suite",
            candidate="gpt-4o-mini",
            baseline="gpt-4o",
            storage=storage,
        )

        assert report.verdict == "comparable"

    def test_assertion_comparisons_populated(self, storage):
        _seed_runs(storage, "test-suite", "gpt-4o", [0.85, 0.87])
        _seed_runs(storage, "test-suite", "claude", [0.90])

        report = compare_models(
            suite_name="test-suite",
            candidate="claude",
            baseline="gpt-4o",
            storage=storage,
        )

        assert len(report.assertion_comparisons) > 0
        atypes = [ac.assertion_type for ac in report.assertion_comparisons]
        assert "semantic" in atypes
        assert "json_valid" in atypes

    def test_no_baseline_runs_raises(self, storage):
        _seed_runs(storage, "test-suite", "claude", [0.90])

        with pytest.raises(ValueError, match="No runs found for baseline"):
            compare_models(
                suite_name="test-suite",
                candidate="claude",
                baseline="nonexistent",
                storage=storage,
            )

    def test_no_candidate_runs_raises(self, storage):
        _seed_runs(storage, "test-suite", "gpt-4o", [0.85])

        with pytest.raises(ValueError, match="No runs found for candidate"):
            compare_models(
                suite_name="test-suite",
                candidate="nonexistent",
                baseline="gpt-4o",
                storage=storage,
            )

    def test_no_auto_baseline_raises(self, storage):
        _seed_runs(storage, "test-suite", "only-model", [0.85])

        with pytest.raises(ValueError, match="No baseline model found"):
            compare_models(
                suite_name="test-suite",
                candidate="only-model",
                storage=storage,
            )


class TestFormatReport:

    def test_format_includes_key_info(self, storage):
        _seed_runs(storage, "test-suite", "gpt-4o", [0.85, 0.87, 0.89])
        _seed_runs(storage, "test-suite", "claude", [0.92])

        report = compare_models(
            suite_name="test-suite",
            candidate="claude",
            baseline="gpt-4o",
            storage=storage,
        )

        output = format_model_compare(report)

        assert "gpt-4o" in output
        assert "claude" in output
        assert "3 runs" in output
        assert "1 runs" in output
        assert "Verdict" in output
        assert "By assertion type" in output

    def test_format_verdict_labels(self, storage):
        _seed_runs(storage, "test-suite", "gpt-4o", [0.90, 0.92, 0.91])
        _seed_runs(storage, "test-suite", "bad-model", [0.50])

        report = compare_models(
            suite_name="test-suite",
            candidate="bad-model",
            baseline="gpt-4o",
            storage=storage,
        )

        output = format_model_compare(report)
        assert "KEEP BASELINE" in output
