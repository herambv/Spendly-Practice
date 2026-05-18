"""
Tests for Step 08 — Edit Expense feature.

Covers:
- Auth guard (GET and POST) — unauthenticated requests redirect to /login
- Ownership guard — accessing another user's expense returns 404
- GET happy path — pre-filled form shows correct values for the expense owner
- GET form structure — amount, category, date, description fields present;
  all allowed categories listed
- POST happy path — valid submission updates the DB and redirects 302 to /profile
  with a "Expense updated successfully." flash message
- DB side effects — after valid POST, raw SQL confirms new values persisted
- POST validation — zero/negative/non-numeric amount returns 200 + error, DB unchanged
- POST validation — invalid date returns 200 + error, DB unchanged
- POST validation — invalid category returns 200 + error, DB unchanged
- POST validation — field preservation on each type of error
- Profile page — each transaction row has an Edit link to /expenses/<id>/edit
- CSRF protection — POST without a valid token returns 403
- Description truncation — 250-char description accepted (silently truncated)
- SQL injection safety — malicious input stored safely via parameterised queries
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

# A valid edit payload (csrf_token injected at test time via fixture helpers)
VALID_EDIT = {
    "amount":      "75.00",
    "category":    "Health",
    "date":        "2026-06-01",
    "description": "Updated description",
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


@pytest.fixture
def demo_expense_id(app):
    """Return the id of the first expense owned by the demo user."""
    conn = db_module.get_db()
    row = conn.execute(
        "SELECT id FROM expenses WHERE user_id = "
        "(SELECT id FROM users WHERE email = ?) LIMIT 1",
        ("demo@spendly.com",),
    ).fetchone()
    conn.close()
    assert row is not None, "Seed data must include at least one expense for demo user"
    return row["id"]


@pytest.fixture
def other_user_expense_id(app):
    """Create a second user and insert one expense; return that expense's id."""
    db_module.create_user("Other User", "other@spendly.com", "otherpass123")
    conn = db_module.get_db()
    other_id = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("other@spendly.com",)
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (other_id, 10.00, "Other", "2026-05-01", "Other user expense"),
    )
    conn.commit()
    expense_row = conn.execute(
        "SELECT id FROM expenses WHERE user_id = ?", (other_id,)
    ).fetchone()
    conn.close()
    return expense_row["id"]


def _get_csrf(client):
    """Retrieve a valid CSRF token by GETting the edit form for any expense.

    This helper logs in, fetches the add-expense GET form (which sets the
    csrf_token in the session), and returns the token stored in the session.
    We use the add_expense GET because it is always available without needing
    a specific expense id at fixture construction time.
    """
    resp = client.get("/expenses/add")
    # The token is embedded in the form HTML as a hidden input
    body = resp.data.decode("utf-8")
    import re
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', body)
    if match:
        return match.group(1)
    # Fallback: look for the value in the other order
    match = re.search(r'value="([^"]+)"\s+name="csrf_token"', body)
    if match:
        return match.group(1)
    raise RuntimeError("Could not extract csrf_token from form HTML")


# ------------------------------------------------------------------ #
# Auth guard — unauthenticated GET                                    #
# ------------------------------------------------------------------ #

class TestAuthGuardGet:
    def test_unauthenticated_get_redirects(self, client, demo_expense_id):
        resp = client.get(f"/expenses/{demo_expense_id}/edit")
        assert resp.status_code == 302, (
            "GET /expenses/<id>/edit while logged out must return 302"
        )

    def test_unauthenticated_get_redirects_to_login(self, client, demo_expense_id):
        resp = client.get(f"/expenses/{demo_expense_id}/edit")
        assert "/login" in resp.headers["Location"], (
            "Unauthenticated GET must redirect to /login"
        )

    def test_unauthenticated_get_does_not_return_200(self, client, demo_expense_id):
        resp = client.get(f"/expenses/{demo_expense_id}/edit")
        assert resp.status_code != 200, (
            "Unauthenticated GET must not render the edit form"
        )

    def test_unauthenticated_get_nonexistent_id_still_redirects(self, client):
        resp = client.get("/expenses/999999/edit")
        assert resp.status_code == 302, (
            "GET for a non-existent id while logged out must still redirect (auth checked first)"
        )
        assert "/login" in resp.headers["Location"], (
            "Redirect must point to /login even for a non-existent expense id"
        )


# ------------------------------------------------------------------ #
# Auth guard — unauthenticated POST                                   #
# ------------------------------------------------------------------ #

