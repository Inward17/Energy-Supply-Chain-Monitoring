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

@pytest.fixture(autouse=True)
def clean_neo4j():
    """
    Clear Neo4j before each test and re-seed it so tests have a pristine graph.
    """
    driver = get_driver()
    if driver:
        with driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        seed_graph()
    yield
