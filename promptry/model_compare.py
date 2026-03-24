"""Model comparison using historical eval data.

Compare a candidate model against the historical performance distribution
of your baseline model. Uses statistical analysis to determine whether
switching models is a good idea, factoring in score consistency, per-assertion
breakdowns, and cost efficiency.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class AssertionStats:
    """Statistics for a single assertion type."""
    assertion_type: str
    mean_score: float
    std_score: float
    count: int
    pass_rate: float


@dataclass
class ModelStats:
    """Aggregate statistics for a model across all runs."""
    model_version: str
    run_count: int
    overall_mean: float
    overall_std: float
    overall_min: float
    overall_max: float
    scores: list[float]
    assertion_stats: dict[str, AssertionStats] = field(default_factory=dict)
    avg_latency_ms: float = 0.0
    # cost fields (from prompt metadata, may be zero if not tracked)
    total_cost: float = 0.0
    avg_cost_per_call: float = 0.0


@dataclass
class AssertionComparison:
    assertion_type: str
    baseline_mean: float
    baseline_std: float
    candidate_score: float
    delta: float
    verdict: str  # "better", "worse", "comparable"


@dataclass
class ModelCompareReport:
    """Full comparison report between baseline and candidate models."""
    suite_name: str
    baseline: ModelStats
    candidate: ModelStats
    overall_delta: float
    percentile: float  # where candidate falls in baseline distribution
    assertion_comparisons: list[AssertionComparison]
    cost_ratio: float | None  # candidate_cost / baseline_cost, None if no cost data
    score_per_dollar_baseline: float | None
    score_per_dollar_candidate: float | None
    verdict: str  # "switch", "comparable", "keep_baseline"
    verdict_reason: str


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(variance)


def _percentile_rank(value: float, distribution: list[float]) -> float:
    """What fraction of the distribution is below this value (0-100)."""
    if not distribution:
        return 50.0
    below = sum(1 for x in distribution if x < value)
    equal = sum(1 for x in distribution if x == value)
    return ((below + 0.5 * equal) / len(distribution)) * 100


def _compute_model_stats(
    model_version: str,
    runs,
    all_results: dict[int, list],
) -> ModelStats:
    """Compute aggregate stats for a model's eval history."""
    scores = [r.overall_score for r in runs if r.overall_score is not None]

    # per-assertion stats
    assertion_scores: dict[str, list[float]] = defaultdict(list)
    assertion_passed: dict[str, list[bool]] = defaultdict(list)
    latencies = []

    for run in runs:
        results = all_results.get(run.id, [])
        for result in results:
            if result.score is not None:
                assertion_scores[result.assertion_type].append(result.score)
            assertion_passed[result.assertion_type].append(result.passed)
            if result.latency_ms:
                latencies.append(result.latency_ms)

    assertion_stats = {}
    for atype, atype_scores in assertion_scores.items():
        passed_list = assertion_passed.get(atype, [])
        assertion_stats[atype] = AssertionStats(
            assertion_type=atype,
            mean_score=_mean(atype_scores),
            std_score=_std(atype_scores),
            count=len(atype_scores),
            pass_rate=sum(1 for p in passed_list if p) / len(passed_list) if passed_list else 0.0,
        )

    return ModelStats(
        model_version=model_version,
        run_count=len(runs),
        overall_mean=_mean(scores),
        overall_std=_std(scores),
        overall_min=min(scores) if scores else 0.0,
        overall_max=max(scores) if scores else 0.0,
        scores=scores,
        assertion_stats=assertion_stats,
        avg_latency_ms=_mean(latencies),
    )


def _enrich_with_cost(stats: ModelStats, storage) -> None:
    """Pull cost metadata from prompts table if available."""
    import json as _json

    try:
        with storage._lock:
            cur = storage._conn.cursor()
            cur.execute(
                """SELECT metadata FROM prompts
                   WHERE metadata IS NOT NULL
                     AND metadata LIKE ?""",
                (f'%"model"%{stats.model_version}%',),
            )
            rows = cur.fetchall()
    except Exception:
        return

    costs = []
    for row in rows:
        try:
            meta = _json.loads(row["metadata"])
            cost = meta.get("cost", 0)
            if cost and cost > 0:
                costs.append(float(cost))
        except (ValueError, TypeError, _json.JSONDecodeError):
            continue

    if costs:
        stats.total_cost = sum(costs)
        stats.avg_cost_per_call = _mean(costs)


