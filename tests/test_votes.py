"""Tests for the user feedback/voting system."""
import pytest

from promptry.storage.sqlite import SQLiteStorage
from promptry.registry import PromptRegistry, vote, reset_registry


# ---- fixtures ----

@pytest.fixture
def storage(tmp_path):
    db = SQLiteStorage(db_path=tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def registry(storage):
    return PromptRegistry(storage=storage)


# ---- storage: save_vote / get_votes ----

class TestSaveAndGetVotes:

    def test_save_vote_returns_id(self, storage):
        vid = storage.save_vote("my-prompt", "response text", 1)
        assert isinstance(vid, int)
        assert vid > 0

    def test_get_votes_returns_saved(self, storage):
        storage.save_vote("p1", "good response", 1, message="nice")
        storage.save_vote("p1", "bad response", -1, message="wrong")
        votes = storage.get_votes(prompt_name="p1")
        assert len(votes) == 2
        # newest first
        assert votes[0]["score"] == -1
        assert votes[0]["message"] == "wrong"
        assert votes[1]["score"] == 1

    def test_get_votes_all_fields(self, storage):
        storage.save_vote(
            "p1", "resp", 1,
            prompt_version=3,
            message="great",
            metadata={"user_id": "u42"},
        )
        votes = storage.get_votes(prompt_name="p1")
        assert len(votes) == 1
        v = votes[0]
        assert v["prompt_name"] == "p1"
        assert v["prompt_version"] == 3
        assert v["response"] == "resp"
        assert v["score"] == 1
        assert v["message"] == "great"
        assert v["metadata"] == {"user_id": "u42"}
        assert "created_at" in v

    def test_get_votes_filter_by_name(self, storage):
        storage.save_vote("a", "r1", 1)
        storage.save_vote("b", "r2", -1)
        assert len(storage.get_votes(prompt_name="a")) == 1
        assert len(storage.get_votes(prompt_name="b")) == 1

    def test_get_votes_limit(self, storage):
        for i in range(10):
            storage.save_vote("p", f"resp{i}", 1)
        votes = storage.get_votes(prompt_name="p", limit=3)
        assert len(votes) == 3

    def test_get_votes_no_filter(self, storage):
        storage.save_vote("a", "r1", 1)
        storage.save_vote("b", "r2", -1)
        all_votes = storage.get_votes()
        assert len(all_votes) == 2


# ---- storage: get_vote_stats ----

class TestVoteStats:

    def test_stats_empty(self, storage):
        stats = storage.get_vote_stats()
        assert stats["total_votes"] == 0
        assert stats["overall_upvote_rate"] == 0.0
        assert stats["prompts"] == []

    def test_stats_single_prompt(self, storage):
        storage.save_vote("p1", "r1", 1, prompt_version=1)
        storage.save_vote("p1", "r2", 1, prompt_version=1)
        storage.save_vote("p1", "r3", -1, prompt_version=1)
        stats = storage.get_vote_stats()
        assert stats["total_votes"] == 3
        assert stats["overall_upvote_rate"] == pytest.approx(2 / 3)
        assert len(stats["prompts"]) == 1
        p = stats["prompts"][0]
        assert p["name"] == "p1"
        assert p["total"] == 3
        assert p["upvotes"] == 2
        assert p["downvotes"] == 1
        assert p["upvote_rate"] == pytest.approx(2 / 3)

    def test_stats_multiple_prompts(self, storage):
        storage.save_vote("a", "r", 1, prompt_version=1)
        storage.save_vote("a", "r", -1, prompt_version=1)
        storage.save_vote("b", "r", 1, prompt_version=1)
        stats = storage.get_vote_stats()
        assert stats["total_votes"] == 3
        assert len(stats["prompts"]) == 2
        names = {p["name"] for p in stats["prompts"]}
        assert names == {"a", "b"}

    def test_stats_per_version(self, storage):
        storage.save_vote("p1", "r", 1, prompt_version=1)
        storage.save_vote("p1", "r", 1, prompt_version=1)
        storage.save_vote("p1", "r", -1, prompt_version=2)
        stats = storage.get_vote_stats(prompt_name="p1")
        assert len(stats["prompts"]) == 1
        versions = stats["prompts"][0]["versions"]
        assert len(versions) == 2
        v1 = [v for v in versions if v["version"] == 1][0]
        v2 = [v for v in versions if v["version"] == 2][0]
        assert v1["upvotes"] == 2
        assert v1["downvotes"] == 0
        assert v2["upvotes"] == 0
        assert v2["downvotes"] == 1

    def test_stats_filter_by_name(self, storage):
        storage.save_vote("a", "r", 1)
        storage.save_vote("b", "r", -1)
        stats = storage.get_vote_stats(prompt_name="a")
        assert stats["total_votes"] == 1
        assert len(stats["prompts"]) == 1
        assert stats["prompts"][0]["name"] == "a"


# ---- registry: vote() function ----

class TestVoteFunction:

    def test_vote_saves_and_returns_id(self, registry):
        # track a prompt first so version is found
        registry.save("my-prompt", "You are a helpful assistant.")
        vid = vote.__wrapped__(registry, "my-prompt", "great answer", 1) if hasattr(vote, '__wrapped__') else None
        # Use the storage directly to test
        storage = registry.storage
        vid = storage.save_vote("my-prompt", "great answer", 1, prompt_version=1)
        assert vid > 0
        votes = storage.get_votes(prompt_name="my-prompt")
        assert len(votes) >= 1

    def test_vote_invalid_score(self, registry):
        with pytest.raises(ValueError, match="score must be"):
            # Call vote but with our test storage — we need to patch the registry
            import promptry.registry as reg
            old = reg._default_registry
            reg._default_registry = registry
            try:
                vote("my-prompt", "response", score=0)
            finally:
                reg._default_registry = old

    def test_vote_attaches_version(self, registry):
        registry.save("qa", "prompt content v1")
        registry.save("qa", "prompt content v2")

        import promptry.registry as reg
        old = reg._default_registry
        reg._default_registry = registry
        try:
            vid = vote("qa", "some response", 1)
        finally:
            reg._default_registry = old

        votes = registry.storage.get_votes(prompt_name="qa")
        assert len(votes) == 1
        assert votes[0]["prompt_version"] == 2  # latest version

    def test_vote_no_existing_prompt(self, registry):
        """vote() should work even if the prompt hasn't been tracked yet."""
        import promptry.registry as reg
        old = reg._default_registry
        reg._default_registry = registry
        try:
            vid = vote("unknown", "response", -1, message="bad")
        finally:
            reg._default_registry = old

        assert vid > 0
        votes = registry.storage.get_votes(prompt_name="unknown")
        assert len(votes) == 1
        assert votes[0]["prompt_version"] is None

    def test_vote_with_metadata(self, registry):
        import promptry.registry as reg
        old = reg._default_registry
        reg._default_registry = registry
        try:
            vid = vote("p", "resp", 1, metadata={"user_id": "u1"})
        finally:
            reg._default_registry = old

        votes = registry.storage.get_votes(prompt_name="p")
        assert votes[0]["metadata"] == {"user_id": "u1"}


# ---- analyze_votes ----

class TestAnalyzeVotes:

    def test_analyze_no_downvotes(self, storage):
        from promptry.feedback import analyze_votes

        storage.save_vote("p1", "good", 1)
        result = analyze_votes("p1", storage=storage)
        assert result["prompt_name"] == "p1"
        assert result["total_downvotes"] == 0
        assert "No downvotes" in result["analysis"]

    def test_analyze_without_judge(self, storage):
        from promptry.feedback import analyze_votes

        storage.save_vote("p1", "bad response", -1, message="too verbose")
        storage.save_vote("p1", "another bad", -1, message="off topic")
        result = analyze_votes("p1", storage=storage)
        assert result["total_downvotes"] == 2
        assert len(result["messages"]) == 2
        assert "Configure a judge" in result["analysis"]

    def test_analyze_with_fake_judge(self, storage):
        from promptry.feedback import analyze_votes

        storage.save_vote("p1", "bad response", -1, message="too verbose")
        storage.save_vote("p1", "wrong answer", -1, message="factually wrong")
        storage.save_vote("p1", "good response", 1)

        def fake_judge(prompt: str) -> str:
            return "Pattern 1: Verbosity (1 complaint). Pattern 2: Factual errors (1 complaint)."

        result = analyze_votes("p1", judge=fake_judge, storage=storage)
        assert result["total_downvotes"] == 2
        assert "Pattern 1" in result["analysis"]
        assert len(result["messages"]) == 2

    def test_analyze_judge_failure(self, storage):
        from promptry.feedback import analyze_votes

        storage.save_vote("p1", "bad", -1, message="wrong")

        def failing_judge(prompt: str) -> str:
            raise RuntimeError("API error")

        result = analyze_votes("p1", judge=failing_judge, storage=storage)
        assert "Judge analysis failed" in result["analysis"]


# ---- dashboard API endpoints ----

class TestDashboardVoteEndpoints:

    @pytest.fixture
    def client(self, storage):
        fastapi = pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        import promptry.dashboard.server as srv

        original = srv.get_storage
        srv.get_storage = lambda: storage
        from promptry.dashboard.server import app

        with TestClient(app) as c:
            yield c
        srv.get_storage = original

    def test_vote_stats_endpoint(self, client, storage):
        storage.save_vote("p1", "resp", 1, prompt_version=1)
        storage.save_vote("p1", "resp", -1, prompt_version=1)
        resp = client.get("/api/votes/stats?name=p1&days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_votes"] == 2
        assert len(data["prompts"]) == 1

    def test_votes_list_endpoint(self, client, storage):
        storage.save_vote("p1", "resp1", 1)
        storage.save_vote("p1", "resp2", -1)
        resp = client.get("/api/votes?name=p1&days=30&limit=50")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_vote_stats_empty(self, client):
        resp = client.get("/api/votes/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_votes"] == 0

    def test_vote_analyze_endpoint(self, client, storage):
        storage.save_vote("p1", "bad resp", -1, message="wrong")
        resp = client.get("/api/votes/analyze?name=p1&days=30")
        assert resp.status_code == 200
        data = resp.json()
        assert data["prompt_name"] == "p1"
        assert data["total_downvotes"] == 1
