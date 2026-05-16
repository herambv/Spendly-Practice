"""
Tests for Step 07 — Add Expense feature.

Covers:
- Auth guard (GET and POST) — unauthenticated requests redirect to /login
- GET renders form with Amount, Category, Date, Description fields
- Date field defaults to today's ISO date (YYYY-MM-DD)
- All allowed categories appear in the rendered form
- Valid POST inserts a DB row and redirects 302 to /profile
- Flash message "Expense added successfully." appears after redirect
- Submitted description appears on profile page after successful add
- Optional description: valid submission with empty description redirects
- DB side effect: raw query confirms user_id, amount, category, date
- Amount validation: missing, zero, negative, non-numeric all return 200 + error
- Field preservation: invalid amount → category/date/description still in response
- Category validation: invalid string and empty/missing category return 200 + error
- Date validation: non-date string and empty date return 200 + error
"""

import datetime
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import database.db as db_module
from tests.conftest import do_login


# ------------------------------------------------------------------ #
# Constants                                                           #
# ------------------------------------------------------------------ #

TODAY_STR = datetime.date.today().isoformat()

ALLOWED_CATEGORIES = [
    "Food", "Transport", "Bills", "Health",
    "Entertainment", "Shopping", "Other",
]

VALID_FORM = {
    "amount":      "42.50",
    "category":    "Food",
    "date":        TODAY_STR,
    "description": "Test expense",
}


# ------------------------------------------------------------------ #
# Fixtures                                                            #
# ------------------------------------------------------------------ #

@pytest.fixture
def app():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    original = db_module.DB_PATH
    db_module.DB_PATH = db_path
    import app as flask_app_module
    flask_app_module.app.config.update(TESTING=True, SECRET_KEY="test-secret")
    with flask_app_module.app.app_context():
        db_module.init_db()
        db_module.seed_db()
    yield flask_app_module.app
    db_module.DB_PATH = original
    os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """Test client already logged in as the seeded demo user."""
    do_login(client)
    return client


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_get_while_logged_out_redirects(self, client):
        resp = client.get("/expenses/add")
        assert resp.status_code == 302, (
            "GET /expenses/add while logged out must return 302"
        )
        assert "/login" in resp.headers["Location"], (
            "Redirect must point to /login"
        )

    def test_post_while_logged_out_redirects(self, client):
        resp = client.post("/expenses/add", data=VALID_FORM)
        assert resp.status_code == 302, (
            "POST /expenses/add while logged out must return 302"
        )
        assert "/login" in resp.headers["Location"], (
            "Redirect must point to /login"
        )

    def test_get_while_logged_out_does_not_return_200(self, client):
        resp = client.get("/expenses/add")
        assert resp.status_code != 200, (
            "Unauthenticated GET must not render the form"
        )

    def test_post_while_logged_out_does_not_insert_row(self, client):
        client.post("/expenses/add", data=VALID_FORM)
        conn = db_module.get_db()
        row = conn.execute(
            "SELECT id FROM expenses WHERE description = ?",
            ("Test expense",),
        ).fetchone()
        conn.close()
        assert row is None, (
            "An unauthenticated POST must not insert any row into expenses"
        )


# ------------------------------------------------------------------ #
# GET — form rendering                                                #
# ------------------------------------------------------------------ #

class TestGetForm:
    def test_get_returns_200(self, auth_client):
        resp = auth_client.get("/expenses/add")
        assert resp.status_code == 200, (
            "GET /expenses/add while logged in must return 200"
        )

    def test_form_contains_amount_field(self, auth_client):
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert 'name="amount"' in body or "Amount" in body, (
            "Form must contain an Amount field"
        )

    def test_form_contains_category_field(self, auth_client):
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert 'name="category"' in body or "Category" in body, (
            "Form must contain a Category field"
        )

    def test_form_contains_date_field(self, auth_client):
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert 'name="date"' in body or "Date" in body, (
            "Form must contain a Date field"
        )

    def test_form_contains_description_field(self, auth_client):
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert 'name="description"' in body or "Description" in body, (
            "Form must contain a Description field"
        )

    def test_date_field_defaults_to_today(self, auth_client):
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert TODAY_STR in body, (
            f"Date field must default to today's date ({TODAY_STR})"
        )

    @pytest.mark.parametrize("category", ALLOWED_CATEGORIES)
    def test_form_lists_all_allowed_categories(self, auth_client, category):
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert category in body, (
            f"Category '{category}' must appear in the form"
        )

    def test_form_has_submit_button(self, auth_client):
        resp = auth_client.get("/expenses/add")
        body = resp.data.decode("utf-8")
        assert (
            'type="submit"' in body
            or "<button" in body
        ), "Form must contain a submit button"


