"""Baseline comparison and root cause analysis.

When a suite run finishes, compare it against the last known good run
to see if anything got worse. If it did, try to explain why.
"""
from __future__ import annotations

from promptry.models import SuiteResult, ComparisonResult, RootCauseHint
from promptry.storage import Storage


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

    # find the baseline run
    baseline_prompt = None
    if current.prompt_name:
        baseline_prompt = storage.get_prompt_by_tag(current.prompt_name, baseline_tag)

    baseline_run = None
    if baseline_prompt:
        runs = storage.get_eval_runs(current.suite_name, limit=100)
        for run in runs:
            if run.prompt_version == baseline_prompt.version and run.id != current.run_id:
                baseline_run = run
                break

    # no prompt-matched baseline, grab previous run
    if not baseline_run:
        runs = storage.get_eval_runs(current.suite_name, limit=10)
        for run in runs:
            if run.id != current.run_id:
                baseline_run = run
                break

    if not baseline_run:
        return comparisons, hints

    # overall score
    if baseline_run.overall_score is not None and current.overall_score is not None:
        comparisons.append(ComparisonResult(
            metric="Overall score",
            baseline_value=baseline_run.overall_score,
            current_value=current.overall_score,
            passed=current.overall_score >= baseline_run.overall_score - 0.05,
        ))

    # per-assertion-type pass rates
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

    if (current.prompt_version and baseline_run.prompt_version
            and current.prompt_version != baseline_run.prompt_version):
        hints.append(RootCauseHint(
            cause="Prompt changed",
            detail=f"v{baseline_run.prompt_version} -> v{current.prompt_version}",
        ))

    if (current.model_version and baseline_run.model_version
            and current.model_version != baseline_run.model_version):
        hints.append(RootCauseHint(
            cause="Model changed",
            detail=f"{baseline_run.model_version} -> {current.model_version}",
        ))

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