class TestAuthGuardPost:
    def test_unauthenticated_post_redirects(self, client, demo_expense_id):
        resp = client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=VALID_EDIT,
        )
        assert resp.status_code == 302, (
            "POST /expenses/<id>/edit while logged out must return 302"
        )

    def test_unauthenticated_post_redirects_to_login(self, client, demo_expense_id):
        resp = client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=VALID_EDIT,
        )
        assert "/login" in resp.headers["Location"], (
            "Unauthenticated POST must redirect to /login"
        )

    def test_unauthenticated_post_does_not_update_db(self, client, demo_expense_id):
        # Record original amount before the attempt
        conn = db_module.get_db()
        original = conn.execute(
            "SELECT amount FROM expenses WHERE id = ?", (demo_expense_id,)
        ).fetchone()["amount"]
        conn.close()

        client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, amount="999.99"),
        )

        conn = db_module.get_db()
        after = conn.execute(
            "SELECT amount FROM expenses WHERE id = ?", (demo_expense_id,)
        ).fetchone()["amount"]
        conn.close()
        assert abs(after - original) < 0.001, (
            "Unauthenticated POST must not modify the expense row in the DB"
        )


# ------------------------------------------------------------------ #
# Ownership guard                                                     #
# ------------------------------------------------------------------ #

class TestOwnershipGuard:
    def test_get_another_users_expense_returns_404(
        self, auth_client, other_user_expense_id
    ):
        resp = auth_client.get(f"/expenses/{other_user_expense_id}/edit")
        assert resp.status_code == 404, (
            "GET for an expense belonging to another user must return 404"
        )

    def test_post_another_users_expense_returns_404(
        self, auth_client, other_user_expense_id
    ):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{other_user_expense_id}/edit",
            data=dict(VALID_EDIT, csrf_token=csrf),
        )
        assert resp.status_code == 404, (
            "POST for an expense belonging to another user must return 404"
        )

    def test_post_another_users_expense_does_not_update_db(
        self, auth_client, other_user_expense_id
    ):
        csrf = _get_csrf(auth_client)
        conn = db_module.get_db()
        original = conn.execute(
            "SELECT amount FROM expenses WHERE id = ?", (other_user_expense_id,)
        ).fetchone()["amount"]
        conn.close()

        auth_client.post(
            f"/expenses/{other_user_expense_id}/edit",
            data=dict(VALID_EDIT, amount="999.99", csrf_token=csrf),
        )

        conn = db_module.get_db()
        after = conn.execute(
            "SELECT amount FROM expenses WHERE id = ?", (other_user_expense_id,)
        ).fetchone()["amount"]
        conn.close()
        assert abs(after - original) < 0.001, (
            "POST for another user's expense must not modify that row"
        )

    def test_get_nonexistent_expense_returns_404(self, auth_client):
        resp = auth_client.get("/expenses/999999/edit")
        assert resp.status_code == 404, (
            "GET for a non-existent expense id must return 404"
        )

    def test_post_nonexistent_expense_returns_404(self, auth_client):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            "/expenses/999999/edit",
            data=dict(VALID_EDIT, csrf_token=csrf),
        )
        assert resp.status_code == 404, (
            "POST for a non-existent expense id must return 404"
        )


# ------------------------------------------------------------------ #
# GET happy path — form rendering and pre-filled values              #
# ------------------------------------------------------------------ #