# ------------------------------------------------------------------ #
# Valid submission — redirect and flash                               #
# ------------------------------------------------------------------ #

class TestValidSubmission:
    def test_valid_post_redirects_302(self, auth_client):
        resp = auth_client.post("/expenses/add", data=VALID_FORM)
        assert resp.status_code == 302, (
            "Valid POST must redirect with 302"
        )

    def test_valid_post_redirects_to_profile(self, auth_client):
        resp = auth_client.post("/expenses/add", data=VALID_FORM)
        assert "/profile" in resp.headers["Location"], (
            "Redirect after valid POST must point to /profile"
        )

    def test_valid_post_flashes_success_message(self, auth_client):
        resp = auth_client.post(
            "/expenses/add", data=VALID_FORM, follow_redirects=True
        )
        assert b"Expense added successfully." in resp.data, (
            "Flash message 'Expense added successfully.' must appear after redirect"
        )

    def test_new_expense_description_appears_on_profile(self, auth_client):
        form = dict(VALID_FORM, description="Unique lunch expense")
        auth_client.post("/expenses/add", data=form, follow_redirects=True)
        resp = auth_client.get("/profile")
        assert b"Unique lunch expense" in resp.data, (
            "Newly added expense description must appear on the profile page"
        )

    def test_optional_description_empty_string_succeeds(self, auth_client):
        form = dict(VALID_FORM, description="")
        resp = auth_client.post("/expenses/add", data=form)
        assert resp.status_code == 302, (
            "Valid POST with empty description must still redirect (description is optional)"
        )
        assert "/profile" in resp.headers["Location"], (
            "Empty-description redirect must point to /profile"
        )

    def test_optional_description_absent_key_succeeds(self, auth_client):
        form = {k: v for k, v in VALID_FORM.items() if k != "description"}
        resp = auth_client.post("/expenses/add", data=form)
        assert resp.status_code == 302, (
            "Valid POST with description key absent must still redirect"
        )

    def test_multiple_valid_posts_each_redirect(self, auth_client):
        for i in range(3):
            form = dict(VALID_FORM, description=f"Expense {i}", amount=str(10 + i))
            resp = auth_client.post("/expenses/add", data=form)
            assert resp.status_code == 302, (
                f"POST #{i} with valid data must redirect"
            )


# ------------------------------------------------------------------ #
# DB side effect                                                      #
# ------------------------------------------------------------------ #

