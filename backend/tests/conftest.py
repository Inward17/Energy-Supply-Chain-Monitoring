import os

import pytest
from sqlalchemy import text
from src.database.postgres_db import get_engine, init_schema
from src.database.neo4j_graph import get_driver, seed_graph

@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Ensure schema is initialized before any tests run."""
    init_schema()
    seed_graph()

@pytest.fixture(autouse=True)
def db_transaction(monkeypatch):
    """
    Wrap each test in a Postgres transaction and roll back at the end.
    This ensures tests don't mutate the database.
    """
    engine = get_engine()
    connection = engine.connect()
    transaction = connection.begin()
    
    # Mock get_conn to yield our connection instead
    import contextlib
    @contextlib.contextmanager
    def mock_get_conn():
        try:
            yield connection
        finally:
            pass # Transaction rollback handled below
            
    monkeypatch.setattr('src.database.postgres_db.get_conn', mock_get_conn)
    
    yield connection
    
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="session", autouse=True)
def neo4j_graph_available():
    """Ensure the knowledge graph is populated for tests that read it.

    This previously ran `MATCH (n) DETACH DELETE n` before *every* test against
    whatever NEO4J_URI pointed at — in practice the developer's live database.
    A run interrupted between the wipe and the re-seed left the graph empty,
    which silently breaks the Reroute Matrix and War Room until someone
    re-seeds by hand.

    `seed_graph()` is idempotent (MERGE-only) and returns early when already
    populated, so ensuring is enough; destroying was never necessary. Set
    NEO4J_ALLOW_TEST_WIPE=1 to opt into the old wipe-first behaviour, and only
    against a throwaway database.
    """
    driver = get_driver()
    if not driver:
        yield
        return

    if os.getenv("NEO4J_ALLOW_TEST_WIPE") == "1":
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    seed_graph()
    yield
    # Leave the graph usable for the app even if a test mutated it.
    seed_graph()
