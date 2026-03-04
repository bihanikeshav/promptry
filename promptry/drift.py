"""Drift detection for eval scores.

Looks at recent score history and flags when things are trending
downward. Uses simple linear regression (no numpy needed) to
detect sustained drops vs one-off flukes.
"""
from __future__ import annotations

from promptry.config import get_config
from promptry.models import DriftReport


class DriftMonitor:

    def __init__(self, storage=None):
        if storage is None:
            from promptry.storage import get_storage
            storage = get_storage()
        self._storage = storage

    def check(self, suite_name: str, window: int | None = None, threshold: float | None = None) -> DriftReport:
        """Check if a suite's scores are drifting downward.

        window: how many recent runs to analyze (default from config)
        threshold: slope steeper than -threshold counts as drift (default from config)
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
            )

        # scores come newest-first from storage, reverse for regression
        scores = [s for _, s in reversed(history)]
        slope = _linear_slope(scores)
        mean_score = sum(scores) / len(scores)
        latest = scores[-1]

        is_drifting = slope < -threshold

        if is_drifting:
            msg = f"Scores trending down (slope: {slope:.4f}, threshold: -{threshold})"
        else:
            msg = f"Scores stable (slope: {slope:.4f})"

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
        )


def _linear_slope(values: list[float]) -> float:
    """Ordinary least squares slope. No numpy required.

    Fits y = mx + b to the values where x = 0, 1, 2, ...
    Returns m (the slope). Negative slope means scores are declining.
    """
    n = len(values)
    if n < 2:
        return 0.0

    # x values are just 0..n-1
    sum_x = n * (n - 1) / 2
    sum_y = sum(values)
    sum_xy = sum(i * v for i, v in enumerate(values))
    sum_x2 = n * (n - 1) * (2 * n - 1) / 6

    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return 0.0

    return (n * sum_xy - sum_x * sum_y) / denom


def format_drift_report(report: DriftReport) -> str:
    """Format a drift report for terminal output."""
    lines = [
        f"  Suite: {report.suite_name}",
        f"  Window: {len(report.scores)}/{report.window} runs",
        f"  Latest score: {report.latest_score:.3f}",
        f"  Mean score: {report.mean_score:.3f}",
        f"  Slope: {report.slope:.4f}",
    ]

    if report.is_drifting:
        lines.append(f"  Status: DRIFTING (threshold: -{report.threshold})")
    else:
        lines.append(f"  Status: stable")

    return "\n".join(lines)
