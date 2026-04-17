"""Drift detection for eval scores.

## What this does

Given a suite's score history (a time series of overall scores from
consecutive eval runs), report whether the scores are drifting downward.
Three signals are computed:

1. **OLS linear slope** over the whole window. Steep negative slope =
   sustained downward trend.
2. **Z-score of the latest run** relative to the window's mean and
   standard deviation. Tells you how unusual the most recent score is.
3. **Mann-Whitney U p-value** comparing the recent half of the window
   against the older half. This is a non-parametric rank-sum test that
   doesn't assume normality — appropriate for noisy LLM scores.

The binary `is_drifting` flag is kept for backward compatibility and is
based on the slope alone. A `confidence` field combines all three signals
into a qualitative label: "high" | "medium" | "low" | "insufficient".

## What this does NOT do

- **Not a formal change-point detector.** We split the window in half and
  compare. If drift happened at run 3 of 30, the split at run 15 will dilute
  the signal. For change-point detection use CUSUM or Bayesian online CPD.
- **No multiple-comparison correction across suites.** If you run drift on
  50 suites and use p < 0.05, you'll get ~2.5 false positives by chance.
  Apply Bonferroni (`p < 0.05 / num_suites`) manually if that matters.
- **Ties in scores aren't corrected** in the Mann-Whitney statistic. With
  continuous LLM scores this rarely matters, but heavy tie-clusters would
  inflate p-values slightly.
- **Small samples are flagged explicitly.** With fewer than 16 runs the
  p-value is `None` (normal approximation needs ~8 per group).

Pure-Python implementation — no scipy/numpy dependency.
"""
from __future__ import annotations

import math

from promptry.config import get_config
from promptry.models import DriftReport

# Minimum samples per group for Mann-Whitney normal approximation
_MWU_MIN_PER_GROUP = 8


