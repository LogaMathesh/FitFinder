"""The connection pool in database.py: reuse, cleanup on return, and recovery."""
import psycopg
import pytest


@pytest.fixture
def database(app_modules, db):
    import database as database_module

    database_module.close_pool()
    yield database_module
    database_module.close_pool()


def backend_pid(conn):
    return conn.execute("SELECT pg_backend_pid()").fetchone()[0]


def test_connections_are_reused_across_requests(client, alice, database, monkeypatch):
    opened = []
    real_connect = database._connect

    def counting_connect():
        opened.append(1)
        return real_connect()

    monkeypatch.setattr(database, "_connect", counting_connect)

    for _ in range(10):
        assert client.get("/usage", headers=alice.headers).status_code == 200

    assert len(opened) == 1
    assert len(database._idle) == 1


def test_uncommitted_work_is_rolled_back_on_close(database, db):
    conn = database.get_connection()
    conn.execute("INSERT INTO users (username, password_hash) VALUES ('ghost', 'x')")
    conn.close()

    assert db.query("SELECT count(*) FROM users WHERE username = 'ghost'")[0][0] == 0
    reused = database.get_connection()
    assert reused.info.transaction_status == psycopg.pq.TransactionStatus.IDLE
    reused.close()


def test_connection_in_failed_transaction_is_usable_again(database):
    conn = database.get_connection()
    with pytest.raises(psycopg.errors.UndefinedTable):
        conn.execute("SELECT * FROM no_such_table")
    raw = conn._conn
    conn.close()

    reused = database.get_connection()
    assert reused._conn is raw  # kept, not thrown away
    assert reused.execute("SELECT 1").fetchone() == (1,)
    reused.close()


def test_close_twice_is_safe_and_use_after_close_raises(database):
    conn = database.get_connection()
    conn.close()
    conn.close()

    assert len(database._idle) == 1
    with pytest.raises(psycopg.InterfaceError):
        conn.cursor()


def test_context_manager_commits_and_returns(database, db):
    with database.get_connection() as conn:
        conn.execute("INSERT INTO users (username, password_hash) VALUES ('kept', 'x')")

    assert db.query("SELECT count(*) FROM users WHERE username = 'kept'")[0][0] == 1
    assert len(database._idle) == 1


def test_closed_idle_connection_is_replaced(database):
    conn = database.get_connection()
    raw = conn._conn
    conn.close()
    raw.close()  # e.g. dropped while sitting in the pool

    fresh = database.get_connection()
    assert fresh._conn is not raw
    assert fresh.execute("SELECT 1").fetchone() == (1,)
    fresh.close()


def test_server_side_disconnect_is_detected_before_reuse(database, db, monkeypatch):
    monkeypatch.setattr(database, "POOL_CHECK_AFTER", -1)  # always check on reuse

    conn = database.get_connection()
    pid = backend_pid(conn)
    conn.close()
    db.query("SELECT pg_terminate_backend(%s)", (pid,))

    fresh = database.get_connection()
    assert backend_pid(fresh) != pid
    fresh.close()


def test_pool_keeps_at_most_max_idle(database):
    conns = [database.get_connection() for _ in range(database.POOL_MAX_IDLE + 2)]
    for conn in conns:
        conn.close()

    assert len(database._idle) == database.POOL_MAX_IDLE
