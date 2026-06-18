"""SQLite connection pool with WAL mode and thread-safe checkout.

For this single-process Telegram bot, a small pool (default 5) reuses
connections and avoids opening/closing on every query. SQLite still allows
only one writer at a time; WAL mode improves concurrent read performance.
"""

from __future__ import annotations

import logging
import os
import queue
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

DEFAULT_DATABASE_PATH = "data/store.db"
DEFAULT_POOL_SIZE = 5

_pool: "ConnectionPool | None" = None
_pool_lock = threading.Lock()


def get_database_path() -> str:
    return os.getenv("DATABASE_PATH", DEFAULT_DATABASE_PATH)


def ensure_database_dir(path: str) -> None:
    parent = Path(path).parent
    if str(parent) not in ("", "."):
        parent.mkdir(parents=True, exist_ok=True)


def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")


class ConnectionPool:
    """Simple thread-safe pool of SQLite connections."""

    def __init__(self, path: str, size: int = DEFAULT_POOL_SIZE) -> None:
        self._path = path
        self._size = size
        self._queue: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=size)
        for _ in range(size):
            self._queue.put(self._create_connection())

    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        _configure_connection(conn)
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._queue.get()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._queue.put(conn)

    def close(self) -> None:
        while not self._queue.empty():
            conn = self._queue.get_nowait()
            conn.close()


def init_pool(path: str | None = None, size: int | None = None) -> ConnectionPool:
    global _pool
    db_path = path or get_database_path()
    pool_size = size or int(os.getenv("DATABASE_POOL_SIZE", DEFAULT_POOL_SIZE))
    ensure_database_dir(db_path)
    with _pool_lock:
        if _pool is not None:
            _pool.close()
        _pool = ConnectionPool(db_path, size=pool_size)
        logger.info("SQLite pool ready: %s (size=%d)", db_path, pool_size)
        return _pool


def get_pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return _pool


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    """Convenience wrapper around the global pool."""
    with get_pool().connection() as conn:
        yield conn
