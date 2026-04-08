import pytest
from typer.testing import CliRunner
from promptry.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTRY_DB", str(tmp_path / "test.db"))
    from promptry.config import reset_config
    reset_config()
    yield
    reset_config()


class TestDoctor:

    def test_doctor_runs(self):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0

    def test_doctor_checks_python(self):
        result = runner.invoke(app, ["doctor"])
        assert "Python version" in result.output

    def test_doctor_checks_storage(self):
        result = runner.invoke(app, ["doctor"])
        assert "Storage writable" in result.output

    def test_doctor_checks_sentence_transformers(self):
        result = runner.invoke(app, ["doctor"])
        assert "sentence-transformers" in result.output

    def test_doctor_checks_dashboard(self):
        result = runner.invoke(app, ["doctor"])
        assert "Dashboard" in result.output

    def test_doctor_prints_summary(self):
        result = runner.invoke(app, ["doctor"])
        assert "ok," in result.output
        assert "warnings" in result.output