class TestGetHappyPath:
    def test_get_returns_200(self, auth_client, demo_expense_id):
        resp = auth_client.get(f"/expenses/{demo_expense_id}/edit")
        assert resp.status_code == 200, (
            "GET /expenses/<id>/edit for own expense must return 200"
        )

    def test_form_shows_correct_amount(self, auth_client):
        """Insert a known expense, then verify its amount appears pre-filled."""
        conn = db_module.get_db()
        demo_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (demo_id, 123.45, "Food", "2026-05-10", "Known amount expense"),
        )
        conn.commit()
        exp_id = conn.execute(
            "SELECT id FROM expenses WHERE description = ?",
            ("Known amount expense",),
        ).fetchone()["id"]
        conn.close()

        resp = auth_client.get(f"/expenses/{exp_id}/edit")
        body = resp.data.decode("utf-8")
        assert "123.45" in body, (
            "The pre-filled form must contain the expense's amount (123.45)"
        )

    def test_form_shows_correct_category(self, auth_client):
        conn = db_module.get_db()
        demo_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (demo_id, 50.00, "Transport", "2026-05-10", "Known category expense"),
        )
        conn.commit()
        exp_id = conn.execute(
            "SELECT id FROM expenses WHERE description = ?",
            ("Known category expense",),
        ).fetchone()["id"]
        conn.close()

        resp = auth_client.get(f"/expenses/{exp_id}/edit")
        body = resp.data.decode("utf-8")
        assert "Transport" in body, (
            "The pre-filled form must reflect the expense's category (Transport)"
        )

    def test_form_shows_correct_date(self, auth_client):
        conn = db_module.get_db()
        demo_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (demo_id, 20.00, "Other", "2026-07-04", "Known date expense"),
        )
        conn.commit()
        exp_id = conn.execute(
            "SELECT id FROM expenses WHERE description = ?",
            ("Known date expense",),
        ).fetchone()["id"]
        conn.close()

        resp = auth_client.get(f"/expenses/{exp_id}/edit")
        body = resp.data.decode("utf-8")
        assert "2026-07-04" in body, (
            "The pre-filled form must reflect the expense's date (2026-07-04)"
        )

    def test_form_shows_correct_description(self, auth_client):
        conn = db_module.get_db()
        demo_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (demo_id, 30.00, "Food", "2026-05-15", "Unique prefilled description xyz"),
        )
        conn.commit()
        exp_id = conn.execute(
            "SELECT id FROM expenses WHERE description = ?",
            ("Unique prefilled description xyz",),
        ).fetchone()["id"]
        conn.close()

        resp = auth_client.get(f"/expenses/{exp_id}/edit")
        body = resp.data.decode("utf-8")
        assert "Unique prefilled description xyz" in body, (
            "The pre-filled form must show the expense's description"
        )

    def test_form_contains_amount_field(self, auth_client, demo_expense_id):
        resp = auth_client.get(f"/expenses/{demo_expense_id}/edit")
        body = resp.data.decode("utf-8")
        assert 'name="amount"' in body or "Amount" in body, (
            "Edit form must contain an Amount field"
        )

    def test_form_contains_category_field(self, auth_client, demo_expense_id):
        resp = auth_client.get(f"/expenses/{demo_expense_id}/edit")
        body = resp.data.decode("utf-8")
        assert 'name="category"' in body or "Category" in body, (
            "Edit form must contain a Category field"
        )

    def test_form_contains_date_field(self, auth_client, demo_expense_id):
        resp = auth_client.get(f"/expenses/{demo_expense_id}/edit")
        body = resp.data.decode("utf-8")
        assert 'name="date"' in body or "Date" in body, (
            "Edit form must contain a Date field"
        )

    def test_form_contains_description_field(self, auth_client, demo_expense_id):
        resp = auth_client.get(f"/expenses/{demo_expense_id}/edit")
        body = resp.data.decode("utf-8")
        assert 'name="description"' in body or "Description" in body, (
            "Edit form must contain a Description field"
        )

    @pytest.mark.parametrize("category", ALLOWED_CATEGORIES)
    def test_form_lists_all_allowed_categories(
        self, auth_client, demo_expense_id, category
    ):
        resp = auth_client.get(f"/expenses/{demo_expense_id}/edit")
        body = resp.data.decode("utf-8")
        assert category in body, (
            f"Allowed category '{category}' must appear in the edit form"
        )

    def test_form_has_csrf_hidden_input(self, auth_client, demo_expense_id):
        resp = auth_client.get(f"/expenses/{demo_expense_id}/edit")
        body = resp.data.decode("utf-8")
        assert 'name="csrf_token"' in body, (
            "Edit form must contain a hidden csrf_token input"
        )

    def test_form_has_submit_button(self, auth_client, demo_expense_id):
        resp = auth_client.get(f"/expenses/{demo_expense_id}/edit")
        body = resp.data.decode("utf-8")
        assert 'type="submit"' in body or "<button" in body, (
            "Edit form must contain a submit button"
        )

    def test_form_action_points_to_edit_route(self, auth_client, demo_expense_id):
        resp = auth_client.get(f"/expenses/{demo_expense_id}/edit")
        body = resp.data.decode("utf-8")
        assert f"/expenses/{demo_expense_id}/edit" in body, (
            "Form action must point back to the edit URL for this expense"
        )


# ------------------------------------------------------------------ #
# POST happy path                                                     #
# ------------------------------------------------------------------ #