class TestDBSideEffect:
    def test_valid_post_inserts_row_in_db(self, auth_client):
        form = dict(VALID_FORM, description="DB side-effect check")
        auth_client.post("/expenses/add", data=form)
        conn = db_module.get_db()
        row = conn.execute(
            "SELECT * FROM expenses WHERE description = ?",
            ("DB side-effect check",),
        ).fetchone()
        conn.close()
        assert row is not None, "A row must exist in expenses after a valid POST"

    def test_inserted_row_has_correct_amount(self, auth_client):
        form = dict(VALID_FORM, amount="99.99", description="Amount check row")
        auth_client.post("/expenses/add", data=form)
        conn = db_module.get_db()
        row = conn.execute(
            "SELECT amount FROM expenses WHERE description = ?",
            ("Amount check row",),
        ).fetchone()
        conn.close()
        assert row is not None, "Row must be found by description"
        assert abs(row["amount"] - 99.99) < 0.001, (
            f"Stored amount must be 99.99, got {row['amount']}"
        )

    def test_inserted_row_has_correct_category(self, auth_client):
        form = dict(VALID_FORM, category="Transport", description="Category check row")
        auth_client.post("/expenses/add", data=form)
        conn = db_module.get_db()
        row = conn.execute(
            "SELECT category FROM expenses WHERE description = ?",
            ("Category check row",),
        ).fetchone()
        conn.close()
        assert row is not None, "Row must be found by description"
        assert row["category"] == "Transport", (
            f"Stored category must be 'Transport', got '{row['category']}'"
        )

    def test_inserted_row_has_correct_date(self, auth_client):
        specific_date = "2026-06-15"
        form = dict(VALID_FORM, date=specific_date, description="Date check row")
        auth_client.post("/expenses/add", data=form)
        conn = db_module.get_db()
        row = conn.execute(
            "SELECT date FROM expenses WHERE description = ?",
            ("Date check row",),
        ).fetchone()
        conn.close()
        assert row is not None, "Row must be found by description"
        assert row["date"] == specific_date, (
            f"Stored date must be '{specific_date}', got '{row['date']}'"
        )

    def test_inserted_row_has_correct_user_id(self, auth_client):
        form = dict(VALID_FORM, description="User ID check row")
        auth_client.post("/expenses/add", data=form)
        conn = db_module.get_db()
        expense_row = conn.execute(
            "SELECT user_id FROM expenses WHERE description = ?",
            ("User ID check row",),
        ).fetchone()
        demo_row = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            ("demo@spendly.com",),
        ).fetchone()
        conn.close()
        assert expense_row is not None, "Expense row must be inserted"
        assert expense_row["user_id"] == demo_row["id"], (
            "Stored user_id must match the logged-in demo user's id"
        )

    def test_description_truncated_to_200_chars(self, auth_client):
        long_desc = "X" * 250
        form = dict(VALID_FORM, description=long_desc)
        resp = auth_client.post("/expenses/add", data=form)
        # The request must still succeed (redirect)
        assert resp.status_code == 302, (
            "POSTing a 250-char description must still redirect (silently truncated)"
        )
        conn = db_module.get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE description = ?",
            ("X" * 200,),
        ).fetchone()
        conn.close()
        assert row is not None, (
            "Description must be stored as 200 characters (truncated silently)"
        )

    def test_empty_description_stored_as_null_or_empty(self, auth_client):
        form = dict(VALID_FORM, description="", amount="5.00")
        auth_client.post("/expenses/add", data=form)
        conn = db_module.get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE amount = ? AND category = ?",
            (5.00, "Food"),
        ).fetchone()
        conn.close()
        assert row is not None, "Row must be inserted even with empty description"
        # description must be falsy (None or empty string)
        assert not row["description"], (
            "An empty description must be stored as NULL or empty string, not arbitrary text"
        )


# ------------------------------------------------------------------ #
# Amount validation                                                   #
# ------------------------------------------------------------------ #

class TestAmountValidation:
    @pytest.mark.parametrize("bad_amount,label", [
        ("",     "empty string"),
        ("0",    "zero"),
        ("0.0",  "zero as float"),
        ("-5",   "negative integer"),
        ("-0.1", "negative fraction"),
        ("abc",  "non-numeric string"),
        ("12abc","partially numeric"),
        ("!@#",  "special characters"),
    ])
    def test_invalid_amount_returns_200(self, auth_client, bad_amount, label):
        form = dict(VALID_FORM, amount=bad_amount)
        resp = auth_client.post("/expenses/add", data=form)
        assert resp.status_code == 200, (
            f"Amount '{label}' ({bad_amount!r}) must re-render form with status 200"
        )

    @pytest.mark.parametrize("bad_amount,label", [
        ("",     "empty string"),
        ("0",    "zero"),
        ("-5",   "negative"),
        ("abc",  "non-numeric"),
    ])
    def test_invalid_amount_shows_error_message(self, auth_client, bad_amount, label):
        form = dict(VALID_FORM, amount=bad_amount)
        resp = auth_client.post("/expenses/add", data=form)
        body = resp.data.decode("utf-8")
        assert (
            "Amount must be a positive number." in body
            or "positive" in body.lower()
            or "error" in body.lower()
            or "invalid" in body.lower()
        ), (
            f"An error message must appear for amount={bad_amount!r} ({label})"
        )

    @pytest.mark.parametrize("bad_amount", ["", "0", "-5", "abc"])
    def test_invalid_amount_does_not_insert_row(self, auth_client, bad_amount):
        unique_desc = f"should-not-appear-{bad_amount}"
        form = dict(VALID_FORM, amount=bad_amount, description=unique_desc)
        auth_client.post("/expenses/add", data=form)
        conn = db_module.get_db()
        row = conn.execute(
            "SELECT id FROM expenses WHERE description = ?",
            (unique_desc,),
        ).fetchone()
        conn.close()
        assert row is None, (
            f"Invalid amount {bad_amount!r} must not insert a row into the DB"
        )


