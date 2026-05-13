import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import database.db as db_module


@pytest.fixture
def app():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    import app as flask_app
    flask_app.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    with flask_app.app.app_context():
        db_module.init_db()
        db_module.seed_db()
    yield flask_app.app
    db_module.DB_PATH = original
    os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def demo_user_id(app):
    conn = db_module.get_db()
    row = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
    ).fetchone()
    conn.close()
    return row["id"]


@pytest.fixture
def empty_user_id(app):
    db_module.create_user("Empty User", "empty@spendly.com", "password123")
    conn = db_module.get_db()
    row = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("empty@spendly.com",)
    ).fetchone()
    conn.close()
    return row["id"]


def do_login(client, email="demo@spendly.com", password="demo123"):
    return client.post("/login", data={"email": email, "password": password})