class TestPostHappyPath:
    def test_valid_post_redirects_302(self, auth_client, demo_expense_id):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, csrf_token=csrf),
        )
        assert resp.status_code == 302, (
            "Valid POST to edit expense must redirect with 302"
        )

    def test_valid_post_redirects_to_profile(self, auth_client, demo_expense_id):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, csrf_token=csrf),
        )
        assert "/profile" in resp.headers["Location"], (
            "Redirect after valid POST must point to /profile"
        )

    def test_valid_post_flashes_success_message(self, auth_client, demo_expense_id):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, csrf_token=csrf),
            follow_redirects=True,
        )
        assert b"Expense updated successfully." in resp.data, (
            "Flash message 'Expense updated successfully.' must appear after redirect"
        )

    def test_valid_post_updated_values_visible_on_profile(
        self, auth_client, demo_expense_id
    ):
        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(
                VALID_EDIT,
                description="Verified on profile page",
                csrf_token=csrf,
            ),
            follow_redirects=True,
        )
        resp = auth_client.get("/profile")
        assert b"Verified on profile page" in resp.data, (
            "Updated description must appear on the profile transactions list"
        )

    def test_all_allowed_categories_can_be_saved(self, auth_client, demo_expense_id):
        for category in ALLOWED_CATEGORIES:
            csrf = _get_csrf(auth_client)
            resp = auth_client.post(
                f"/expenses/{demo_expense_id}/edit",
                data=dict(VALID_EDIT, category=category, csrf_token=csrf),
            )
            assert resp.status_code == 302, (
                f"Category '{category}' is allowed and must result in a redirect"
            )

    def test_empty_description_is_accepted(self, auth_client, demo_expense_id):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, description="", csrf_token=csrf),
        )
        assert resp.status_code == 302, (
            "Empty description must be accepted (description is optional)"
        )

    def test_absent_description_key_is_accepted(self, auth_client, demo_expense_id):
        csrf = _get_csrf(auth_client)
        form = {k: v for k, v in VALID_EDIT.items() if k != "description"}
        form["csrf_token"] = csrf
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=form,
        )
        assert resp.status_code == 302, (
            "Missing description key must be accepted (description is optional)"
        )


# ------------------------------------------------------------------ #
# DB side effects after valid POST                                    #
# ------------------------------------------------------------------ #

