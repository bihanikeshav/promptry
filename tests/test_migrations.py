"""Tests for the lightweight schema migration system."""
import sqlite3

import pytest

from promptry.storage import Storage
from promptry.storage.sqlite import _MIGRATIONS, _SCHEMA_VERSION_DDL


class TestFreshDatabase:

    def test_all_migrations_applied(self, tmp_path):
        """A fresh DB should have all migrations applied."""
        db = Storage(db_path=tmp_path / "fresh.db")
        try:
            conn = db._conn
            cur = conn.execute("SELECT version, description FROM schema_version ORDER BY version")
            rows = cur.fetchall()
            assert len(rows) == len(_MIGRATIONS)
            for row, (expected_ver, expected_desc, _) in zip(rows, _MIGRATIONS):
                assert row["version"] == expected_ver
                assert row["description"] == expected_desc
        finally:
            db.close()

    def test_schema_version_has_applied_at(self, tmp_path):
        """Each migration row should have an applied_at timestamp."""
        db = Storage(db_path=tmp_path / "fresh.db")
        try:
            cur = db._conn.execute("SELECT applied_at FROM schema_version")
            for row in cur.fetchall():
                assert row["applied_at"] is not None
        finally:
            db.close()

    def test_tables_exist(self, tmp_path):
        """All expected tables should exist after migration."""
        db = Storage(db_path=tmp_path / "fresh.db")
        try:
            cur = db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = {row["name"] for row in cur.fetchall()}
            expected = {"prompts", "prompt_tags", "eval_runs", "eval_results",
                        "votes", "schema_version"}
            assert expected.issubset(tables)
        finally:
            db.close()


class TestExistingDatabase:

    def _create_legacy_db(self, db_path):
        """Simulate a pre-migration database that already has the tables
        but no schema_version table."""
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                version INTEGER NOT NULL,
                content TEXT NOT NULL,
                hash TEXT NOT NULL,
                metadata TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(name, version),
                UNIQUE(name, hash)
            );
            CREATE TABLE prompt_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_id INTEGER NOT NULL,
                tag TEXT NOT NULL,
                FOREIGN KEY (prompt_id) REFERENCES prompts(id),
                UNIQUE(prompt_id, tag)
            );
            CREATE TABLE eval_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                suite_name TEXT NOT NULL,
                prompt_name TEXT,
                prompt_version INTEGER,
                model_version TEXT,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                overall_pass INTEGER NOT NULL DEFAULT 1,
                overall_score REAL
            );
            CREATE TABLE eval_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                test_name TEXT NOT NULL,
                assertion_type TEXT NOT NULL,
                passed INTEGER NOT NULL,
                score REAL,
                details TEXT,
                latency_ms REAL,
                FOREIGN KEY (run_id) REFERENCES eval_runs(id)
            );
            CREATE TABLE votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_name TEXT NOT NULL,
                prompt_version INTEGER,
                response TEXT NOT NULL,
                score INTEGER NOT NULL,
                message TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO prompts (name, version, content, hash) VALUES ('legacy', 1, 'old content', 'oldhash');
        """)
        conn.commit()
        conn.close()

    def test_legacy_db_gets_migrated(self, tmp_path):
        """An existing DB (tables present, no schema_version) should be
        migrated without losing data."""
        db_path = tmp_path / "legacy.db"
        self._create_legacy_db(db_path)

        db = Storage(db_path=db_path)
        try:
            # schema_version should now exist and show version 1
            cur = db._conn.execute("SELECT MAX(version) FROM schema_version")
            assert cur.fetchone()[0] == len(_MIGRATIONS)

            # existing data should be intact
            prompt = db.get_prompt("legacy", 1)
            assert prompt is not None
            assert prompt.content == "old content"
        finally:
            db.close()

    def test_legacy_db_indexes_created(self, tmp_path):
        """Indexes should be created on the legacy DB."""
        db_path = tmp_path / "legacy.db"
        self._create_legacy_db(db_path)

        db = Storage(db_path=db_path)
        try:
            cur = db._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            )
            indexes = {row["name"] for row in cur.fetchall()}
            assert "idx_prompts_name" in indexes
            assert "idx_votes_prompt" in indexes
        finally:
            db.close()


class TestIdempotency:

    def test_migrations_idempotent(self, tmp_path):
        """Running migrations twice should not fail or duplicate rows."""
        db_path = tmp_path / "idem.db"
        db = Storage(db_path=db_path)
        db.save_prompt("test", "hello", "h1")
        db.close()

        # Open again -- _init_schema runs migrations again
        db2 = Storage(db_path=db_path)
        try:
            cur = db2._conn.execute("SELECT COUNT(*) FROM schema_version")
            assert cur.fetchone()[0] == len(_MIGRATIONS)

            # data should still be there
            prompt = db2.get_prompt("test", 1)
            assert prompt is not None
            assert prompt.content == "hello"
        finally:
            db2.close()

    def test_reopen_no_extra_rows(self, tmp_path):
        """Opening the DB multiple times should not add extra schema_version rows."""
        db_path = tmp_path / "multi.db"
        for _ in range(3):
            db = Storage(db_path=db_path)
            db.close()

        db = Storage(db_path=db_path)
        try:
            cur = db._conn.execute("SELECT COUNT(*) FROM schema_version")
            assert cur.fetchone()[0] == len(_MIGRATIONS)
        finally:
            db.close()
