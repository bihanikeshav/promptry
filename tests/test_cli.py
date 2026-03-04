import pytest
from typer.testing import CliRunner
from promptry.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTRY_DB", str(tmp_path / "test.db"))


class TestPromptCLI:

    def test_save_from_stdin(self):
        result = runner.invoke(app, ["prompt", "save", "--name", "test"], input="Hello world")
        assert result.exit_code == 0
        assert "Saved" in result.output

    def test_save_from_file(self, tmp_path):
        f = tmp_path / "prompt.txt"
        f.write_text("File prompt content", encoding="utf-8")
        result = runner.invoke(app, ["prompt", "save", str(f), "--name", "test"])
        assert result.exit_code == 0
        assert "Saved" in result.output

    def test_save_empty_fails(self):
        result = runner.invoke(app, ["prompt", "save", "--name", "test"], input="")
        assert result.exit_code == 1

    def test_list(self):
        runner.invoke(app, ["prompt", "save", "--name", "a"], input="Content A")
        runner.invoke(app, ["prompt", "save", "--name", "b"], input="Content B")
        result = runner.invoke(app, ["prompt", "list"])
        assert result.exit_code == 0
        assert "a" in result.output
        assert "b" in result.output

    def test_show(self):
        runner.invoke(app, ["prompt", "save", "--name", "test"], input="Show me")
        result = runner.invoke(app, ["prompt", "show", "test"])
        assert result.exit_code == 0
        assert "Show me" in result.output

    def test_show_not_found(self):
        result = runner.invoke(app, ["prompt", "show", "nonexistent"])
        assert result.exit_code == 1

    def test_diff(self):
        runner.invoke(app, ["prompt", "save", "--name", "test"], input="Line one\nLine two\n")
        runner.invoke(app, ["prompt", "save", "--name", "test"], input="Line one\nLine changed\n")
        result = runner.invoke(app, ["prompt", "diff", "test", "1", "2"])
        assert result.exit_code == 0
        assert "Line two" in result.output
        assert "Line changed" in result.output

    def test_tag(self):
        runner.invoke(app, ["prompt", "save", "--name", "test"], input="Content")
        result = runner.invoke(app, ["prompt", "tag", "test", "1", "prod"])
        assert result.exit_code == 0
        assert "Tagged" in result.output
        assert "prod" in result.output