class TestDBSideEffects:
    def _insert_known_expense(self, description="DB check expense"):
        conn = db_module.get_db()
        demo_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (demo_id, 10.00, "Food", "2026-01-01", description),
        )
        conn.commit()
        exp_id = conn.execute(
            "SELECT id FROM expenses WHERE description = ?", (description,)
        ).fetchone()["id"]
        conn.close()
        return exp_id

    def test_amount_updated_in_db(self, auth_client):
        exp_id = self._insert_known_expense("amount update check")
        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{exp_id}/edit",
            data=dict(VALID_EDIT, amount="88.88", csrf_token=csrf),
        )
        conn = db_module.get_db()
        row = conn.execute(
            "SELECT amount FROM expenses WHERE id = ?", (exp_id,)
        ).fetchone()
        conn.close()
        assert row is not None, "Row must still exist after update"
        assert abs(row["amount"] - 88.88) < 0.001, (
            f"Amount must be updated to 88.88 in DB, got {row['amount']}"
        )

    def test_category_updated_in_db(self, auth_client):
        exp_id = self._insert_known_expense("category update check")
        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{exp_id}/edit",
            data=dict(VALID_EDIT, category="Entertainment", csrf_token=csrf),
        )
        conn = db_module.get_db()
        row = conn.execute(
            "SELECT category FROM expenses WHERE id = ?", (exp_id,)
        ).fetchone()
        conn.close()
        assert row["category"] == "Entertainment", (
            f"Category must be updated to 'Entertainment' in DB, got '{row['category']}'"
        )

    def test_date_updated_in_db(self, auth_client):
        exp_id = self._insert_known_expense("date update check")
        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{exp_id}/edit",
            data=dict(VALID_EDIT, date="2026-09-15", csrf_token=csrf),
        )
        conn = db_module.get_db()
        row = conn.execute(
            "SELECT date FROM expenses WHERE id = ?", (exp_id,)
        ).fetchone()
        conn.close()
        assert row["date"] == "2026-09-15", (
            f"Date must be updated to '2026-09-15' in DB, got '{row['date']}'"
        )

    def test_description_updated_in_db(self, auth_client):
        exp_id = self._insert_known_expense("original description here")
        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{exp_id}/edit",
            data=dict(VALID_EDIT, description="Replaced description", csrf_token=csrf),
        )
        conn = db_module.get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE id = ?", (exp_id,)
        ).fetchone()
        conn.close()
        assert row["description"] == "Replaced description", (
            f"Description must be updated in DB, got '{row['description']}'"
        )

    def test_user_id_unchanged_after_update(self, auth_client):
        exp_id = self._insert_known_expense("user_id stability check")
        conn = db_module.get_db()
        original_user_id = conn.execute(
            "SELECT user_id FROM expenses WHERE id = ?", (exp_id,)
        ).fetchone()["user_id"]
        conn.close()

        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{exp_id}/edit",
            data=dict(VALID_EDIT, csrf_token=csrf),
        )

        conn = db_module.get_db()
        after_user_id = conn.execute(
            "SELECT user_id FROM expenses WHERE id = ?", (exp_id,)
        ).fetchone()["user_id"]
        conn.close()
        assert after_user_id == original_user_id, (
            "The user_id on the expense row must not change after an edit"
        )

    def test_only_target_row_is_modified(self, auth_client):
        """Editing one expense must leave the other seed expenses untouched."""
        exp_id = self._insert_known_expense("target row only")
        conn = db_module.get_db()
        # Pick a different expense row (from seed data)
        other = conn.execute(
            "SELECT id, amount FROM expenses WHERE id != ?", (exp_id,)
        ).fetchone()
        other_id, other_amount = other["id"], other["amount"]
        conn.close()

        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{exp_id}/edit",
            data=dict(VALID_EDIT, amount="111.11", csrf_token=csrf),
        )

        conn = db_module.get_db()
        unchanged = conn.execute(
            "SELECT amount FROM expenses WHERE id = ?", (other_id,)
        ).fetchone()["amount"]
        conn.close()
        assert abs(unchanged - other_amount) < 0.001, (
            "Only the targeted expense row must be updated; other rows must remain unchanged"
        )

    def test_description_truncated_to_200_chars(self, auth_client):
        exp_id = self._insert_known_expense("truncation check expense")
        csrf = _get_csrf(auth_client)
        long_desc = "Z" * 250
        resp = auth_client.post(
            f"/expenses/{exp_id}/edit",
            data=dict(VALID_EDIT, description=long_desc, csrf_token=csrf),
        )
        assert resp.status_code == 302, (
            "A 250-char description must be silently truncated and still redirect"
        )
        conn = db_module.get_db()
        row = conn.execute(
            "SELECT description FROM expenses WHERE id = ?", (exp_id,)
        ).fetchone()
        conn.close()
        assert row["description"] == "Z" * 200, (
            "Description must be stored as 200 characters after truncation"
        )


# ------------------------------------------------------------------ #
# Amount validation                                                   #
# ------------------------------------------------------------------ #

