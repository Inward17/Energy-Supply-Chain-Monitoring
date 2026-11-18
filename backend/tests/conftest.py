"""Test isolation.

Tests run against whatever database `backend/.env` points at, so this file
refuses anything that might be production before a single connection opens:

* Postgres must be local (localhost / 127.0.0.1 / ::1 / the compose service
  name) unless TEST_DB_ALLOW_REMOTE=1 says the remote one is disposable — CI
  sets it only for its per-PR Neon branch. Every test also runs inside a
  transaction that is rolled back.
* Neo4j is never the configured one. Tests use TEST_NEO4J_URI if set, otherwise
  a closed port, so the code exercises its seed-data fallback. There is no
  option to wipe a graph from the test suite.
"""
import contextlib
import os

import pytest
from dotenv import load_dotenv

load_dotenv()  # does not override variables already set in the environment

_LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "host.docker.internal"}


def _check_postgres_target() -> None:
    host = (os.getenv("DB_HOST") or "localhost").strip().lower()
    if host in _LOCAL_DB_HOSTS or os.getenv("TEST_DB_ALLOW_REMOTE") == "1":
        return
    pytest.exit(
        f"Refusing to run tests against remote Postgres host {host!r}. Point DB_HOST "
        "at a local database, or set TEST_DB_ALLOW_REMOTE=1 if it is disposable.",
        returncode=2,
    )


_check_postgres_target()
# Never the configured graph: a dedicated test instance, or none at all.
os.environ["NEO4J_URI"] = os.getenv("TEST_NEO4J_URI") or "bolt://127.0.0.1:9"
if os.getenv("TEST_NEO4J_URI"):
    os.environ["NEO4J_USER"] = os.getenv("TEST_NEO4J_USER", "neo4j")
    os.environ["NEO4J_PASSWORD"] = os.getenv("TEST_NEO4J_PASSWORD", "")

from src.database.postgres_db import get_engine, init_schema  # noqa: E402
from src.database.neo4j_graph import seed_graph  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Ensure schema exists (idempotent) and, with a test graph, seed it (MERGE-only)."""
    init_schema()
    seed_graph()


@pytest.fixture(autouse=True)
def db_transaction(monkeypatch):
    """Wrap each test in a Postgres transaction and roll it back afterwards."""
    engine = get_engine()
    connection = engine.connect()
    transaction = connection.begin()

    @contextlib.contextmanager
    def mock_get_conn():
        yield connection

    monkeypatch.setattr("src.database.postgres_db.get_conn", mock_get_conn)

    yield connection

    transaction.rollback()
    connection.close()
