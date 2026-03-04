import json
import pytest
from unittest.mock import patch, MagicMock

from promptry import scheduler


class TestScheduler:

    @pytest.fixture(autouse=True)
    def _temp_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr(scheduler, "_PROMPTRY_DIR", tmp_path)
        monkeypatch.setattr(scheduler, "_PID_FILE", tmp_path / "monitor.pid")
        monkeypatch.setattr(scheduler, "_LOG_FILE", tmp_path / "monitor.log")
        monkeypatch.setattr(scheduler, "_STATE_FILE", tmp_path / "monitor.json")
        self.tmp = tmp_path

    def test_is_running_no_pid_file(self):
        assert not scheduler.is_running()

    def test_is_running_stale_pid(self):
        (self.tmp / "monitor.pid").write_text("9999999")
        assert not scheduler.is_running()

    def test_stop_no_monitor(self):
        with pytest.raises(RuntimeError, match="No monitor running"):
            scheduler.stop()

    @patch("subprocess.Popen")
    def test_start_creates_pid_and_state(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        pid = scheduler.start("my_suite", "my_module", interval=60)

        assert pid == 12345
        assert (self.tmp / "monitor.pid").read_text() == "12345"
        state = json.loads((self.tmp / "monitor.json").read_text())
        assert state["suite"] == "my_suite"
        assert state["interval_minutes"] == 60

    @patch("subprocess.Popen")
    def test_start_when_already_running(self, mock_popen, monkeypatch):
        (self.tmp / "monitor.pid").write_text("12345")
        monkeypatch.setattr(scheduler, "is_running", lambda: True)

        with pytest.raises(RuntimeError, match="already running"):
            scheduler.start("suite", "module")

    @patch("os.kill")
    def test_stop_removes_pid_file(self, mock_kill):
        (self.tmp / "monitor.pid").write_text("12345")

        pid = scheduler.stop()
        assert pid == 12345
        assert not (self.tmp / "monitor.pid").exists()
