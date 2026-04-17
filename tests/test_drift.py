import pytest
from promptry.drift import (
    DriftMonitor,
    _linear_slope,
    _stddev,
    _rank_values,
    _mann_whitney_u_pvalue,
)


class TestLinearSlope:

    def test_flat(self):
        assert _linear_slope([1.0, 1.0, 1.0, 1.0]) == pytest.approx(0.0)

    def test_increasing(self):
        assert _linear_slope([0.5, 0.6, 0.7, 0.8]) > 0

    def test_decreasing(self):
        assert _linear_slope([0.9, 0.8, 0.7, 0.6]) < 0

    def test_single_value(self):
        assert _linear_slope([0.5]) == 0.0


class TestStddev:

    def test_identical(self):
        assert _stddev([0.5, 0.5, 0.5]) == pytest.approx(0.0)

    def test_known_value(self):
        # stddev of [1, 2, 3, 4, 5] with N-1 denominator is sqrt(2.5) ≈ 1.5811
        assert _stddev([1.0, 2.0, 3.0, 4.0, 5.0]) == pytest.approx(1.5811, abs=1e-3)

    def test_single_value(self):
        assert _stddev([0.5]) == 0.0

    def test_empty(self):
        assert _stddev([]) == 0.0


class TestRankValues:

    def test_no_ties(self):
        # [3, 1, 2] -> ranks [3, 1, 2]
        assert _rank_values([3.0, 1.0, 2.0]) == [3.0, 1.0, 2.0]

    def test_with_ties(self):
        # [1, 2, 2, 3] -> ranks should be [1, 2.5, 2.5, 4]
        ranks = _rank_values([1.0, 2.0, 2.0, 3.0])
        assert ranks == [1.0, 2.5, 2.5, 4.0]


class TestMannWhitneyU:

    def test_identical_distributions(self):
        # Same data -> p ≈ 1.0
        a = [0.5] * 10
        b = [0.5] * 10
        p = _mann_whitney_u_pvalue(a, b)
        assert p is not None
        assert p > 0.9

    def test_clearly_different_distributions(self):
        # Group 1 all low, group 2 all high -> p very small
        a = [0.1, 0.15, 0.12, 0.11, 0.13, 0.14, 0.16, 0.12]
        b = [0.9, 0.85, 0.88, 0.91, 0.92, 0.87, 0.93, 0.89]
        p = _mann_whitney_u_pvalue(a, b)
        assert p is not None
        assert p < 0.01

    def test_insufficient_samples(self):
        # Fewer than 8 per group -> None
        a = [0.1, 0.2, 0.3]
        b = [0.7, 0.8, 0.9]
        assert _mann_whitney_u_pvalue(a, b) is None

    def test_overlapping_distributions(self):
        # Similar but not identical -> p somewhere in the middle
        a = [0.5, 0.55, 0.6, 0.52, 0.58, 0.51, 0.54, 0.57]
        b = [0.6, 0.55, 0.5, 0.58, 0.52, 0.61, 0.56, 0.53]
        p = _mann_whitney_u_pvalue(a, b)
        assert p is not None
        assert p > 0.1


class TestDriftMonitor:

    def _seed_runs(self, storage, suite_name, scores):
        for score in scores:
            storage.save_eval_run(
                suite_name=suite_name,
                overall_pass=score > 0.5,
                overall_score=score,
            )

    def test_not_enough_data(self, storage):
        monitor = DriftMonitor(storage=storage)
        report = monitor.check("empty_suite")
        assert not report.is_drifting
        assert "Not enough data" in report.message

    def test_stable_scores(self, storage):
        self._seed_runs(storage, "stable", [0.9, 0.88, 0.91, 0.89, 0.90])
        monitor = DriftMonitor(storage=storage)
        report = monitor.check("stable", threshold=0.05)
        assert not report.is_drifting

    def test_drifting_scores(self, storage):
        self._seed_runs(storage, "declining", [0.95, 0.90, 0.82, 0.75, 0.65])
        monitor = DriftMonitor(storage=storage)
        report = monitor.check("declining", threshold=0.01)
        assert report.is_drifting
        assert report.slope < 0

    def test_custom_window(self, storage):
        scores = [0.9] * 7 + [0.5, 0.4, 0.3]
        self._seed_runs(storage, "windowed", scores)
        monitor = DriftMonitor(storage=storage)
        report = monitor.check("windowed", window=3, threshold=0.01)
        assert report.is_drifting

    def test_confidence_insufficient_under_10_runs(self, storage):
        self._seed_runs(storage, "small", [0.9, 0.8, 0.7])
        report = DriftMonitor(storage=storage).check("small", threshold=0.01)
        assert report.confidence == "insufficient"

    def test_confidence_low_for_stable_scores(self, storage):
        self._seed_runs(storage, "stable20", [0.88, 0.89, 0.90, 0.91, 0.89,
                                              0.88, 0.90, 0.91, 0.89, 0.90,
                                              0.88, 0.89, 0.90, 0.91, 0.89,
                                              0.88, 0.90, 0.91, 0.89, 0.90])
        report = DriftMonitor(storage=storage).check("stable20", threshold=0.01)
        assert report.confidence == "low"
        assert report.p_value is not None  # 20 >= 16 so Mann-Whitney should run

    def test_confidence_high_for_clear_drift(self, storage):
        # 20 scores declining clearly
        scores = [0.95, 0.94, 0.93, 0.92, 0.91, 0.90, 0.89, 0.88, 0.87, 0.86,
                  0.80, 0.78, 0.76, 0.74, 0.72, 0.70, 0.68, 0.66, 0.64, 0.62]
        self._seed_runs(storage, "clear_drift", scores)
        report = DriftMonitor(storage=storage).check("clear_drift", threshold=0.001)
        assert report.confidence == "high"
        assert report.is_drifting
        assert report.p_value is not None
        assert report.p_value < 0.05

    def test_stddev_populated(self, storage):
        self._seed_runs(storage, "varied", [0.5, 0.7, 0.6, 0.8, 0.4])
        report = DriftMonitor(storage=storage).check("varied")
        assert report.stddev_score > 0

    def test_latest_z_score(self, storage):
        # 10 runs at 0.9, then one at 0.5 — latest should be very unusual
        scores = [0.9] * 10 + [0.5]
        self._seed_runs(storage, "outlier", scores)
        report = DriftMonitor(storage=storage).check("outlier")
        assert report.latest_z is not None
        assert report.latest_z < -2  # strongly negative
