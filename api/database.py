"""Database connections, reused through a small per-process pool.

Opening a connection to Supabase (TCP + TLS + auth, often cross-region) costs
far more than the queries most requests run, so finished connections are kept
and handed to the next request instead of being closed.

Routes keep the plain pattern `conn = get_connection() ... conn.close()`:
close() hands the connection back to the pool (rolled back to a clean state)
instead of closing it. Each gunicorn worker has its own pool, because the app
is imported separately in each worker.
"""
import atexit
import logging
import os
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
from dotenv import load_dotenv
from psycopg import pq

load_dotenv()

logger = logging.getLogger(__name__)

DB_URL = os.environ.get("SUPABASE_DB_URL")

# Idle connections kept per process. gunicorn runs 4 threads per worker, so 4
# covers every concurrent request; a request beyond that opens one more.
POOL_MAX_IDLE = int(os.environ.get("DB_POOL_MAX_IDLE", 4))
# Idle connections older than this are closed rather than reused.
POOL_IDLE_TIMEOUT = 300
# A connection idle longer than this is checked with one round trip before
# reuse, in case the server or the network dropped it meanwhile.
POOL_CHECK_AFTER = 30

_idle = []  # (connection, monotonic time it was returned), most recent last
_lock = threading.Lock()


def normalize_db_url(db_url):
    parts = urlsplit(db_url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    filtered_query = [(key, value) for key, value in query if key != "pgbouncer"]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(filtered_query), parts.fragment))


def _connect():
    if DB_URL:
        return psycopg.connect(normalize_db_url(DB_URL), autocommit=False, prepare_threshold=None)

    return psycopg.connect(
        dbname=os.environ.get("DB_NAME", "postgres"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "postgres"),
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
    )


def _discard(conn):
    try:
        conn.close()
    except Exception:
        pass


def _is_alive(conn):
    """One cheap round trip; False if the connection no longer works."""
    try:
        conn.autocommit = True
        conn.execute("")
        conn.autocommit = False
        return True
    except Exception:
        return False


def _release(conn):
    """Take a connection back: clean it up and keep it, or close it."""
    try:
        if conn.closed or conn.broken:
            _discard(conn)
            return
        if conn.info.transaction_status != pq.TransactionStatus.IDLE:
            conn.rollback()  # discard anything the caller left uncommitted
        if conn.autocommit:
            conn.autocommit = False
    except Exception:
        _discard(conn)
        return

    with _lock:
        if len(_idle) < POOL_MAX_IDLE:
            _idle.append((conn, time.monotonic()))
            return
    _discard(conn)


class PooledConnection:
    """A psycopg connection whose close() returns it to the pool.

    Everything else (cursor, execute, commit, rollback...) is the real
    connection's. close() may be called more than once; using the object after
    close() raises instead of touching a connection another request now owns.
    """

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        conn = self.__dict__.get("_conn")
        if conn is None:
            raise psycopg.InterfaceError("the connection was already returned to the pool")
        return getattr(conn, name)

    def close(self):
        conn, self._conn = self._conn, None
        if conn is not None:
            _release(conn)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        # Same contract as psycopg's own connection context manager.
        try:
            if self._conn is not None:
                if exc_type is None:
                    self._conn.commit()
                else:
                    self._conn.rollback()
        finally:
            self.close()

    def __del__(self):
        # Safety net for a code path that forgets close().
        try:
            self.close()
        except Exception:
            pass


def get_connection():
    while True:
        with _lock:
            item = _idle.pop() if _idle else None
        if item is None:
            return PooledConnection(_connect())

        conn, returned_at = item
        idle_for = time.monotonic() - returned_at
        if conn.closed or conn.broken or idle_for > POOL_IDLE_TIMEOUT:
            _discard(conn)
            continue
        if idle_for > POOL_CHECK_AFTER and not _is_alive(conn):
            logger.info("Dropping a pooled database connection that stopped responding")
            _discard(conn)
            continue
        return PooledConnection(conn)


def close_pool():
    """Close every idle connection (at exit, and between tests)."""
    with _lock:
        items = list(_idle)
        _idle.clear()
    for conn, _ in items:
        _discard(conn)


atexit.register(close_pool)
