import pytest


class TestPromptStorage:

    def test_basic_save(self, storage):
        record = storage.save_prompt("test", "Hello world", "abc123")
        assert record.name == "test"
        assert record.version == 1
        assert record.content == "Hello world"
        assert record.hash == "abc123"

    def test_auto_increment_version(self, storage):
        r1 = storage.save_prompt("test", "Version 1", "hash1")
        r2 = storage.save_prompt("test", "Version 2", "hash2")
        assert r1.version == 1
        assert r2.version == 2

    def test_dedup_same_content(self, storage):
        r1 = storage.save_prompt("test", "Same content", "same_hash")
        r2 = storage.save_prompt("test", "Same content", "same_hash")
        assert r1.version == r2.version
        assert r1.id == r2.id

    def test_metadata_roundtrip(self, storage):
        storage.save_prompt("test", "Content", "h1", metadata={"author": "keshav"})
        fetched = storage.get_prompt("test", 1)
        assert fetched.metadata == {"author": "keshav"}

    def test_get_latest(self, storage):
        storage.save_prompt("test", "V1", "h1")
        storage.save_prompt("test", "V2", "h2")
        latest = storage.get_prompt("test")
        assert latest.version == 2
        assert latest.content == "V2"

    def test_get_specific_version(self, storage):
        storage.save_prompt("test", "V1", "h1")
        storage.save_prompt("test", "V2", "h2")
        v1 = storage.get_prompt("test", 1)
        assert v1.content == "V1"

    def test_get_nonexistent(self, storage):
        assert storage.get_prompt("nope") is None

    def test_list_all(self, storage):
        storage.save_prompt("a", "Content A", "ha")
        storage.save_prompt("b", "Content B", "hb")
        records = storage.list_prompts()
        assert len(records) == 2
        assert {r.name for r in records} == {"a", "b"}

    def test_list_by_name(self, storage):
        storage.save_prompt("a", "V1", "h1")
        storage.save_prompt("a", "V2", "h2")
        storage.save_prompt("b", "Other", "h3")
        records = storage.list_prompts("a")
        assert len(records) == 2
        assert all(r.name == "a" for r in records)

    def test_tagging(self, storage):
        record = storage.save_prompt("test", "Content", "h1")
        storage.tag_prompt(record.id, "prod")
        assert "prod" in storage.get_tags(record.id)

    def test_duplicate_tag_ignored(self, storage):
        record = storage.save_prompt("test", "Content", "h1")
        storage.tag_prompt(record.id, "prod")
        storage.tag_prompt(record.id, "prod")
        assert storage.get_tags(record.id).count("prod") == 1

    def test_get_by_tag(self, storage):
        storage.save_prompt("test", "V1", "h1")
        r2 = storage.save_prompt("test", "V2", "h2")
        storage.tag_prompt(r2.id, "prod")
        found = storage.get_prompt_by_tag("test", "prod")
        assert found.version == 2


class TestEvalStorage:

    def test_save_run(self, storage):
        run_id = storage.save_eval_run(
            suite_name="regression",
            prompt_name="test",
            prompt_version=1,
            overall_pass=True,
            overall_score=0.95,
        )
        assert run_id > 0

    def test_save_and_fetch_results(self, storage):
        run_id = storage.save_eval_run(suite_name="regression", overall_pass=True)
        result_id = storage.save_eval_result(
            run_id=run_id,
            test_name="test_qa",
            assertion_type="semantic",
            passed=True,
            score=0.91,
            details={"threshold": 0.8},
            latency_ms=150.0,
        )
        assert result_id > 0

        results = storage.get_eval_results(run_id)
        assert len(results) == 1
        assert results[0].test_name == "test_qa"
        assert results[0].score == 0.91
        assert results[0].details == {"threshold": 0.8}

    def test_runs_ordered_newest_first(self, storage):
        storage.save_eval_run(suite_name="s1", overall_pass=True, overall_score=0.9)
        storage.save_eval_run(suite_name="s1", overall_pass=False, overall_score=0.7)
        runs = storage.get_eval_runs("s1")
        assert len(runs) == 2
        assert runs[0].overall_score == 0.7  # newest first

    def test_score_history(self, storage):
        storage.save_eval_run(suite_name="s1", overall_pass=True, overall_score=0.9)
        storage.save_eval_run(suite_name="s1", overall_pass=True, overall_score=0.85)
        history = storage.get_score_history("s1")
        assert len(history) == 2
        assert all(isinstance(s, float) for _, s in history)


class TestSuiteNames:

    def test_list_suite_names_empty(self, storage):
        assert storage.list_suite_names() == []

    def test_list_suite_names(self, storage):
        storage.save_eval_run(suite_name="alpha", overall_pass=True, overall_score=0.9)
        storage.save_eval_run(suite_name="beta", overall_pass=True, overall_score=0.8)
        storage.save_eval_run(suite_name="alpha", overall_pass=True, overall_score=0.85)
        names = storage.list_suite_names()
        assert sorted(names) == ["alpha", "beta"]


class TestGetRunById:

    def test_get_existing_run(self, storage):
        run_id = storage.save_eval_run(suite_name="test", overall_pass=True, overall_score=0.9)
        run = storage.get_eval_run_by_id(run_id)
        assert run is not None
        assert run.id == run_id
        assert run.suite_name == "test"

    def test_get_nonexistent_run(self, storage):
        assert storage.get_eval_run_by_id(9999) is None


class TestGetCostData:

    def test_cost_data_empty(self, storage):
        result = storage.get_cost_data(days=7)
        assert result["summary"]["total_calls"] == 0
        assert result["by_name"] == []

    def test_cost_data_with_metadata(self, storage):
        storage.save_prompt(name="my-prompt", content="test", content_hash="h1",
            metadata={"tokens_in": 500, "tokens_out": 100, "model": "gpt-4o", "cost": 0.005})
        storage.save_prompt(name="my-prompt", content="test2", content_hash="h2",
            metadata={"tokens_in": 300, "tokens_out": 50, "model": "gpt-4o", "cost": 0.003})
        result = storage.get_cost_data(days=7)
        assert result["summary"]["total_calls"] == 2
        assert result["summary"]["total_cost"] == pytest.approx(0.008)
        assert len(result["by_name"]) == 1
        assert result["by_name"][0]["name"] == "my-prompt"
        assert result["by_name"][0]["tokens_in"] == 800

    def test_cost_data_filter_by_name(self, storage):
        storage.save_prompt(name="a", content="x", content_hash="h1", metadata={"cost": 0.01})
        storage.save_prompt(name="b", content="y", content_hash="h2", metadata={"cost": 0.02})
        result = storage.get_cost_data(days=7, name="a")
        assert len(result["by_name"]) == 1
        assert result["by_name"][0]["name"] == "a"

    def test_cost_data_filter_by_model(self, storage):
        storage.save_prompt(name="p", content="x", content_hash="h1", metadata={"cost": 0.01, "model": "gpt-4o"})
        storage.save_prompt(name="p", content="y", content_hash="h2", metadata={"cost": 0.02, "model": "claude"})
        result = storage.get_cost_data(days=7, model="gpt-4o")
        assert result["summary"]["total_cost"] == pytest.approx(0.01)