class TestAmountValidation:
    @pytest.mark.parametrize("bad_amount,label", [
        ("",     "empty string"),
        ("0",    "zero"),
        ("0.00", "zero as float"),
        ("-5",   "negative integer"),
        ("-0.1", "negative fraction"),
        ("abc",  "non-numeric string"),
        ("12abc","partially numeric"),
        ("!@#",  "special characters"),
    ])
    def test_invalid_amount_returns_200(
        self, auth_client, demo_expense_id, bad_amount, label
    ):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, amount=bad_amount, csrf_token=csrf),
        )
        assert resp.status_code == 200, (
            f"Amount '{label}' ({bad_amount!r}) must re-render form with 200"
        )

    @pytest.mark.parametrize("bad_amount,label", [
        ("",    "empty string"),
        ("0",   "zero"),
        ("-5",  "negative"),
        ("abc", "non-numeric"),
    ])
    def test_invalid_amount_shows_error_message(
        self, auth_client, demo_expense_id, bad_amount, label
    ):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, amount=bad_amount, csrf_token=csrf),
        )
        body = resp.data.decode("utf-8")
        assert (
            "Amount must be a positive number." in body
            or "positive" in body.lower()
            or "error" in body.lower()
            or "invalid" in body.lower()
        ), (
            f"An error message must appear for amount='{bad_amount}' ({label})"
        )

    @pytest.mark.parametrize("bad_amount", ["", "0", "-5", "abc"])
    def test_invalid_amount_does_not_update_db(
        self, auth_client, demo_expense_id, bad_amount
    ):
        conn = db_module.get_db()
        original_amount = conn.execute(
            "SELECT amount FROM expenses WHERE id = ?", (demo_expense_id,)
        ).fetchone()["amount"]
        conn.close()

        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, amount=bad_amount, csrf_token=csrf),
        )

        conn = db_module.get_db()
        after_amount = conn.execute(
            "SELECT amount FROM expenses WHERE id = ?", (demo_expense_id,)
        ).fetchone()["amount"]
        conn.close()
        assert abs(after_amount - original_amount) < 0.001, (
            f"Invalid amount {bad_amount!r} must not update the DB row"
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
        ("05-01-2026",  "wrong order MM-DD-YYYY"),
        ("20260501",    "no separators"),
        ("2026/05/01",  "slash separators"),
        ("yesterday",   "natural language"),
    ])
    def test_invalid_date_returns_200(
        self, auth_client, demo_expense_id, bad_date, label
    ):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, date=bad_date, csrf_token=csrf),
        )
        assert resp.status_code == 200, (
            f"Date '{label}' ({bad_date!r}) must re-render form with 200"
        )

    @pytest.mark.parametrize("bad_date", ["", "not-a-date", "2026-13-01"])
    def test_invalid_date_shows_error_message(
        self, auth_client, demo_expense_id, bad_date
    ):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, date=bad_date, csrf_token=csrf),
        )
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
    def test_invalid_date_does_not_update_db(
        self, auth_client, demo_expense_id, bad_date
    ):
        conn = db_module.get_db()
        original_date = conn.execute(
            "SELECT date FROM expenses WHERE id = ?", (demo_expense_id,)
        ).fetchone()["date"]
        conn.close()

        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, date=bad_date, csrf_token=csrf),
        )

        conn = db_module.get_db()
        after_date = conn.execute(
            "SELECT date FROM expenses WHERE id = ?", (demo_expense_id,)
        ).fetchone()["date"]
        conn.close()
        assert after_date == original_date, (
            f"Invalid date {bad_date!r} must not update the date in the DB"
        )

    def test_past_date_is_accepted(self, auth_client, demo_expense_id):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, date="2020-01-01", csrf_token=csrf),
        )
        assert resp.status_code == 302, (
            "A past date in YYYY-MM-DD format must be accepted"
        )

    def test_future_date_is_accepted(self, auth_client, demo_expense_id):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, date="2099-12-31", csrf_token=csrf),
        )
        assert resp.status_code == 302, (
            "A future date in YYYY-MM-DD format must be accepted"
        )


# ------------------------------------------------------------------ #
# Category validation                                                 #
# ------------------------------------------------------------------ #

class TestCategoryValidation:
    @pytest.mark.parametrize("bad_category,label", [
        ("",              "empty string"),
        ("Groceries",     "unrecognised value"),
        ("food",          "lowercase"),
        ("FOOD",          "uppercase"),
        ("Food ",         "trailing space"),
        (" Food",         "leading space"),
        ("InvalidCat",    "arbitrary string"),
        ("'; DROP TABLE", "SQL injection attempt"),
    ])
    def test_invalid_category_returns_200(
        self, auth_client, demo_expense_id, bad_category, label
    ):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, category=bad_category, csrf_token=csrf),
        )
        assert resp.status_code == 200, (
            f"Category '{label}' ({bad_category!r}) must re-render form with 200"
        )

    @pytest.mark.parametrize("bad_category", ["", "Groceries", "InvalidCat"])
    def test_invalid_category_shows_error_message(
        self, auth_client, demo_expense_id, bad_category
    ):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, category=bad_category, csrf_token=csrf),
        )
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
    def test_invalid_category_does_not_update_db(
        self, auth_client, demo_expense_id, bad_category
    ):
        conn = db_module.get_db()
        original_cat = conn.execute(
            "SELECT category FROM expenses WHERE id = ?", (demo_expense_id,)
        ).fetchone()["category"]
        conn.close()

        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, category=bad_category, csrf_token=csrf),
        )

        conn = db_module.get_db()
        after_cat = conn.execute(
            "SELECT category FROM expenses WHERE id = ?", (demo_expense_id,)
        ).fetchone()["category"]
        conn.close()
        assert after_cat == original_cat, (
            f"Invalid category {bad_category!r} must not update the category in the DB"
        )

    @pytest.mark.parametrize("good_category", ALLOWED_CATEGORIES)
    def test_each_allowed_category_is_accepted(
        self, auth_client, demo_expense_id, good_category
    ):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, category=good_category, csrf_token=csrf),
        )
        assert resp.status_code == 302, (
            f"Category '{good_category}' is in the allowed list and must be accepted (302)"
        )


