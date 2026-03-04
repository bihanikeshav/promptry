import pytest
from promptry.registry import PromptRegistry, track, reset_registry


class TestPromptRegistry:

    def test_hash_is_deterministic(self):
        assert PromptRegistry.content_hash("hello") == PromptRegistry.content_hash("hello")

    def test_different_content_different_hash(self):
        assert PromptRegistry.content_hash("hello") != PromptRegistry.content_hash("world")

    def test_save_and_get(self, registry):
        registry.save("test", "My prompt content")
        fetched = registry.get("test")
        assert fetched.content == "My prompt content"
        assert fetched.version == 1

    def test_version_increments(self, registry):
        r1 = registry.save("test", "Version 1")
        r2 = registry.save("test", "Version 2")
        assert r1.version == 1
        assert r2.version == 2

    def test_dedup(self, registry):
        r1 = registry.save("test", "Same content")
        r2 = registry.save("test", "Same content")
        assert r1.version == r2.version

    def test_save_with_tag(self, registry):
        record = registry.save("test", "Content", tag="prod")
        assert "prod" in record.tags

    def test_get_by_tag(self, registry):
        registry.save("test", "V1", tag="old")
        registry.save("test", "V2", tag="prod")
        assert registry.get_by_tag("test", "prod").version == 2

    def test_tag_existing_version(self, registry):
        registry.save("test", "Content")
        registry.tag("test", 1, "prod")
        assert registry.get_by_tag("test", "prod").version == 1

    def test_tag_nonexistent_raises(self, registry):
        with pytest.raises(ValueError):
            registry.tag("nonexistent", 1, "prod")

    def test_list_all(self, registry):
        registry.save("a", "Content A")
        registry.save("b", "Content B")
        assert len(registry.list()) == 2

    def test_list_filtered(self, registry):
        registry.save("a", "V1")
        registry.save("a", "V2")
        registry.save("b", "Other")
        assert len(registry.list("a")) == 2

    def test_diff(self, registry):
        registry.save("test", "Line one\nLine two\n")
        registry.save("test", "Line one\nLine changed\n")
        diff = registry.diff("test", 1, 2)
        assert "-Line two" in diff
        assert "+Line changed" in diff

    def test_diff_shows_changes(self, registry):
        registry.save("test", "Same")
        registry.save("test", "Different")
        assert len(registry.diff("test", 1, 2)) > 0

    def test_diff_bad_version_raises(self, registry):
        registry.save("test", "Content")
        with pytest.raises(ValueError):
            registry.diff("test", 1, 99)

    def test_load_from_file(self, registry, tmp_path):
        f = tmp_path / "prompt.txt"
        f.write_text("File content", encoding="utf-8")
        assert registry.load_from_file(f) == "File content"


class TestTrack:

    def _patch_registry(self, monkeypatch, storage):
        monkeypatch.setattr(
            "promptry.registry._default_registry",
            PromptRegistry(storage=storage),
        )

    def test_returns_content_unchanged(self, storage, monkeypatch):
        self._patch_registry(monkeypatch, storage)
        assert track("Hello world", "test") == "Hello world"

    def test_saves_to_db(self, storage, monkeypatch):
        self._patch_registry(monkeypatch, storage)
        track("Hello world", "test")
        assert storage.get_prompt("test").content == "Hello world"

    def test_dedup_same_content(self, storage, monkeypatch):
        self._patch_registry(monkeypatch, storage)
        track("Same", "test")
        track("Same", "test")
        assert len(storage.list_prompts("test")) == 1

    def test_new_version_on_change(self, storage, monkeypatch):
        self._patch_registry(monkeypatch, storage)
        track("Version 1", "test")
        track("Version 2", "test")
        assert len(storage.list_prompts("test")) == 2

    def test_with_tag(self, storage, monkeypatch):
        self._patch_registry(monkeypatch, storage)
        track("Content", "test", tag="prod")
        record = storage.get_prompt("test")
        assert "prod" in storage.get_tags(record.id)