def compare_models(
    suite_name: str,
    candidate: str,
    baseline: str | None = None,
    storage=None,
) -> ModelCompareReport:
    """Compare candidate model against baseline using historical eval data.

    If baseline is None, uses the model with the most historical runs
    (excluding the candidate).

    Args:
        suite_name: The eval suite to compare on.
        candidate: Model version string for the candidate.
        baseline: Model version string for the baseline (optional).
        storage: Storage backend (defaults to configured storage).

    Returns:
        ModelCompareReport with statistics, per-assertion breakdown,
        cost analysis, and a verdict.
    """
    if storage is None:
        from promptry.storage import get_storage
        storage = get_storage()

    # auto-detect baseline if not specified
    if baseline is None:
        versions = storage.get_model_versions(suite_name)
        for version, count in versions:
            if version != candidate:
                baseline = version
                break
        if baseline is None:
            raise ValueError(
                f"No baseline model found for suite '{suite_name}'. "
                f"Run evals with --model-version to tag runs."
            )

    # pull runs for both models
    baseline_runs = storage.get_runs_by_model(suite_name, baseline)
    candidate_runs = storage.get_runs_by_model(suite_name, candidate)

    if not baseline_runs:
        raise ValueError(
            f"No runs found for baseline model '{baseline}' in suite '{suite_name}'."
        )
    if not candidate_runs:
        raise ValueError(
            f"No runs found for candidate model '{candidate}' in suite '{suite_name}'. "
            f"Run: promptry run {suite_name} --module <mod> --model-version {candidate}"
        )

    # pull all assertion results for these runs
    all_results: dict[int, list] = {}
    for run in baseline_runs + candidate_runs:
        all_results[run.id] = storage.get_eval_results(run.id)

    # compute stats
    b_stats = _compute_model_stats(baseline, baseline_runs, all_results)
    c_stats = _compute_model_stats(candidate, candidate_runs, all_results)

    # try to enrich with cost data
    _enrich_with_cost(b_stats, storage)
    _enrich_with_cost(c_stats, storage)

    # overall comparison
    overall_delta = c_stats.overall_mean - b_stats.overall_mean
    percentile = _percentile_rank(c_stats.overall_mean, b_stats.scores)

    # per-assertion comparisons
    assertion_comparisons = []
    all_atypes = set(b_stats.assertion_stats.keys()) | set(c_stats.assertion_stats.keys())
    for atype in sorted(all_atypes):
        b_astat = b_stats.assertion_stats.get(atype)
        c_astat = c_stats.assertion_stats.get(atype)

        if not b_astat or not c_astat:
            continue

        delta = c_astat.mean_score - b_astat.mean_score
        # within 1 std of baseline = comparable
        if b_astat.std_score > 0 and abs(delta) <= b_astat.std_score:
            verdict = "comparable"
        elif delta > 0:
            verdict = "better"
        else:
            verdict = "worse"

        assertion_comparisons.append(AssertionComparison(
            assertion_type=atype,
            baseline_mean=b_astat.mean_score,
            baseline_std=b_astat.std_score,
            candidate_score=c_astat.mean_score,
            delta=delta,
            verdict=verdict,
        ))

    # cost analysis
    cost_ratio = None
    spd_baseline = None
    spd_candidate = None

    if b_stats.avg_cost_per_call > 0 and c_stats.avg_cost_per_call > 0:
        cost_ratio = c_stats.avg_cost_per_call / b_stats.avg_cost_per_call
        spd_baseline = b_stats.overall_mean / b_stats.avg_cost_per_call
        spd_candidate = c_stats.overall_mean / c_stats.avg_cost_per_call

    # verdict
    verdict, reason = _compute_verdict(
        b_stats, c_stats, overall_delta, percentile,
        assertion_comparisons, cost_ratio,
    )

    return ModelCompareReport(
        suite_name=suite_name,
        baseline=b_stats,
        candidate=c_stats,
        overall_delta=overall_delta,
        percentile=percentile,
        assertion_comparisons=assertion_comparisons,
        cost_ratio=cost_ratio,
        score_per_dollar_baseline=spd_baseline,
        score_per_dollar_candidate=spd_candidate,
        verdict=verdict,
        verdict_reason=reason,
    )