# ------------------------------------------------------------------ #
# Field preservation on validation error                             #
# ------------------------------------------------------------------ #

class TestFieldPreservationOnError:
    def test_category_preserved_when_amount_invalid(self, auth_client):
        form = dict(VALID_FORM, amount="", category="Health")
        resp = auth_client.post("/expenses/add", data=form)
        body = resp.data.decode("utf-8")
        assert "Health" in body, (
            "Category value must be preserved in the re-rendered form when amount is invalid"
        )

    def test_date_preserved_when_amount_invalid(self, auth_client):
        specific_date = "2026-07-04"
        form = dict(VALID_FORM, amount="", date=specific_date)
        resp = auth_client.post("/expenses/add", data=form)
        body = resp.data.decode("utf-8")
        assert specific_date in body, (
            "Date value must be preserved in the re-rendered form when amount is invalid"
        )

    def test_description_preserved_when_amount_invalid(self, auth_client):
        form = dict(VALID_FORM, amount="", description="Preserve me please")
        resp = auth_client.post("/expenses/add", data=form)
        body = resp.data.decode("utf-8")
        assert "Preserve me please" in body, (
            "Description value must be preserved in the re-rendered form when amount is invalid"
        )

    def test_amount_preserved_when_category_invalid(self, auth_client):
        form = dict(VALID_FORM, amount="77.77", category="InvalidCat")
        resp = auth_client.post("/expenses/add", data=form)
        body = resp.data.decode("utf-8")
        assert "77.77" in body, (
            "Amount value must be preserved in the re-rendered form when category is invalid"
        )

    def test_description_preserved_when_date_invalid(self, auth_client):
        form = dict(VALID_FORM, date="not-a-date", description="Keep this text")
        resp = auth_client.post("/expenses/add", data=form)
        body = resp.data.decode("utf-8")
        assert "Keep this text" in body, (
            "Description must be preserved in the re-rendered form when date is invalid"
        )


# ------------------------------------------------------------------ #
# Category validation                                                 #
# ------------------------------------------------------------------ #

class TestCategoryValidation:
    @pytest.mark.parametrize("bad_category,label", [
        ("",              "empty string"),
        ("Groceries",     "unrecognised value"),
        ("food",          "lowercase (case-sensitive check)"),
        ("FOOD",          "uppercase"),
        ("Food ",         "trailing space"),
        (" Food",         "leading space"),
        ("InvalidCat",    "arbitrary string"),
        ("'; DROP TABLE", "SQL injection attempt"),
    ])
    def test_invalid_category_returns_200(self, auth_client, bad_category, label):
        form = dict(VALID_FORM, category=bad_category)
        resp = auth_client.post("/expenses/add", data=form)
        assert resp.status_code == 200, (
            f"Category '{label}' ({bad_category!r}) must re-render form with 200"
        )

    @pytest.mark.parametrize("bad_category", ["", "Groceries", "InvalidCat"])
    def test_invalid_category_shows_error_message(self, auth_client, bad_category):
        form = dict(VALID_FORM, category=bad_category)
        resp = auth_client.post("/expenses/add", data=form)
        body = resp.data.decode("utf-8")
        assert (
            "valid category" in body.lower()
            or "Please select a valid category." in body
            or "error" in body.lower()
            or "invalid" in body.lower()
        ), (
            f"An error message must appear for invalid category {bad_category!r}"
        )

    @pytest.mark.parametrize("bad_category", ["", "Groceries", "InvalidCat"])
    def test_invalid_category_does_not_insert_row(self, auth_client, bad_category):
        unique_desc = f"no-insert-cat-{bad_category}"
        form = dict(VALID_FORM, category=bad_category, description=unique_desc)
        auth_client.post("/expenses/add", data=form)
        conn = db_module.get_db()
        row = conn.execute(
            "SELECT id FROM expenses WHERE description = ?",
            (unique_desc,),
        ).fetchone()
        conn.close()
        assert row is None, (
            f"Invalid category {bad_category!r} must not insert a row into the DB"
        )

    @pytest.mark.parametrize("good_category", ALLOWED_CATEGORIES)
    def test_each_allowed_category_is_accepted(self, auth_client, good_category):
        form = dict(VALID_FORM, category=good_category, description=f"cat-test-{good_category}")
        resp = auth_client.post("/expenses/add", data=form)
        assert resp.status_code == 302, (
            f"Category '{good_category}' is in the allowed list and must be accepted"
        )


