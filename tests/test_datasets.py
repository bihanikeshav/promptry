"""Tests for dataset management: storage, registry API, and CLI."""
import json
import pytest
from promptry.storage import Storage
from promptry.registry import save_dataset, load_dataset, reset_registry
from typer.testing import CliRunner
from promptry.cli import app

runner = CliRunner()

SAMPLE_ITEMS = [
    {"input": "What is ML?", "expected": "Machine learning is..."},
    {"input": "Explain RAG", "expected": "Retrieval augmented generation..."},
]


@pytest.fixture
def storage(tmp_path):
    db = Storage(db_path=tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMPTRY_DB", str(tmp_path / "test.db"))
    from promptry.config import reset_config
    from promptry.storage import reset_storage
    reset_registry()
    reset_storage()
    reset_config()
    yield
    reset_registry()
    reset_storage()
    reset_config()


class TestDatasetStorage:

    def test_save_and_retrieve(self, storage):
        version = storage.save_dataset("test-ds", SAMPLE_ITEMS)
        assert version == 1

        dataset = storage.get_dataset("test-ds")
        assert dataset is not None
        assert dataset["name"] == "test-ds"
        assert dataset["version"] == 1
        assert dataset["items"] == SAMPLE_ITEMS
        assert dataset["created_at"] is not None

    def test_versioning(self, storage):
        v1 = storage.save_dataset("test-ds", SAMPLE_ITEMS)
        assert v1 == 1

        updated_items = SAMPLE_ITEMS + [
            {"input": "What is NLP?", "expected": "Natural language processing..."}
        ]
        v2 = storage.save_dataset("test-ds", updated_items)
        assert v2 == 2

        # get latest should return v2
        latest = storage.get_dataset("test-ds")
        assert latest["version"] == 2
        assert len(latest["items"]) == 3

        # get specific version should return v1
        first = storage.get_dataset("test-ds", version=1)
        assert first["version"] == 1
        assert len(first["items"]) == 2

    def test_list_datasets(self, storage):
        storage.save_dataset("ds-alpha", SAMPLE_ITEMS)
        storage.save_dataset("ds-beta", [{"input": "x", "expected": "y"}])
        storage.save_dataset("ds-alpha", SAMPLE_ITEMS + [{"input": "z", "expected": "w"}])

        datasets = storage.list_datasets()
        assert len(datasets) == 2

        alpha = next(d for d in datasets if d["name"] == "ds-alpha")
        assert alpha["latest_version"] == 2
        assert alpha["item_count"] == 3

        beta = next(d for d in datasets if d["name"] == "ds-beta")
        assert beta["latest_version"] == 1
        assert beta["item_count"] == 1

    def test_get_nonexistent(self, storage):
        assert storage.get_dataset("nope") is None
        assert storage.get_dataset("nope", version=1) is None

    def test_metadata(self, storage):
        meta = {"source": "production", "date": "2026-04-08"}
        storage.save_dataset("meta-ds", SAMPLE_ITEMS, metadata=meta)
        dataset = storage.get_dataset("meta-ds")
        assert dataset["metadata"] == meta


class TestDatasetRegistryAPI:

    def test_save_and_load(self):
        version = save_dataset("api-ds", SAMPLE_ITEMS)
        assert version == 1

        items = load_dataset("api-ds")
        assert items == SAMPLE_ITEMS

    def test_load_specific_version(self):
        save_dataset("api-ds", SAMPLE_ITEMS)
        save_dataset("api-ds", [{"input": "new", "expected": "data"}])

        v1_items = load_dataset("api-ds", version=1)
        assert len(v1_items) == 2

        v2_items = load_dataset("api-ds", version=2)
        assert len(v2_items) == 1

    def test_load_nonexistent_raises(self):
        with pytest.raises(ValueError, match="not found"):
            load_dataset("nonexistent")


class TestDatasetCLI:

    def test_save_from_file(self, tmp_path):
        f = tmp_path / "dataset.json"
        f.write_text(json.dumps(SAMPLE_ITEMS), encoding="utf-8")
        result = runner.invoke(app, ["dataset", "save", str(f), "--name", "cli-ds"])
        assert result.exit_code == 0
        assert "Saved" in result.output
        assert "2 items" in result.output

    def test_save_invalid_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json", encoding="utf-8")
        result = runner.invoke(app, ["dataset", "save", str(f), "--name", "bad"])
        assert result.exit_code == 1
        assert "Invalid JSON" in result.output

    def test_save_not_a_list(self, tmp_path):
        f = tmp_path / "obj.json"
        f.write_text('{"key": "value"}', encoding="utf-8")
        result = runner.invoke(app, ["dataset", "save", str(f), "--name", "bad"])
        assert result.exit_code == 1
        assert "list" in result.output

    def test_save_file_not_found(self):
        result = runner.invoke(app, ["dataset", "save", "nonexistent.json", "--name", "bad"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_list_empty(self):
        result = runner.invoke(app, ["dataset", "list"])
        assert result.exit_code == 0
        assert "No datasets" in result.output

    def test_list_with_data(self, tmp_path):
        f = tmp_path / "ds.json"
        f.write_text(json.dumps(SAMPLE_ITEMS), encoding="utf-8")
        runner.invoke(app, ["dataset", "save", str(f), "--name", "list-ds"])
        result = runner.invoke(app, ["dataset", "list"])
        assert result.exit_code == 0
        assert "list-ds" in result.output

    def test_show(self, tmp_path):
        f = tmp_path / "ds.json"
        f.write_text(json.dumps(SAMPLE_ITEMS), encoding="utf-8")
        runner.invoke(app, ["dataset", "save", str(f), "--name", "show-ds"])
        result = runner.invoke(app, ["dataset", "show", "show-ds"])
        assert result.exit_code == 0
        assert "What is ML?" in result.output
        assert "show-ds" in result.output

    def test_show_specific_version(self, tmp_path):
        f1 = tmp_path / "ds1.json"
        f1.write_text(json.dumps(SAMPLE_ITEMS), encoding="utf-8")
        runner.invoke(app, ["dataset", "save", str(f1), "--name", "ver-ds"])

        f2 = tmp_path / "ds2.json"
        f2.write_text(json.dumps([{"input": "new", "expected": "data"}]), encoding="utf-8")
        runner.invoke(app, ["dataset", "save", str(f2), "--name", "ver-ds"])

        result = runner.invoke(app, ["dataset", "show", "ver-ds", "--version", "1"])
        assert result.exit_code == 0
        assert "What is ML?" in result.output

    def test_show_not_found(self):
        result = runner.invoke(app, ["dataset", "show", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()