# ------------------------------------------------------------------ #
# Field preservation on validation error                             #
# ------------------------------------------------------------------ #

class TestFieldPreservationOnError:
    def test_category_preserved_when_amount_invalid(
        self, auth_client, demo_expense_id
    ):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, amount="", category="Shopping", csrf_token=csrf),
        )
        assert "Shopping" in resp.data.decode("utf-8"), (
            "Category must be preserved in the re-rendered form when amount is invalid"
        )

    def test_date_preserved_when_amount_invalid(self, auth_client, demo_expense_id):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, amount="", date="2026-08-20", csrf_token=csrf),
        )
        assert "2026-08-20" in resp.data.decode("utf-8"), (
            "Date must be preserved in the re-rendered form when amount is invalid"
        )

    def test_description_preserved_when_amount_invalid(
        self, auth_client, demo_expense_id
    ):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(
                VALID_EDIT,
                amount="",
                description="Preserve this text",
                csrf_token=csrf,
            ),
        )
        assert "Preserve this text" in resp.data.decode("utf-8"), (
            "Description must be preserved in the re-rendered form when amount is invalid"
        )

    def test_amount_preserved_when_category_invalid(
        self, auth_client, demo_expense_id
    ):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, amount="55.55", category="BadCat", csrf_token=csrf),
        )
        assert "55.55" in resp.data.decode("utf-8"), (
            "Amount must be preserved in the re-rendered form when category is invalid"
        )

    def test_description_preserved_when_date_invalid(
        self, auth_client, demo_expense_id
    ):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(
                VALID_EDIT,
                date="not-a-date",
                description="Keep this description",
                csrf_token=csrf,
            ),
        )
        assert "Keep this description" in resp.data.decode("utf-8"), (
            "Description must be preserved in the re-rendered form when date is invalid"
        )

    def test_amount_preserved_when_date_invalid(self, auth_client, demo_expense_id):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, amount="33.33", date="bad-date", csrf_token=csrf),
        )
        assert "33.33" in resp.data.decode("utf-8"), (
            "Amount must be preserved in the re-rendered form when date is invalid"
        )

    def test_category_preserved_when_date_invalid(self, auth_client, demo_expense_id):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(
                VALID_EDIT,
                category="Bills",
                date="bad-date",
                csrf_token=csrf,
            ),
        )
        assert "Bills" in resp.data.decode("utf-8"), (
            "Category must be preserved in the re-rendered form when date is invalid"
        )


# ------------------------------------------------------------------ #
# CSRF protection                                                     #
# ------------------------------------------------------------------ #

class TestCsrfProtection:
    def test_post_without_csrf_token_returns_403(
        self, auth_client, demo_expense_id
    ):
        # Submit with no csrf_token key at all
        form = {k: v for k, v in VALID_EDIT.items()}  # no csrf_token
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=form,
        )
        assert resp.status_code == 403, (
            "POST without a csrf_token must return 403 Forbidden"
        )

    def test_post_with_wrong_csrf_token_returns_403(
        self, auth_client, demo_expense_id
    ):
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, csrf_token="definitely-wrong-token"),
        )
        assert resp.status_code == 403, (
            "POST with a mismatched csrf_token must return 403 Forbidden"
        )

    def test_post_with_empty_csrf_token_returns_403(
        self, auth_client, demo_expense_id
    ):
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, csrf_token=""),
        )
        assert resp.status_code == 403, (
            "POST with an empty csrf_token must return 403 Forbidden"
        )

    def test_post_with_valid_csrf_token_does_not_return_403(
        self, auth_client, demo_expense_id
    ):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, csrf_token=csrf),
        )
        assert resp.status_code != 403, (
            "POST with a valid csrf_token must not return 403"
        )


# ------------------------------------------------------------------ #
# Profile page — Edit link per transaction row                        #
# ------------------------------------------------------------------ #