class DriftMonitor:

    def __init__(self, storage=None):
        if storage is None:
            from promptry.storage import get_storage
            storage = get_storage()
        self._storage = storage

    def check(
        self,
        suite_name: str,
        window: int | None = None,
        threshold: float | None = None,
    ) -> DriftReport:
        """Check if a suite's scores are drifting downward.

        Args:
            suite_name: the suite to analyze
            window: how many recent runs to include (default from config)
            threshold: slope steeper than -threshold counts as drift
                (default from config)
        """
        config = get_config()
        window = window or config.monitor.window
        threshold = threshold if threshold is not None else config.monitor.threshold

        history = self._storage.get_score_history(suite_name, limit=window)

        if len(history) < 2:
            return DriftReport(
                suite_name=suite_name,
                window=window,
                scores=[],
                slope=0.0,
                mean_score=0.0,
                latest_score=0.0,
                is_drifting=False,
                threshold=threshold,
                message="Not enough data (need at least 2 runs)",
                stddev_score=0.0,
                latest_z=None,
                p_value=None,
                confidence="insufficient",
            )

        # scores come newest-first from storage, reverse for chronological
        scores = [s for _, s in reversed(history)]
        slope = _linear_slope(scores)
        mean_score = sum(scores) / len(scores)
        stddev_score = _stddev(scores)
        latest = scores[-1]

        # z-score of latest relative to the window's distribution
        latest_z = (latest - mean_score) / stddev_score if stddev_score > 0 else None

        # Mann-Whitney U: recent half vs older half
        p_value = None
        if len(scores) >= 2 * _MWU_MIN_PER_GROUP:
            half = len(scores) // 2
            older = scores[:half]
            recent = scores[half:]
            p_value = _mann_whitney_u_pvalue(recent, older)

        is_drifting = slope < -threshold

        # Confidence combines slope + significance + sample size
        if len(scores) < 10:
            confidence = "insufficient"
            msg = f"Only {len(scores)} runs — need 10+ for reliable drift"
        elif is_drifting and p_value is not None and p_value < 0.05:
            confidence = "high"
            msg = f"Drift confirmed: slope {slope:+.4f}, p={p_value:.3f}"
        elif is_drifting and p_value is None:
            confidence = "medium"
            msg = f"Slope trending down ({slope:+.4f}) — need 16+ runs for significance test"
        elif is_drifting:
            confidence = "medium"
            msg = f"Slope trending down ({slope:+.4f}), but not statistically significant (p={p_value:.3f})"
        elif p_value is not None and p_value < 0.05 and mean_score_of(scores[len(scores) // 2:]) < mean_score_of(scores[:len(scores) // 2]):
            confidence = "medium"
            msg = f"Recent half significantly lower (p={p_value:.3f}) even though overall slope is mild"
        else:
            confidence = "low"
            msg = f"Scores stable (slope: {slope:+.4f})"

        return DriftReport(
            suite_name=suite_name,
            window=window,
            scores=scores,
            slope=slope,
            mean_score=mean_score,
            latest_score=latest,
            is_drifting=is_drifting,
            threshold=threshold,
            message=msg,
            stddev_score=stddev_score,
            latest_z=latest_z,
            p_value=p_value,
            confidence=confidence,
        )


# ---------------------------------------------------------------------------
# Stats helpers (pure Python, no numpy/scipy)
# ---------------------------------------------------------------------------

def _linear_slope(values: list[float]) -> float:
    """Ordinary least squares slope of y vs index.

    Fits y = mx + b where x = 0, 1, 2, ... Returns m. Negative = declining.
    """
    n = len(values)
    if n < 2:
        return 0.0
    sum_x = n * (n - 1) / 2
    sum_y = sum(values)
    sum_xy = sum(i * v for i, v in enumerate(values))
    sum_x2 = n * (n - 1) * (2 * n - 1) / 6
    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom


def _stddev(values: list[float]) -> float:
    """Sample standard deviation (N-1 denominator)."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(variance)


def mean_score_of(values: list[float]) -> float:
    """Helper: mean of a non-empty list. Returns 0.0 if empty."""
    return sum(values) / len(values) if values else 0.0


def _rank_values(values: list[float]) -> list[float]:
    """Return ranks for values, averaging tied ranks (midrank method)."""
    indexed = sorted(enumerate(values), key=lambda p: p[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j) / 2 + 1  # 1-indexed rank
        for k in range(i, j + 1):
            orig_idx = indexed[k][0]
            ranks[orig_idx] = avg_rank
        i = j + 1
    return ranks


def _mann_whitney_u_pvalue(group1: list[float], group2: list[float]) -> float | None:
    """Two-tailed Mann-Whitney U p-value via normal approximation.

    Returns None if either group has fewer than 8 samples (approximation
    is unreliable at small N — callers should report insufficient data).
    No tie correction applied — acceptable for continuous LLM scores.
    """
    n1 = len(group1)
    n2 = len(group2)
    if n1 < _MWU_MIN_PER_GROUP or n2 < _MWU_MIN_PER_GROUP:
        return None

    combined = group1 + group2
    ranks = _rank_values(combined)
    r1 = sum(ranks[:n1])

    u1 = r1 - n1 * (n1 + 1) / 2
    u2 = n1 * n2 - u1
    u = min(u1, u2)

    mu = n1 * n2 / 2
    sigma_sq = n1 * n2 * (n1 + n2 + 1) / 12
    if sigma_sq <= 0:
        return 1.0
    sigma = math.sqrt(sigma_sq)

    z = (u - mu) / sigma
    # two-tailed p-value from standard normal CDF (math.erf is stdlib)
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return min(1.0, max(0.0, p))


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_drift_report(report: DriftReport) -> str:
    """Format a drift report for terminal output."""
    lines = [
        f"  Suite: {report.suite_name}",
        f"  Window: {len(report.scores)}/{report.window} runs",
        f"  Latest score: {report.latest_score:.3f}",
        f"  Mean +/- stddev: {report.mean_score:.3f} +/- {report.stddev_score:.3f}",
    ]
    if report.latest_z is not None:
        lines.append(f"  Latest z-score: {report.latest_z:+.2f}")
    lines.append(f"  Slope: {report.slope:+.4f}")
    if report.p_value is not None:
        lines.append(f"  Significance (recent vs older half): p={report.p_value:.3f}")
    else:
        lines.append(f"  Significance: insufficient data (need {2 * _MWU_MIN_PER_GROUP}+ runs)")
    lines.append(f"  Confidence: {report.confidence}")
    if report.is_drifting:
        lines.append(f"  Status: DRIFTING (slope < -{report.threshold})")
    else:
        lines.append("  Status: stable")
    return "\n".join(lines)
