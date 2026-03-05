"""SQLite storage backend.

Everything that touches the database lives here. Other modules go through
the Storage interface instead of importing sqlite3 directly.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from promptry.config import get_config
from promptry.models import PromptRecord, EvalRunRecord, EvalResultRecord
from promptry.storage.base import BaseStorage

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prompts (
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

CREATE TABLE IF NOT EXISTS prompt_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_id INTEGER NOT NULL,
    tag TEXT NOT NULL,
    FOREIGN KEY (prompt_id) REFERENCES prompts(id),
    UNIQUE(prompt_id, tag)
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    suite_name TEXT NOT NULL,
    prompt_name TEXT,
    prompt_version INTEGER,
    model_version TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    overall_pass INTEGER NOT NULL DEFAULT 1,
    overall_score REAL
);

CREATE TABLE IF NOT EXISTS eval_results (
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

CREATE INDEX IF NOT EXISTS idx_prompts_name ON prompts(name);
CREATE INDEX IF NOT EXISTS idx_prompts_hash ON prompts(hash);
CREATE INDEX IF NOT EXISTS idx_prompt_tags_tag ON prompt_tags(tag);
CREATE INDEX IF NOT EXISTS idx_eval_runs_suite ON eval_runs(suite_name);
CREATE INDEX IF NOT EXISTS idx_eval_results_run ON eval_results(run_id);
"""


