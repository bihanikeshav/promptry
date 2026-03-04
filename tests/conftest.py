import pytest
from promptry.storage import Storage
from promptry.registry import PromptRegistry, reset_registry
from promptry.config import reset_config
from promptry.evaluator import clear_suites


@pytest.fixture
def storage(tmp_path):
    db = Storage(db_path=tmp_path / "test.db")
    yield db
    db.close()


@pytest.fixture
def registry(storage):
    return PromptRegistry(storage=storage)


@pytest.fixture(autouse=True)
def clean_state():
    reset_registry()
    reset_config()
    clear_suites()
    yield
    reset_registry()
    reset_config()
    clear_suites()
