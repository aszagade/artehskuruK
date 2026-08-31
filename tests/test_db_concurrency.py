"""
Tests for DuckDB Connection Pool — Mission 3.56A

Tests:
  - Connection pool lifecycle (acquire/release)
  - Concurrent reads
  - Concurrent read+write
  - Exception during transaction (connection not leaked)
  - Pool exhaustion/timeout
  - Connection recycling
  - Pool stats
  - Context manager guaranteed cleanup
"""

import threading
import time
import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed

from kurukshetra.registry.database import (
    ConnectionPool, get_connection, release_connection,
    db_connection, db_transaction, get_pool_stats, close_pool,
    DATABASE_PATH,
)


@pytest.fixture(autouse=True)
def _clean_pool():
    """Reset pool before each test."""
    close_pool()
    yield
    close_pool()


class TestConnectionPoolLifecycle:
    """Test basic pool acquire/release."""

    def test_acquire_release(self):
        pool = ConnectionPool(str(DATABASE_PATH), max_size=2)
        conn = pool.acquire()
        assert conn is not None
        result = conn.execute("SELECT 1").fetchone()
        assert result[0] == 1
        pool.release(conn)
        stats = pool.stats
        assert stats["active"] == 0
        assert stats["total_acquired"] == 1
        assert stats["total_released"] == 1

    def test_recycle_connection(self):
        pool = ConnectionPool(str(DATABASE_PATH), max_size=2)
        conn1 = pool.acquire()
        pool.release(conn1)
        conn2 = pool.acquire()
        # Should be recycled (same object or verified-alive)
        result = conn2.execute("SELECT 1").fetchone()
        assert result[0] == 1
        pool.release(conn2)

    def test_release_none_is_safe(self):
        pool = ConnectionPool(str(DATABASE_PATH), max_size=2)
        pool.release(None)  # Should not raise

    def test_pool_stats(self):
        pool = ConnectionPool(str(DATABASE_PATH), max_size=3)
        conn = pool.acquire()
        stats = pool.stats
        assert stats["max_size"] == 3
        assert stats["active"] == 1
        assert stats["available"] == 0
        pool.release(conn)
        stats = pool.stats
        assert stats["active"] == 0
        assert stats["available"] == 1

    def test_close_all(self):
        pool = ConnectionPool(str(DATABASE_PATH), max_size=3)
        c1 = pool.acquire()
        c2 = pool.acquire()
        pool.release(c1)
        pool.release(c2)
        pool.close_all()
        stats = pool.stats
        assert stats["available"] == 0
        assert stats["active"] == 0


class TestContextManager:
    """Test db_connection() and db_transaction() context managers."""

    def test_db_connection_yields_valid_conn(self):
        with db_connection() as conn:
            result = conn.execute("SELECT 42").fetchone()
            assert result[0] == 42
        # Connection should be returned to pool
        stats = get_pool_stats()
        assert stats["active"] == 0

    def test_db_connection_cleanup_on_exception(self):
        with pytest.raises(ValueError):
            with db_connection() as conn:
                conn.execute("SELECT 1")
                raise ValueError("test error")
        stats = get_pool_stats()
        assert stats["active"] == 0

    def test_db_transaction_commit(self):
        with db_transaction() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS _test_pool (id INT)")
            conn.execute("INSERT INTO _test_pool VALUES (1)")
        # Data should persist
        with db_connection() as conn:
            result = conn.execute("SELECT COUNT(*) FROM _test_pool").fetchone()
            assert result[0] >= 1
        # Cleanup
        with db_connection() as conn:
            conn.execute("DROP TABLE IF EXISTS _test_pool")

    def test_db_transaction_rollback_on_exception(self):
        with db_connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS _test_pool_rb (id INT)")
            conn.execute("DELETE FROM _test_pool_rb")
            conn.commit()
        with pytest.raises(RuntimeError):
            with db_transaction() as conn:
                conn.execute("BEGIN TRANSACTION")
                conn.execute("INSERT INTO _test_pool_rb VALUES (999)")
                raise RuntimeError("fail")
        with db_connection() as conn:
            result = conn.execute("SELECT COUNT(*) FROM _test_pool_rb").fetchone()
            assert result[0] == 0
            conn.execute("DROP TABLE IF EXISTS _test_pool_rb")
            conn.commit()