class SQLiteStorage(BaseStorage):

    def __init__(self, db_path: Path | str | None = None):
        if db_path is None:
            db_path = get_config().storage.db_path
        self._db_path = Path(db_path).expanduser()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = self._connect()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __del__(self):
        try:
            self._conn.close()
        except Exception:
            pass

    # ---- prompts ----

    def save_prompt(self, name, content, content_hash, metadata=None) -> PromptRecord:
        with self._lock:
            cur = self._conn.cursor()

            # dedup: same name + same hash means same content, skip
            cur.execute(
                "SELECT * FROM prompts WHERE name = ? AND hash = ?",
                (name, content_hash),
            )
            row = cur.fetchone()
            if row:
                record = self._row_to_prompt(row)
                record.tags = self._get_tags_unlocked(cur, record.id)
                return record

            # atomic version increment + insert in one statement
            meta_json = json.dumps(metadata) if metadata else None
            cur.execute(
                """INSERT INTO prompts (name, version, content, hash, metadata)
                   VALUES (?, (SELECT COALESCE(MAX(version), 0) + 1 FROM prompts WHERE name = ?), ?, ?, ?)""",
                (name, name, content, content_hash, meta_json),
            )
            self._conn.commit()

            # re-read the row to get the version and created_at
            cur.execute("SELECT * FROM prompts WHERE id = ?", (cur.lastrowid,))
            return self._row_to_prompt(cur.fetchone())

    def get_prompt(self, name, version=None) -> PromptRecord | None:
        with self._lock:
            cur = self._conn.cursor()
            if version is not None:
                cur.execute(
                    "SELECT * FROM prompts WHERE name = ? AND version = ?",
                    (name, version),
                )
            else:
                cur.execute(
                    "SELECT * FROM prompts WHERE name = ? ORDER BY version DESC LIMIT 1",
                    (name,),
                )
            row = cur.fetchone()
            if not row:
                return None
            record = self._row_to_prompt(row)
            record.tags = self._get_tags_unlocked(cur, record.id)
            return record

    def get_prompt_by_tag(self, name, tag) -> PromptRecord | None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """SELECT p.* FROM prompts p
                   JOIN prompt_tags pt ON p.id = pt.prompt_id
                   WHERE p.name = ? AND pt.tag = ?
                   ORDER BY p.version DESC LIMIT 1""",
                (name, tag),
            )
            row = cur.fetchone()
            if not row:
                return None
            record = self._row_to_prompt(row)
            record.tags = self._get_tags_unlocked(cur, record.id)
            return record

    def list_prompts(self, name=None) -> list[PromptRecord]:
        with self._lock:
            cur = self._conn.cursor()
            if name:
                cur.execute(
                    """SELECT p.*, GROUP_CONCAT(pt.tag) as tags_csv
                       FROM prompts p LEFT JOIN prompt_tags pt ON p.id = pt.prompt_id
                       WHERE p.name = ? GROUP BY p.id ORDER BY p.version ASC""",
                    (name,),
                )
            else:
                cur.execute(
                    """SELECT p.*, GROUP_CONCAT(pt.tag) as tags_csv
                       FROM prompts p LEFT JOIN prompt_tags pt ON p.id = pt.prompt_id
                       GROUP BY p.id ORDER BY p.name, p.version ASC"""
                )
            records = []
            for row in cur.fetchall():
                record = self._row_to_prompt(row)
                tags_csv = row["tags_csv"]
                record.tags = tags_csv.split(",") if tags_csv else []
                records.append(record)
            return records

    def tag_prompt(self, prompt_id, tag):
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO prompt_tags (prompt_id, tag) VALUES (?, ?)",
                (prompt_id, tag),
            )
            self._conn.commit()

    def get_tags(self, prompt_id) -> list[str]:
        with self._lock:
            return self._get_tags_unlocked(self._conn.cursor(), prompt_id)

    def _get_tags_unlocked(self, cur, prompt_id) -> list[str]:
        """Get tags without acquiring the lock (caller must hold it)."""
        cur.execute(
            "SELECT tag FROM prompt_tags WHERE prompt_id = ?",
            (prompt_id,),
        )
        return [row[0] for row in cur.fetchall()]

    # ---- eval runs ----

    def save_eval_run(
        self,
        suite_name,
        prompt_name=None,
        prompt_version=None,
        model_version=None,
        overall_pass=True,
        overall_score=None,
    ) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO eval_runs
                   (suite_name, prompt_name, prompt_version, model_version, overall_pass, overall_score)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (suite_name, prompt_name, prompt_version, model_version, int(overall_pass), overall_score),
            )
            self._conn.commit()
            return cur.lastrowid

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
        with self._lock:
            details_json = json.dumps(details) if details else None
            cur = self._conn.execute(
                """INSERT INTO eval_results
                   (run_id, test_name, assertion_type, passed, score, details, latency_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (run_id, test_name, assertion_type, int(passed), score, details_json, latency_ms),
            )
            self._conn.commit()
            return cur.lastrowid

    def get_eval_runs(self, suite_name, limit=50) -> list[EvalRunRecord]:
        with self._lock:
            cur = self._conn.execute(
                """SELECT * FROM eval_runs
                   WHERE suite_name = ?
                   ORDER BY id DESC LIMIT ?""",
                (suite_name, limit),
            )
            return [self._row_to_eval_run(row) for row in cur.fetchall()]

    def get_eval_results(self, run_id) -> list[EvalResultRecord]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM eval_results WHERE run_id = ?",
                (run_id,),
            )
            return [self._row_to_eval_result(row) for row in cur.fetchall()]

    def get_score_history(self, suite_name, limit=30) -> list[tuple[str, float]]:
        with self._lock:
            cur = self._conn.execute(
                """SELECT timestamp, overall_score FROM eval_runs
                   WHERE suite_name = ? AND overall_score IS NOT NULL
                   ORDER BY id DESC LIMIT ?""",
                (suite_name, limit),
            )
            return [(row[0], row[1]) for row in cur.fetchall()]

    # ---- row converters ----

    def _row_to_prompt(self, row) -> PromptRecord:
        try:
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
        except (json.JSONDecodeError, TypeError):
            meta = {}
        return PromptRecord(
            id=row["id"],
            name=row["name"],
            version=row["version"],
            content=row["content"],
            hash=row["hash"],
            metadata=meta,
            created_at=row["created_at"],
        )

    def _row_to_eval_run(self, row) -> EvalRunRecord:
        return EvalRunRecord(
            id=row["id"],
            suite_name=row["suite_name"],
            prompt_name=row["prompt_name"],
            prompt_version=row["prompt_version"],
            model_version=row["model_version"],
            timestamp=row["timestamp"],
            overall_pass=bool(row["overall_pass"]),
            overall_score=row["overall_score"],
        )

    def _row_to_eval_result(self, row) -> EvalResultRecord:
        details = json.loads(row["details"]) if row["details"] else None
        return EvalResultRecord(
            id=row["id"],
            run_id=row["run_id"],
            test_name=row["test_name"],
            assertion_type=row["assertion_type"],
            passed=bool(row["passed"]),
            score=row["score"],
            details=details,
            latency_ms=row["latency_ms"],
        )
