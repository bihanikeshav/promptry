"""Suite runner.

Executes eval suites, stores results. Comparison logic lives
in comparison.py -- this module is just execution.
"""
from __future__ import annotations

import time

from promptry.evaluator import get_suite, run_context
from promptry.models import TestResult, SuiteResult
from promptry.storage import Storage

# re-export for backwards compat (tests import these from runner)
from promptry.models import ComparisonResult, RootCauseHint  # noqa: F401
from promptry.comparison import compare_with_baseline, format_comparison  # noqa: F401


def run_suite(
    suite_name,
    prompt_name=None,
    prompt_version=None,
    model_version=None,
    storage=None,
) -> SuiteResult:
    """Run all tests in a suite and store the results."""
    suite_def = get_suite(suite_name)
    if not suite_def:
        raise ValueError(f"Suite '{suite_name}' not found. Did you import the module that defines it?")

    storage = storage or Storage()
    test_result = _execute_test(suite_def.fn, suite_def.name)

    scores = [a.score for a in test_result.assertions if a.score is not None]
    overall_score = sum(scores) / len(scores) if scores else 0.0
    overall_pass = test_result.passed

    run_id = storage.save_eval_run(
        suite_name=suite_name,
        prompt_name=prompt_name,
        prompt_version=prompt_version,
        model_version=model_version,
        overall_pass=overall_pass,
        overall_score=overall_score,
    )

    for assertion in test_result.assertions:
        storage.save_eval_result(
            run_id=run_id,
            test_name=test_result.test_name,
            assertion_type=assertion.assertion_type,
            passed=assertion.passed,
            score=assertion.score,
            details=assertion.details,
            latency_ms=test_result.latency_ms,
        )

    return SuiteResult(
        suite_name=suite_name,
        tests=[test_result],
        overall_pass=overall_pass,
        overall_score=overall_score,
        prompt_name=prompt_name,
        prompt_version=prompt_version,
        model_version=model_version,
        run_id=run_id,
    )


def _execute_test(fn, test_name) -> TestResult:
    """Run a single test function, catching failures."""
    start = time.perf_counter()
    with run_context() as results:
        try:
            fn()
            passed = True
            error = None
        except AssertionError as e:
            passed = False
            error = str(e)
        except Exception as e:
            passed = False
            error = f"{type(e).__name__}: {e}"

    elapsed = (time.perf_counter() - start) * 1000
    return TestResult(
        test_name=test_name,
        passed=passed,
        assertions=list(results),
        error=error,
        latency_ms=elapsed,
    )
