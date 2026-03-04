"""Storage backends for promptry.

Default is SQLite. The BaseStorage interface lets you plug in your own.
"""
from promptry.storage.base import BaseStorage
from promptry.storage.sqlite import SQLiteStorage

# backwards compat -- old code imports "from promptry.storage import Storage"
Storage = SQLiteStorage

__all__ = ["BaseStorage", "SQLiteStorage", "Storage"]
