"""Storage backends for promptry.

Default is SQLite. The BaseStorage interface lets you plug in your own.
Storage mode (sync/async/off) is handled by get_storage().
"""
from promptry.storage.base import BaseStorage
from promptry.storage.sqlite import SQLiteStorage

# backwards compat
Storage = SQLiteStorage


def get_storage() -> BaseStorage:
    """Get a storage instance based on the current config mode.

    - sync: direct SQLiteStorage (default)
    - async: SQLiteStorage wrapped in AsyncWriter (background thread)
    - off: should not be called (track() short-circuits before this)
    """
    from promptry.config import get_config

    config = get_config()
    storage = SQLiteStorage()

    if config.storage.mode == "async":
        from promptry.writer import AsyncWriter
        return AsyncWriter(storage)

    return storage


__all__ = ["BaseStorage", "SQLiteStorage", "Storage", "get_storage"]
