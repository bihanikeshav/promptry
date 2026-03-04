import pytest
from promptry.evaluator import suite, clear_suites
from promptry.runner import run_suite, compare_with_baseline, format_comparison


@pytest.fixture(autouse=True)
def _clean():
    clear_suites()
    yield
    clear_suites()


class TestRunSuite:

    def test_passing_suite(self, storage):
        @suite("pass_suite")
        def my_test():
            from promptry.assertions import assert_schema
            from pydantic import BaseModel

            class Simple(BaseModel):
                value: int

            assert_schema({"value": 42}, Simple)

        result = run_suite("pass_suite", storage=storage)
        assert result.overall_pass is True
        assert result.overall_score > 0

    def test_failing_suite(self, storage):
        @suite("fail_suite")
        def my_test():
            from promptry.assertions import assert_schema
            from pydantic import BaseModel

            class Simple(BaseModel):
                value: int

            assert_schema({"wrong_key": "bad"}, Simple)

        result = run_suite("fail_suite", storage=storage)
        assert result.overall_pass is False

    def test_stores_results(self, storage):
        @suite("stored_suite")
        def my_test():
            from promptry.assertions import assert_schema
            from pydantic import BaseModel

            class Simple(BaseModel):
                value: int

            assert_schema({"value": 1}, Simple)

        result = run_suite("stored_suite", storage=storage)
        assert result.run_id is not None

        # check it actually persisted
        runs = storage.get_eval_runs("stored_suite")
        assert len(runs) == 1
        results = storage.get_eval_results(runs[0].id)
        assert len(results) == 1

    def test_unknown_suite_raises(self, storage):
        with pytest.raises(ValueError, match="not found"):
            run_suite("nonexistent", storage=storage)

    def test_exception_in_suite(self, storage):
        @suite("error_suite")
        def my_test():
            raise RuntimeError("something broke")

        result = run_suite("error_suite", storage=storage)
        assert result.overall_pass is False
        assert "RuntimeError" in result.tests[0].error

    def test_records_prompt_and_model(self, storage):
        @suite("meta_suite")
        def my_test():
            pass

        result = run_suite(
            "meta_suite",
            prompt_name="qa",
            prompt_version=3,
            model_version="gpt-4",
            storage=storage,
        )
        runs = storage.get_eval_runs("meta_suite")
        assert runs[0].prompt_name == "qa"
        assert runs[0].prompt_version == 3
        assert runs[0].model_version == "gpt-4"


class TestBaselineComparison:

    def test_compare_detects_regression(self, storage):
        @suite("regression_suite")
        def my_test():
            from promptry.assertions import assert_schema
            from pydantic import BaseModel

            class Simple(BaseModel):
                value: int

            assert_schema({"value": 1}, Simple)

        # run baseline
        baseline = run_suite("regression_suite", storage=storage)

        # simulate a worse run by inserting directly
        run_id = storage.save_eval_run(
            suite_name="regression_suite",
            overall_pass=True,
            overall_score=0.5,  # dropped from 1.0
        )
        storage.save_eval_result(
            run_id=run_id,
            test_name="regression_suite",
            assertion_type="schema",
            passed=False,
            score=0.5,
        )

        from promptry.runner import SuiteResult, TestResult
        worse = SuiteResult(
            suite_name="regression_suite",
            tests=[],
            overall_pass=True,
            overall_score=0.5,
            run_id=run_id,
        )

        comparisons, hints = compare_with_baseline(worse, storage=storage)
        assert len(comparisons) > 0
        assert any(not c.passed for c in comparisons)

    def test_no_baseline_returns_empty(self, storage):
        from promptry.runner import SuiteResult
        result = SuiteResult(
            suite_name="no_baseline",
            tests=[],
            overall_pass=True,
            overall_score=0.9,
            run_id=999,
        )
        comparisons, hints = compare_with_baseline(result, storage=storage)
        assert comparisons == []


class TestFormatComparison:

    def test_formats_output(self):
        from promptry.runner import ComparisonResult, RootCauseHint

        comparisons = [
            ComparisonResult("Overall score", 0.91, 0.82, passed=False),
        ]
        hints = [
            RootCauseHint("Prompt changed", "v1 -> v2"),
        ]

        output = format_comparison(comparisons, hints)
        assert "0.910" in output
        assert "0.820" in output
        assert "REGRESSION" in output
        assert "Prompt changed" in output
