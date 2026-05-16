import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = "spendly.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    NOT NULL,
            email         TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            amount      REAL    NOT NULL,
            category    TEXT    NOT NULL,
            date        TEXT    NOT NULL,
            description TEXT,
            created_at  TEXT    DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()


def create_user(name, email, password):
    conn = get_db()
    pw_hash = generate_password_hash(password)
    conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        (name, email, pw_hash),
    )
    conn.commit()
    conn.close()


def get_user_by_email(email):
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    return user


def insert_expense(user_id, amount, category, expense_date, description):
    conn = get_db()
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, category, expense_date, description),
    )
    conn.commit()
    conn.close()


def seed_db():
    conn = get_db()
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        conn.close()
        return

    cursor = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
        ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
    )
    user_id = cursor.lastrowid

    expenses = [
        (user_id, 45.50,  "Food",          "2026-05-01", "Grocery shopping"),
        (user_id, 15.00,  "Transport",     "2026-05-02", "Bus pass"),
        (user_id, 120.00, "Bills",         "2026-05-03", "Electricity bill"),
        (user_id, 30.00,  "Health",        "2026-05-04", "Vitamins"),
        (user_id, 25.00,  "Entertainment", "2026-05-05", "Movie tickets"),
        (user_id, 60.00,  "Shopping",      "2026-05-06", "New shirt"),
        (user_id, 10.00,  "Other",         "2026-05-07", "Miscellaneous"),
        (user_id, 55.00,  "Food",          "2026-05-07", "Restaurant dinner"),
    ]
    conn.executemany(
        "INSERT INTO expenses (user_id, amount, category, date, description) VALUES (?, ?, ?, ?, ?)",
        expenses,
    )
    conn.commit()
    conn.close()
