"""Abstract storage interface.

Implement this to use a different backend (Postgres, Mongo, etc.).
The only requirement is that your backend can handle the methods below.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from promptry.models import PromptRecord, EvalRunRecord, EvalResultRecord


class BaseStorage(ABC):

    # ---- prompts ----

    @abstractmethod
    def save_prompt(self, name, content, content_hash, metadata=None) -> PromptRecord:
        ...

    @abstractmethod
    def get_prompt(self, name, version=None) -> PromptRecord | None:
        ...

    @abstractmethod
    def get_prompt_by_tag(self, name, tag) -> PromptRecord | None:
        ...

    @abstractmethod
    def list_prompts(self, name=None) -> list[PromptRecord]:
        ...

    @abstractmethod
    def tag_prompt(self, prompt_id, tag):
        ...

    @abstractmethod
    def get_tags(self, prompt_id) -> list[str]:
        ...

    # ---- eval runs ----

    @abstractmethod
    def save_eval_run(
        self,
        suite_name,
        prompt_name=None,
        prompt_version=None,
        model_version=None,
        overall_pass=True,
        overall_score=None,
    ) -> int:
        ...

    @abstractmethod
    def save_eval_result(
        self,
        run_id,
        test_name,
        assertion_type,
        passed,
        score=None,
        details=None,
        latency_ms=None,
    ) -> int:
        ...

    @abstractmethod
    def get_eval_runs(self, suite_name, limit=50) -> list[EvalRunRecord]:
        ...

    @abstractmethod
    def get_eval_results(self, run_id) -> list[EvalResultRecord]:
        ...

    @abstractmethod
    def get_score_history(self, suite_name, limit=30) -> list[tuple[str, float]]:
        ...

    @abstractmethod
    def close(self):
        ...
