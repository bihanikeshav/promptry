"""Storage backends for promptry.

Default is SQLite. The BaseStorage interface lets you plug in your own.
Storage mode (sync/async/off) is handled by get_storage().
"""
from promptry.storage.base import BaseStorage
from promptry.storage.sqlite import SQLiteStorage

# backwards compat
Storage = SQLiteStorage

_storage_instance: BaseStorage | None = None


def get_storage() -> BaseStorage:
    """Get the singleton storage instance based on the current config mode.

    - sync: direct SQLiteStorage (default)
    - async: SQLiteStorage wrapped in AsyncWriter (background thread)
    - off: should not be called (track() short-circuits before this)
    """
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    from promptry.config import get_config

    config = get_config()
    storage = SQLiteStorage()

    if config.storage.mode == "async":
        from promptry.writer import AsyncWriter
        storage = AsyncWriter(storage)

    _storage_instance = storage
    return storage


def reset_storage():
    """Close and discard the singleton storage instance."""
    global _storage_instance
    if _storage_instance is not None:
        _storage_instance.close()
    _storage_instance = None


__all__ = ["BaseStorage", "SQLiteStorage", "Storage", "get_storage", "reset_storage"]