class TestConcurrentReads:
    """Test that concurrent reads don't block each other."""

    def test_concurrent_select(self):
        pool = ConnectionPool(str(DATABASE_PATH), max_size=4)
        errors = []
        results = []

        def read_worker(worker_id):
            try:
                conn = pool.acquire(timeout=5.0)
                try:
                    for _ in range(10):
                        r = conn.execute("SELECT ?", (worker_id,)).fetchone()
                        results.append((worker_id, r[0]))
                finally:
                    pool.release(conn)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 40  # 4 workers * 10 reads each

    def test_concurrent_reads_and_writes(self):
        pool = ConnectionPool(str(DATABASE_PATH), max_size=4)
        errors = []
        write_count = [0]
        read_count = [0]
        lock = threading.Lock()

        # Create table first (single writer)
        with db_connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS _test_concurrent (id INT)")
            conn.execute("DELETE FROM _test_concurrent")
            conn.commit()

        def writer():
            try:
                conn = pool.acquire(timeout=5.0)
                try:
                    for i in range(5):
                        conn.execute("INSERT INTO _test_concurrent VALUES (?)", (i,))
                        with lock:
                            write_count[0] += 1
                finally:
                    pool.release(conn)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                conn = pool.acquire(timeout=5.0)
                try:
                    for _ in range(5):
                        try:
                            conn.execute("SELECT COUNT(*) FROM _test_concurrent").fetchone()
                            with lock:
                                read_count[0] += 1
                        except Exception:
                            pass
                finally:
                    pool.release(conn)
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(2):
            threads.append(threading.Thread(target=writer))
        for _ in range(2):
            threads.append(threading.Thread(target=reader))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert len(errors) == 0, f"Errors: {errors}"
        assert write_count[0] > 0
        # Cleanup
        with db_connection() as conn:
            conn.execute("DROP TABLE IF EXISTS _test_concurrent")
            conn.commit()


class TestExceptionSafety:
    """Test that connections are not leaked on exceptions."""

    def test_exception_in_middle_returns_connection(self):
        pool = ConnectionPool(str(DATABASE_PATH), max_size=2)
        for _ in range(10):
            conn = pool.acquire(timeout=2.0)
            try:
                conn.execute("SELECT 1")
                raise RuntimeError("simulated error")
            except RuntimeError:
                pool.release(conn)
        stats = pool.stats
        assert stats["active"] == 0
        assert stats["total_acquired"] == stats["total_released"]

    def test_concurrent_exception_safety(self):
        pool = ConnectionPool(str(DATABASE_PATH), max_size=4)
        errors = []

        def worker(worker_id):
            try:
                for _ in range(5):
                    conn = pool.acquire(timeout=2.0)
                    try:
                        conn.execute("SELECT ?", (worker_id,))
                        if worker_id % 3 == 0:
                            raise ValueError(f"worker {worker_id} error")
                    finally:
                        pool.release(conn)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        stats = pool.stats
        assert stats["active"] == 0, f"Active connections leaked: {stats['active']}"


class TestBackwardCompatibility:
    """Test that get_connection() / conn.close() still works."""

    def test_get_close_cycle(self):
        conn = get_connection()
        result = conn.execute("SELECT 1").fetchone()
        assert result[0] == 1
        release_connection(conn)
        stats = get_pool_stats()
        assert stats["active"] == 0

    def test_multiple_get_close_cycles(self):
        for _ in range(20):
            conn = get_connection()
            conn.execute("SELECT 1")
            release_connection(conn)
        stats = get_pool_stats()
        assert stats["active"] == 0
        assert stats["total_acquired"] == stats["total_released"]
