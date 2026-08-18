"""Checkpointing: persistence, resume, and time-travel.

A checkpoint is a snapshot of (state, trajectory, step) at the end of a step.
The engine writes one per step when a ``thread_id`` and ``checkpointer`` are
supplied. Checkpoints enable: survival across runs, human-in-the-loop resume,
and time-travel inspection (read the state at any past step).
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class Checkpoint:
    """A single state snapshot on a thread's timeline."""

    checkpoint_id: str
    thread_id: str
    step: int
    state: dict
    trajectory: list[str]
    step_groups: list[list[str]]
    parent_id: Optional[str]
    terminated_by: Optional[str] = None


class Checkpointer(ABC):
    """Stores and retrieves checkpoints keyed by thread."""

    @abstractmethod
    def put(self, cp: Checkpoint) -> None:
        """Insert or update (by checkpoint_id) a checkpoint."""

    @abstractmethod
    def get(self, thread_id: str, checkpoint_id: Optional[str] = None) -> Optional[Checkpoint]:
        """Return the checkpoint; the latest for the thread if id is None."""

    @abstractmethod
    def list(self, thread_id: str) -> list[Checkpoint]:
        """All checkpoints for a thread, oldest first."""


class InMemoryCheckpointer(Checkpointer):
    """Process-lifetime checkpointer (no dependencies)."""

    def __init__(self):
        self._db: dict[str, dict[str, Checkpoint]] = {}
        self._order: dict[str, list[str]] = {}

    def put(self, cp: Checkpoint) -> None:
        thread = self._db.setdefault(cp.thread_id, {})
        if cp.checkpoint_id not in thread:
            self._order.setdefault(cp.thread_id, []).append(cp.checkpoint_id)
        thread[cp.checkpoint_id] = cp

    def get(self, thread_id: str, checkpoint_id: Optional[str] = None) -> Optional[Checkpoint]:
        thread = self._db.get(thread_id, {})
        if checkpoint_id is not None:
            return thread.get(checkpoint_id)
        order = self._order.get(thread_id, [])
        return thread[order[-1]] if order else None

    def list(self, thread_id: str) -> list[Checkpoint]:
        thread = self._db.get(thread_id, {})
        return [thread[cid] for cid in self._order.get(thread_id, [])]