def _compute_verdict(
    baseline: ModelStats,
    candidate: ModelStats,
    delta: float,
    percentile: float,
    assertion_comps: list[AssertionComparison],
    cost_ratio: float | None,
) -> tuple[str, str]:
    """Determine whether to switch, stay, or call it comparable."""
    worse_assertions = [a for a in assertion_comps if a.verdict == "worse"]
    better_assertions = [a for a in assertion_comps if a.verdict == "better"]

    # strong signal: candidate significantly better
    if baseline.overall_std > 0 and delta > baseline.overall_std:
        reason = (
            f"Candidate scores {delta:+.3f} higher (above {percentile:.0f}th "
            f"percentile of baseline)."
        )
        if cost_ratio and cost_ratio < 0.9:
            reason += f" Also {(1 - cost_ratio) * 100:.0f}% cheaper."
        if worse_assertions:
            names = ", ".join(a.assertion_type for a in worse_assertions)
            reason += f" Watch: {names} slightly lower."
        return "switch", reason

    # strong signal: candidate significantly worse
    if baseline.overall_std > 0 and delta < -baseline.overall_std:
        reason = (
            f"Candidate scores {delta:+.3f} lower ({percentile:.0f}th "
            f"percentile of baseline)."
        )
        if worse_assertions:
            names = ", ".join(a.assertion_type for a in worse_assertions)
            reason += f" Regressions in: {names}."
        return "keep_baseline", reason

    # within noise but cheaper
    if cost_ratio and cost_ratio < 0.7 and delta >= -0.01:
        reason = (
            f"Comparable scores (delta {delta:+.3f}, within noise) "
            f"but {(1 - cost_ratio) * 100:.0f}% cheaper."
        )
        return "switch", reason

    # within noise
    reason = (
        f"Scores are comparable (delta {delta:+.3f}, "
        f"{percentile:.0f}th percentile of baseline)."
    )
    if better_assertions:
        names = ", ".join(a.assertion_type for a in better_assertions)
        reason += f" Better at: {names}."
    if worse_assertions:
        names = ", ".join(a.assertion_type for a in worse_assertions)
        reason += f" Worse at: {names}."
    if cost_ratio:
        if cost_ratio < 1.0:
            reason += f" {(1 - cost_ratio) * 100:.0f}% cheaper."
        else:
            reason += f" {(cost_ratio - 1) * 100:.0f}% more expensive."
    return "comparable", reason


def format_model_compare(report: ModelCompareReport) -> str:
    """Format a ModelCompareReport for terminal output."""
    b = report.baseline
    c = report.candidate
    lines = []

    # header
    lines.append(
        f"Model comparison: {b.model_version} ({b.run_count} runs) "
        f"vs {c.model_version} ({c.run_count} runs)"
    )
    lines.append("")

    # overall scores
    b_range = f"[{b.overall_min:.3f} — {b.overall_max:.3f}]"
    lines.append(f"{'':20s} {b.model_version:>20s}    {c.model_version:>20s}")
    lines.append(f"{'Overall score':20s} {b.overall_mean:>13.3f} +/- {b.overall_std:.3f}    {c.overall_mean:>13.3f}")
    lines.append(f"{'':20s} {b_range:>20s}    {'':>4s}{report.overall_delta:+.3f} ({report.percentile:.0f}th pctl)")
    lines.append("")

    # per-assertion breakdown
    if report.assertion_comparisons:
        lines.append("By assertion type:")
        for ac in report.assertion_comparisons:
            indicator = {"better": "+", "worse": "-", "comparable": "~"}[ac.verdict]
            lines.append(
                f"  {ac.assertion_type:18s} "
                f"{ac.baseline_mean:.3f} +/- {ac.baseline_std:.3f}    "
                f"{ac.candidate_score:.3f}  [{indicator}] {ac.verdict}"
            )
        lines.append("")

    # cost comparison
    if report.cost_ratio is not None:
        lines.append("Cost analysis:")
        lines.append(
            f"  Cost per call:     ${b.avg_cost_per_call:.4f}              "
            f"${c.avg_cost_per_call:.4f}"
        )
        pct = abs(1 - report.cost_ratio) * 100
        direction = "cheaper" if report.cost_ratio < 1 else "more expensive"
        lines.append(f"  Candidate is {pct:.0f}% {direction}")

        if report.score_per_dollar_baseline and report.score_per_dollar_candidate:
            lines.append(
                f"  Score/$:           {report.score_per_dollar_baseline:.0f}                   "
                f"{report.score_per_dollar_candidate:.0f}"
            )
        lines.append("")

    # verdict
    verdict_label = {
        "switch": "SWITCH",
        "comparable": "COMPARABLE",
        "keep_baseline": "KEEP BASELINE",
    }[report.verdict]
    lines.append(f"Verdict: {verdict_label}")
    lines.append(f"  {report.verdict_reason}")

    return "\n".join(lines)