# ------------------------------------------------------------------ #
# Date validation                                                     #
# ------------------------------------------------------------------ #

class TestDateValidation:
    @pytest.mark.parametrize("bad_date,label", [
        ("",            "empty string"),
        ("not-a-date",  "arbitrary string"),
        ("2026-13-01",  "month 13"),
        ("2026-05-32",  "day 32"),
        ("05-01-2026",  "wrong order (MM-DD-YYYY)"),
        ("20260501",    "no separators"),
        ("2026/05/01",  "slash separators"),
        ("yesterday",   "natural language"),
    ])
    def test_invalid_date_returns_200(self, auth_client, bad_date, label):
        form = dict(VALID_FORM, date=bad_date)
        resp = auth_client.post("/expenses/add", data=form)
        assert resp.status_code == 200, (
            f"Date '{label}' ({bad_date!r}) must re-render form with 200"
        )

    @pytest.mark.parametrize("bad_date", ["", "not-a-date", "2026-13-01"])
    def test_invalid_date_shows_error_message(self, auth_client, bad_date):
        form = dict(VALID_FORM, date=bad_date)
        resp = auth_client.post("/expenses/add", data=form)
        body = resp.data.decode("utf-8")
        assert (
            "valid date" in body.lower()
            or "Please enter a valid date." in body
            or "error" in body.lower()
            or "invalid" in body.lower()
        ), (
            f"An error message must appear for invalid date {bad_date!r}"
        )

    @pytest.mark.parametrize("bad_date", ["", "not-a-date"])
    def test_invalid_date_does_not_insert_row(self, auth_client, bad_date):
        unique_desc = f"no-insert-date-{bad_date or 'empty'}"
        form = dict(VALID_FORM, date=bad_date, description=unique_desc)
        auth_client.post("/expenses/add", data=form)
        conn = db_module.get_db()
        row = conn.execute(
            "SELECT id FROM expenses WHERE description = ?",
            (unique_desc,),
        ).fetchone()
        conn.close()
        assert row is None, (
            f"Invalid date {bad_date!r} must not insert a row into the DB"
        )

    def test_past_date_is_accepted(self, auth_client):
        form = dict(VALID_FORM, date="2025-01-01", description="Past date expense")
        resp = auth_client.post("/expenses/add", data=form)
        assert resp.status_code == 302, (
            "A past date in YYYY-MM-DD format must be accepted"
        )

    def test_future_date_is_accepted(self, auth_client):
        form = dict(VALID_FORM, date="2099-12-31", description="Future date expense")
        resp = auth_client.post("/expenses/add", data=form)
        assert resp.status_code == 302, (
            "A future date in YYYY-MM-DD format must be accepted (no upper-bound restriction in spec)"
        )


# ------------------------------------------------------------------ #
# Data isolation — one user cannot see another's expenses            #
# ------------------------------------------------------------------ #

class TestUserIsolation:
    def test_expense_added_by_user_a_not_visible_to_user_b(self, client):
        # Create a second user
        db_module.create_user("Other User", "other@spendly.com", "password123")

        # Log in as demo user and add an expense
        do_login(client, email="demo@spendly.com", password="demo123")
        form = dict(VALID_FORM, description="Secret demo expense")
        client.post("/expenses/add", data=form)

        # Log out, log in as the other user
        client.get("/logout")
        do_login(client, email="other@spendly.com", password="password123")

        resp = client.get("/profile")
        assert b"Secret demo expense" not in resp.data, (
            "An expense added by user A must not appear on user B's profile"
        )

    def test_expense_row_is_scoped_to_demo_user_id(self, client):
        do_login(client)
        form = dict(VALID_FORM, description="Scoped expense row")
        client.post("/expenses/add", data=form)

        conn = db_module.get_db()
        expense = conn.execute(
            "SELECT user_id FROM expenses WHERE description = ?",
            ("Scoped expense row",),
        ).fetchone()
        demo = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            ("demo@spendly.com",),
        ).fetchone()
        conn.close()

        assert expense is not None, "Expense must be in the DB"
        assert expense["user_id"] == demo["id"], (
            "The expense's user_id must match the demo user's id"
        )
