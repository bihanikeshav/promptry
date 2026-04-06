import pytest
from typer.testing import CliRunner
from promptry.cli import app

runner = CliRunner()

try:
    import sentence_transformers  # noqa: F401
    _has_st = True
except ImportError:
    _has_st = False

needs_semantic = pytest.mark.skipif(not _has_st, reason="requires promptry[semantic]")


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTRY_DB", str(tmp_path / "test.db"))
    from promptry.config import reset_config
    reset_config()
    yield
    reset_config()


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


class TestInitCLI:

    def test_init_creates_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Created" in result.output
        assert (tmp_path / "promptry.toml").exists()
        assert (tmp_path / "evals.py").exists()

    def test_init_does_not_overwrite(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "promptry.toml").write_text("existing", encoding="utf-8")
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "already exists" in result.output
        # original content preserved
        assert (tmp_path / "promptry.toml").read_text() == "existing"

    def test_init_creates_valid_toml(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        import sys
        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib
        with open(tmp_path / "promptry.toml", "rb") as f:
            data = tomllib.load(f)
        assert "storage" in data


class TestTemplatesCLI:

    def test_templates_list(self):
        result = runner.invoke(app, ["templates", "list"])
        assert result.exit_code == 0
        assert "injection" in result.output.lower() or "jailbreak" in result.output.lower()

    @needs_semantic
    def test_templates_run_custom_func(self, tmp_path, monkeypatch):
        """--func flag should use the specified function name."""
        mod_file = tmp_path / "mymod.py"
        mod_file.write_text(
            "def my_llm(prompt):\n"
            "    return 'I cannot help with that request.'\n",
            encoding="utf-8",
        )
        monkeypatch.syspath_prepend(str(tmp_path))
        result = runner.invoke(
            app, ["templates", "run", "--module", "mymod", "--func", "my_llm", "--category", "prompt_injection"]
        )
        assert result.exit_code in (0, 1)  # runs without crashing
        assert "PASS" in result.output or "FAIL" in result.output

    def test_templates_run_missing_func(self, tmp_path, monkeypatch):
        """Should error when specified function doesn't exist."""
        mod_file = tmp_path / "emptymod.py"
        mod_file.write_text("x = 1\n", encoding="utf-8")
        monkeypatch.syspath_prepend(str(tmp_path))
        result = runner.invoke(
            app, ["templates", "run", "--module", "emptymod", "--func", "nonexistent"]
        )
        assert result.exit_code == 1
        assert "nonexistent" in result.output