class TestProfileEditLinks:
    def test_profile_contains_edit_links(self, auth_client):
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        assert "/edit" in body, (
            "The profile page must contain at least one /edit link in the transactions table"
        )

    def test_profile_edit_links_point_to_expenses_route(self, auth_client):
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        assert "/expenses/" in body and "/edit" in body, (
            "Edit links must use the /expenses/<id>/edit URL pattern"
        )

    def test_edit_link_for_known_expense_present_on_profile(self, auth_client):
        """
        Insert an expense and verify its edit link appears on /profile.
        This confirms that get_recent_transactions includes the 'id' key.
        """
        conn = db_module.get_db()
        demo_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()["id"]
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (demo_id, 9.99, "Other", TODAY_STR, "Edit link check expense"),
        )
        conn.commit()
        exp_id = conn.execute(
            "SELECT id FROM expenses WHERE description = ?",
            ("Edit link check expense",),
        ).fetchone()["id"]
        conn.close()

        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        assert f"/expenses/{exp_id}/edit" in body, (
            f"The profile page must contain an edit link for expense id={exp_id}"
        )

    def test_get_recent_transactions_includes_id_field(self, app):
        """
        Verify that get_recent_transactions returns dicts with an 'id' key,
        which is required for building Edit links in the template.
        """
        from database.queries import get_recent_transactions
        conn = db_module.get_db()
        demo_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()["id"]
        conn.close()

        with app.app_context():
            transactions = get_recent_transactions(demo_id)

        assert len(transactions) > 0, "Seeded demo user must have transactions"
        for tx in transactions:
            assert "id" in tx, (
                "Each transaction dict returned by get_recent_transactions must include 'id'"
            )

    def test_transaction_ids_are_integers(self, app):
        """
        The 'id' field in each transaction must be a usable integer (for URL building).
        """
        from database.queries import get_recent_transactions
        conn = db_module.get_db()
        demo_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()["id"]
        conn.close()

        with app.app_context():
            transactions = get_recent_transactions(demo_id)

        for tx in transactions:
            assert isinstance(tx["id"], int), (
                f"Transaction id must be an int; got {type(tx['id'])} for tx={tx}"
            )

    def test_profile_edit_links_navigate_to_edit_form(self, auth_client):
        """
        Verify that following an edit link from the profile returns a 200 (edit form),
        not a 404 or redirect.
        """
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")

        # Extract first /expenses/<id>/edit href from the page
        import re
        match = re.search(r'href="(/expenses/(\d+)/edit)"', body)
        assert match is not None, (
            "At least one /expenses/<id>/edit href must be present on the profile page"
        )
        edit_url = match.group(1)
        edit_resp = auth_client.get(edit_url)
        assert edit_resp.status_code == 200, (
            f"Following the edit link '{edit_url}' from profile must return 200"
        )

    def test_profile_has_actions_column_or_edit_text(self, auth_client):
        """
        The transactions table must contain an actions column or Edit link text.
        """
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        has_actions = "Actions" in body or "Edit" in body or "edit" in body
        assert has_actions, (
            "Profile transactions table must include an 'Actions' column or 'Edit' link text"
        )


# ------------------------------------------------------------------ #
# SQL injection safety                                                #
# ------------------------------------------------------------------ #

class TestSQLInjectionSafety:
    def test_sql_injection_in_description_is_safe(self, auth_client, demo_expense_id):
        """
        A SQL injection string in description must be stored verbatim
        (parameterised queries prevent execution).
        """
        injection = "'; DROP TABLE expenses; --"
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, description=injection, csrf_token=csrf),
        )
        # Request must succeed (redirect), and expenses table must still exist
        assert resp.status_code == 302, (
            "A SQL injection string in description must not crash the app"
        )
        conn = db_module.get_db()
        # If DROP TABLE executed, this query would raise an error
        count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        conn.close()
        assert count > 0, (
            "expenses table must still exist and contain rows after a SQL injection attempt"
        )

    def test_sql_injection_in_category_rejected_cleanly(
        self, auth_client, demo_expense_id
    ):
        """
        A SQL injection string as category must be rejected by the allowlist
        validation (not cause a crash or DB error).
        """
        injection = "'; DROP TABLE expenses; --"
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/edit",
            data=dict(VALID_EDIT, category=injection, csrf_token=csrf),
        )
        # Category is not in allowed list → 200 with error
        assert resp.status_code == 200, (
            "A SQL injection string as category must be rejected with 200 (not in allowed list)"
        )
        conn = db_module.get_db()
        count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
        conn.close()
        assert count > 0, (
            "expenses table must still exist after a SQL injection attempt via category"
        )
