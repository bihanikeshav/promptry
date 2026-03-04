"""Suite runner with baseline comparison and root cause hints.

Executes eval suites, stores results, compares against baselines,
and tries to explain why regressions happened.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from promptry.evaluator import get_suite, list_suites, AssertionResult, run_context
from promptry.storage import Storage


@dataclass
class TestResult:
    test_name: str
    passed: bool
    assertions: list[AssertionResult]
    error: str | None = None
    latency_ms: float = 0.0


@dataclass
class SuiteResult:
    suite_name: str
    tests: list[TestResult]
    overall_pass: bool = True
    overall_score: float = 0.0
    prompt_name: str | None = None
    prompt_version: int | None = None
    model_version: str | None = None
    run_id: int | None = None


@dataclass
class ComparisonResult:
    metric: str
    baseline_value: float
    current_value: float
    passed: bool


@dataclass
class RootCauseHint:
    """A possible explanation for a regression."""
    cause: str
    detail: str


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

    # compute aggregate score from all assertions
    scores = [a.score for a in test_result.assertions if a.score is not None]
    overall_score = sum(scores) / len(scores) if scores else 0.0
    overall_pass = test_result.passed

    # persist
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


def compare_with_baseline(
    current: SuiteResult,
    baseline_tag="prod",
    storage=None,
) -> tuple[list[ComparisonResult], list[RootCauseHint]]:
    """Compare current run against the most recent baseline.

    Returns (comparisons, root_cause_hints).
    """
    storage = storage or Storage()
    comparisons = []
    hints = []

    # find the baseline run -- look for the most recent run that was tagged
    # with the baseline prompt version
    baseline_prompt = None
    if current.prompt_name:
        baseline_prompt = storage.get_prompt_by_tag(current.prompt_name, baseline_tag)

    baseline_run = None
    if baseline_prompt:
        # find a run with this prompt version
        runs = storage.get_eval_runs(current.suite_name, limit=100)
        for run in runs:
            if run.prompt_version == baseline_prompt.version and run.id != current.run_id:
                baseline_run = run
                break

    # if no prompt-matched baseline, just grab the previous run
    if not baseline_run:
        runs = storage.get_eval_runs(current.suite_name, limit=10)
        for run in runs:
            if run.id != current.run_id:
                baseline_run = run
                break

    if not baseline_run:
        return comparisons, hints

    # compare scores
    if baseline_run.overall_score is not None and current.overall_score is not None:
        comparisons.append(ComparisonResult(
            metric="Overall score",
            baseline_value=baseline_run.overall_score,
            current_value=current.overall_score,
            passed=current.overall_score >= baseline_run.overall_score - 0.05,
        ))

    # compare pass rates by assertion type
    baseline_results = storage.get_eval_results(baseline_run.id)
    current_results = storage.get_eval_results(current.run_id) if current.run_id else []

    for atype in ("semantic", "contains", "schema"):
        b_results = [r for r in baseline_results if r.assertion_type == atype]
        c_results = [r for r in current_results if r.assertion_type == atype]

        if not b_results or not c_results:
            continue

        b_pass_rate = sum(1 for r in b_results if r.passed) / len(b_results)
        c_pass_rate = sum(1 for r in c_results if r.passed) / len(c_results)

        comparisons.append(ComparisonResult(
            metric=f"{atype.title()} pass rate",
            baseline_value=b_pass_rate,
            current_value=c_pass_rate,
            passed=c_pass_rate >= b_pass_rate - 0.05,
        ))

    # ---- root cause hints ----
    # check what changed between baseline and current

    # prompt changed?
    if (current.prompt_version and baseline_run.prompt_version
            and current.prompt_version != baseline_run.prompt_version):
        hints.append(RootCauseHint(
            cause="Prompt changed",
            detail=f"v{baseline_run.prompt_version} -> v{current.prompt_version}",
        ))

    # model changed?
    if (current.model_version and baseline_run.model_version
            and current.model_version != baseline_run.model_version):
        hints.append(RootCauseHint(
            cause="Model changed",
            detail=f"{baseline_run.model_version} -> {current.model_version}",
        ))

    # score dropped but nothing obvious changed? probably retrieval
    has_regression = any(not c.passed for c in comparisons)
    if has_regression and not hints:
        hints.append(RootCauseHint(
            cause="Possible retrieval drift",
            detail="Scores dropped but prompt and model are unchanged",
        ))

    return comparisons, hints


def format_comparison(comparisons, hints=None) -> str:
    """Format comparison results for terminal output."""
    lines = []

    for c in comparisons:
        indicator = "ok" if c.passed else "REGRESSION"
        if c.metric.endswith("pass rate"):
            lines.append(
                f"  {c.metric}: {c.baseline_value:.0%} -> {c.current_value:.0%}  {indicator}"
            )
        else:
            lines.append(
                f"  {c.metric}: {c.baseline_value:.3f} -> {c.current_value:.3f}  {indicator}"
            )

    if hints:
        lines.append("")
        lines.append("  Probable cause:")
        for h in hints:
            lines.append(f"    -> {h.cause} ({h.detail})")

    return "\n".join(lines)
