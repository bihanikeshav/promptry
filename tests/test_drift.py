import pytest
from promptry.drift import DriftMonitor, _linear_slope


class TestLinearSlope:

    def test_flat(self):
        assert _linear_slope([1.0, 1.0, 1.0, 1.0]) == pytest.approx(0.0)

    def test_increasing(self):
        assert _linear_slope([0.5, 0.6, 0.7, 0.8]) > 0

    def test_decreasing(self):
        assert _linear_slope([0.9, 0.8, 0.7, 0.6]) < 0

    def test_single_value(self):
        assert _linear_slope([0.5]) == 0.0


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