class SqliteCheckpointer(Checkpointer):
    """File-backed checkpointer (stdlib sqlite3). State values must be JSON-able.

    Safe to use from the async engine (and other threads): the connection is
    opened with ``check_same_thread=False`` in WAL mode and every statement is
    serialized through a lock.

    Args:
        path: database file; ``None`` uses a fresh temp file (good for tests).
    """

    def __init__(self, path: Optional[str] = None):
        self.path = path or tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    thread_id      TEXT,
                    checkpoint_id  TEXT,
                    step           INTEGER,
                    state          TEXT,
                    trajectory     TEXT,
                    step_groups    TEXT,
                    parent_id      TEXT,
                    terminated_by  TEXT,
                    PRIMARY KEY (thread_id, checkpoint_id)
                )
                """
            )
            self._conn.commit()

    def put(self, cp: Checkpoint) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO checkpoints
                (thread_id, checkpoint_id, step, state, trajectory, step_groups,
                 parent_id, terminated_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cp.thread_id, cp.checkpoint_id, cp.step,
                    json.dumps(cp.state), json.dumps(cp.trajectory),
                    json.dumps(cp.step_groups), cp.parent_id, cp.terminated_by,
                ),
            )
            self._conn.commit()

    def _row_to_cp(self, row) -> Checkpoint:
        return Checkpoint(
            checkpoint_id=row[1], thread_id=row[0], step=row[2],
            state=json.loads(row[3]), trajectory=json.loads(row[4]),
            step_groups=json.loads(row[5]), parent_id=row[6],
            terminated_by=row[7],
        )

    def get(self, thread_id: str, checkpoint_id: Optional[str] = None) -> Optional[Checkpoint]:
        with self._lock:
            if checkpoint_id is not None:
                cur = self._conn.execute(
                    "SELECT * FROM checkpoints WHERE thread_id=? AND checkpoint_id=?",
                    (thread_id, checkpoint_id),
                )
            else:
                cur = self._conn.execute(
                    "SELECT * FROM checkpoints WHERE thread_id=? ORDER BY step DESC, rowid DESC LIMIT 1",
                    (thread_id,),
                )
            row = cur.fetchone()
        return self._row_to_cp(row) if row else None

    def list(self, thread_id: str) -> list[Checkpoint]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM checkpoints WHERE thread_id=? ORDER BY step ASC, rowid ASC",
                (thread_id,),
            )
            rows = cur.fetchall()
        return [self._row_to_cp(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class MySqlCheckpointer(Checkpointer):
    """MySQL-backed checkpointer (optional; needs ``PyMySQL`` + a server).

    Same schema and semantics as ``SqliteCheckpointer`` (state values must be
    JSON-able), in MySQL dialect (``REPLACE INTO``, ``%s`` params). A single
    connection is serialized through a lock; for high-concurrency deployments
    inject a pooled ``conn`` and keep one checkpointer per worker.

    Args:
        host / port / user / password / database: server coordinates.
        table: table name (created if missing).
        conn: an existing DB-API connection (overrides the coordinates);
            must expose ``cursor()`` whose cursors yield tuple rows.
    """

    _COLS = ("thread_id, checkpoint_id, step, state, trajectory,"
             " step_groups, parent_id, terminated_by")

    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        user: str = "root",
        password: str = "",
        database: str = "fullspace",
        table: str = "checkpoints",
        conn: Any = None,
    ):
        if conn is None:
            try:
                import pymysql
            except ImportError as e:  # pragma: no cover
                raise ImportError(
                    "MySqlCheckpointer needs PyMySQL: pip install fullspace[cp-mysql]"
                ) from e
            conn = pymysql.connect(
                host=host, port=port, user=user, password=password, database=database,
            )
        self._conn = conn
        self._table = table
        self._lock = threading.Lock()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS `{table}` (
                    thread_id      VARCHAR(255) NOT NULL,
                    checkpoint_id  VARCHAR(64)  NOT NULL,
                    step           INT NOT NULL,
                    state          JSON NOT NULL,
                    trajectory     JSON NOT NULL,
                    step_groups    JSON NOT NULL,
                    parent_id      VARCHAR(64),
                    terminated_by  VARCHAR(32),
                    PRIMARY KEY (thread_id, checkpoint_id)
                )
            """)
            self._conn.commit()
            cur.close()

    def put(self, cp: Checkpoint) -> None:
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                f"REPLACE INTO `{self._table}` ({self._COLS})"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    cp.thread_id, cp.checkpoint_id, cp.step,
                    json.dumps(cp.state), json.dumps(cp.trajectory),
                    json.dumps(cp.step_groups), cp.parent_id, cp.terminated_by,
                ),
            )
            self._conn.commit()
            cur.close()

    def _select(self, sql: str, params: tuple):
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            rows = cur.fetchall()
            cur.close()
        return rows

    def get(self, thread_id: str, checkpoint_id: Optional[str] = None) -> Optional[Checkpoint]:
        if checkpoint_id is not None:
            rows = self._select(
                f"SELECT {self._COLS} FROM `{self._table}`"
                " WHERE thread_id=%s AND checkpoint_id=%s",
                (thread_id, checkpoint_id),
            )
        else:
            rows = self._select(
                f"SELECT {self._COLS} FROM `{self._table}`"
                " WHERE thread_id=%s ORDER BY step DESC, checkpoint_id DESC LIMIT 1",
                (thread_id,),
            )
        return self._row_to_cp(rows[0]) if rows else None

    def list(self, thread_id: str) -> list[Checkpoint]:
        rows = self._select(
            f"SELECT {self._COLS} FROM `{self._table}`"
            " WHERE thread_id=%s ORDER BY step ASC, checkpoint_id ASC",
            (thread_id,),
        )
        return [self._row_to_cp(r) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _row_to_cp(self, row) -> Checkpoint:
        # SELECT column order == _COLS order (tuple rows, DB-API default).
        return Checkpoint(
            checkpoint_id=row[1], thread_id=row[0], step=row[2],
            state=json.loads(row[3]), trajectory=json.loads(row[4]),
            step_groups=json.loads(row[5]), parent_id=row[6],
            terminated_by=row[7],
        )
