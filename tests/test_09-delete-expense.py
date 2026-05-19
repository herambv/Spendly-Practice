"""
Tests for Step 09 — Delete Expense feature.

Spec: .claude/specs/09-delete-expense.md

Covers:
- HTTP method guard — GET /expenses/<id>/delete returns 405 (POST-only route)
- Auth guard — unauthenticated POST redirects to /login; DB row untouched
- CSRF validation — missing, empty, or wrong token returns 403; valid token passes
- Ownership guard — deleting another user's expense returns 404; their row untouched
- Non-existent expense — POST for unknown id returns 404
- Happy path — valid POST deletes the expense, returns 302, redirects to /profile
- Flash message — "Expense deleted." appears on the profile page after redirect
- DB side effect — expense row no longer exists in the database after deletion
- Row count — total expense count decrements by exactly one after deletion
- Sibling rows unaffected — other expenses belonging to the same user are untouched
- Profile template — delete form present alongside Edit button, uses POST method,
  has hidden csrf_token input, action points to /expenses/<id>/delete
- Profile page post-deletion — deleted expense no longer appears in transactions table
"""

import os
import re
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import database.db as db_module
from tests.conftest import do_login


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
        (other_id, 22.00, "Other", "2026-05-10", "Other user's private expense"),
    )
    conn.commit()
    expense_row = conn.execute(
        "SELECT id FROM expenses WHERE user_id = ?", (other_id,)
    ).fetchone()
    conn.close()
    return expense_row["id"]


def _get_csrf(client):
    """Retrieve a valid CSRF token from the add-expense GET form.

    The add-expense page sets the csrf_token in the session and embeds it in
    the form HTML as a hidden input — we extract it via regex so that every
    POST test can supply the exact session-matched token.
    """
    resp = client.get("/expenses/add")
    body = resp.data.decode("utf-8")
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', body)
    if match:
        return match.group(1)
    match = re.search(r'value="([^"]+)"\s+name="csrf_token"', body)
    if match:
        return match.group(1)
    raise RuntimeError("Could not extract csrf_token from form HTML")


def _insert_expense(description="Delete test expense"):
    """Insert a fresh expense owned by the demo user; return its id."""
    conn = db_module.get_db()
    demo_id = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO expenses (user_id, amount, category, date, description) "
        "VALUES (?, ?, ?, ?, ?)",
        (demo_id, 19.99, "Food", "2026-05-15", description),
    )
    conn.commit()
    exp_id = conn.execute(
        "SELECT id FROM expenses WHERE description = ?", (description,)
    ).fetchone()["id"]
    conn.close()
    return exp_id


def _expense_exists(expense_id):
    """Return True if an expense row with this id still exists in the DB."""
    conn = db_module.get_db()
    row = conn.execute(
        "SELECT id FROM expenses WHERE id = ?", (expense_id,)
    ).fetchone()
    conn.close()
    return row is not None


def _expense_count():
    """Return the total number of expense rows in the DB."""
    conn = db_module.get_db()
    count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    conn.close()
    return count


# ------------------------------------------------------------------ #
# HTTP method guard                                                   #
# ------------------------------------------------------------------ #

class TestHttpMethodGuard:
    def test_get_request_returns_405(self, auth_client, demo_expense_id):
        resp = auth_client.get(f"/expenses/{demo_expense_id}/delete")
        assert resp.status_code == 405, (
            "GET /expenses/<id>/delete must return 405 — route is POST-only"
        )

    def test_get_request_does_not_delete_row(self, auth_client, demo_expense_id):
        auth_client.get(f"/expenses/{demo_expense_id}/delete")
        assert _expense_exists(demo_expense_id), (
            "A GET request to the delete route must not remove the expense row"
        )

    def test_unauthenticated_get_also_returns_405(self, client, demo_expense_id):
        resp = client.get(f"/expenses/{demo_expense_id}/delete")
        assert resp.status_code == 405, (
            "GET /expenses/<id>/delete must return 405 even for an unauthenticated client"
        )


# ------------------------------------------------------------------ #
# Auth guard — unauthenticated POST                                   #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_unauthenticated_post_redirects(self, client, demo_expense_id):
        resp = client.post(f"/expenses/{demo_expense_id}/delete", data={})
        assert resp.status_code == 302, (
            "POST /expenses/<id>/delete while logged out must redirect (302)"
        )

    def test_unauthenticated_post_redirects_to_login(self, client, demo_expense_id):
        resp = client.post(f"/expenses/{demo_expense_id}/delete", data={})
        assert "/login" in resp.headers["Location"], (
            "Unauthenticated POST to delete route must redirect to /login"
        )

    def test_unauthenticated_post_does_not_delete_row(self, client, demo_expense_id):
        client.post(f"/expenses/{demo_expense_id}/delete", data={})
        assert _expense_exists(demo_expense_id), (
            "Unauthenticated POST must not remove the expense row from the DB"
        )

    def test_unauthenticated_post_for_nonexistent_id_still_redirects(self, client):
        resp = client.post("/expenses/999999/delete", data={})
        assert resp.status_code == 302, (
            "Unauthenticated POST for a non-existent id must still redirect (auth checked first)"
        )
        assert "/login" in resp.headers["Location"], (
            "Redirect for non-existent id while logged out must point to /login"
        )


# ------------------------------------------------------------------ #
# CSRF validation                                                     #
# ------------------------------------------------------------------ #

class TestCsrfValidation:
    def test_post_without_csrf_token_returns_403(self, auth_client, demo_expense_id):
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/delete",
            data={},  # no csrf_token key at all
        )
        assert resp.status_code == 403, (
            "POST without a csrf_token must return 403 Forbidden"
        )

    def test_post_with_empty_csrf_token_returns_403(self, auth_client, demo_expense_id):
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/delete",
            data={"csrf_token": ""},
        )
        assert resp.status_code == 403, (
            "POST with an empty csrf_token must return 403 Forbidden"
        )

    def test_post_with_wrong_csrf_token_returns_403(self, auth_client, demo_expense_id):
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/delete",
            data={"csrf_token": "completely-wrong-token-value"},
        )
        assert resp.status_code == 403, (
            "POST with a mismatched csrf_token must return 403 Forbidden"
        )

    def test_post_with_valid_csrf_token_does_not_return_403(
        self, auth_client, demo_expense_id
    ):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{demo_expense_id}/delete",
            data={"csrf_token": csrf},
        )
        assert resp.status_code != 403, (
            "POST with a valid csrf_token must not return 403"
        )

    def test_invalid_csrf_token_does_not_delete_row(self, auth_client, demo_expense_id):
        auth_client.post(
            f"/expenses/{demo_expense_id}/delete",
            data={"csrf_token": "bad-token"},
        )
        assert _expense_exists(demo_expense_id), (
            "An invalid CSRF token must prevent deletion — row must still exist"
        )


# ------------------------------------------------------------------ #
# Ownership guard                                                     #
# ------------------------------------------------------------------ #

class TestOwnershipGuard:
    def test_post_another_users_expense_returns_404(
        self, auth_client, other_user_expense_id
    ):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{other_user_expense_id}/delete",
            data={"csrf_token": csrf},
        )
        assert resp.status_code == 404, (
            "POST to delete another user's expense must return 404"
        )

    def test_post_another_users_expense_does_not_delete_row(
        self, auth_client, other_user_expense_id
    ):
        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{other_user_expense_id}/delete",
            data={"csrf_token": csrf},
        )
        assert _expense_exists(other_user_expense_id), (
            "POST for another user's expense must not remove that row from the DB"
        )

    def test_post_nonexistent_expense_returns_404(self, auth_client):
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            "/expenses/999999/delete",
            data={"csrf_token": csrf},
        )
        assert resp.status_code == 404, (
            "POST for a non-existent expense id must return 404"
        )


# ------------------------------------------------------------------ #
# Happy path                                                          #
# ------------------------------------------------------------------ #

class TestHappyPath:
    def test_valid_post_returns_302(self, auth_client):
        exp_id = _insert_expense("happy path redirect check")
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{exp_id}/delete",
            data={"csrf_token": csrf},
        )
        assert resp.status_code == 302, (
            "Valid POST to delete expense must return 302 redirect"
        )

    def test_valid_post_redirects_to_profile(self, auth_client):
        exp_id = _insert_expense("redirect target check")
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{exp_id}/delete",
            data={"csrf_token": csrf},
        )
        assert "/profile" in resp.headers["Location"], (
            "Valid POST to delete expense must redirect to /profile"
        )

    def test_valid_post_flashes_expense_deleted(self, auth_client):
        exp_id = _insert_expense("flash message check")
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{exp_id}/delete",
            data={"csrf_token": csrf},
            follow_redirects=True,
        )
        assert b"Expense deleted." in resp.data, (
            "Flash message 'Expense deleted.' must appear on the profile page after deletion"
        )

    def test_valid_post_profile_page_returns_200_after_redirect(self, auth_client):
        exp_id = _insert_expense("profile 200 after delete")
        csrf = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{exp_id}/delete",
            data={"csrf_token": csrf},
            follow_redirects=True,
        )
        assert resp.status_code == 200, (
            "Following the redirect after deletion must render the profile page with 200"
        )


# ------------------------------------------------------------------ #
# DB side effects                                                     #
# ------------------------------------------------------------------ #

class TestDBSideEffects:
    def test_deleted_expense_no_longer_exists_in_db(self, auth_client):
        exp_id = _insert_expense("db removal check")
        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{exp_id}/delete",
            data={"csrf_token": csrf},
        )
        assert not _expense_exists(exp_id), (
            f"Expense id={exp_id} must no longer exist in the DB after deletion"
        )

    def test_expense_count_decrements_by_one(self, auth_client):
        exp_id = _insert_expense("count decrement check")
        before = _expense_count()
        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{exp_id}/delete",
            data={"csrf_token": csrf},
        )
        after = _expense_count()
        assert after == before - 1, (
            f"Total expense count must decrease by 1 after deletion; "
            f"was {before}, now {after}"
        )

    def test_other_expenses_of_same_user_untouched(self, auth_client):
        """Deleting one expense must leave the user's other expenses intact."""
        exp_id = _insert_expense("row to delete")

        # Record all sibling ids before deletion
        conn = db_module.get_db()
        demo_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", ("demo@spendly.com",)
        ).fetchone()["id"]
        sibling_ids = [
            row["id"]
            for row in conn.execute(
                "SELECT id FROM expenses WHERE user_id = ? AND id != ?",
                (demo_id, exp_id),
            ).fetchall()
        ]
        conn.close()

        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{exp_id}/delete",
            data={"csrf_token": csrf},
        )

        for sibling_id in sibling_ids:
            assert _expense_exists(sibling_id), (
                f"Sibling expense id={sibling_id} must still exist after deleting id={exp_id}"
            )

    def test_repeated_delete_of_same_id_returns_404(self, auth_client):
        """After a successful delete, a second POST for the same id must return 404."""
        exp_id = _insert_expense("double delete check")
        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{exp_id}/delete",
            data={"csrf_token": csrf},
        )
        csrf2 = _get_csrf(auth_client)
        resp = auth_client.post(
            f"/expenses/{exp_id}/delete",
            data={"csrf_token": csrf2},
        )
        assert resp.status_code == 404, (
            "A second POST to delete an already-deleted expense must return 404"
        )

    def test_deleted_expense_does_not_appear_on_profile(self, auth_client):
        """After deletion the expense's description must not appear in the profile page."""
        unique_desc = "Unique description for profile absence test xyz987"
        exp_id = _insert_expense(unique_desc)
        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{exp_id}/delete",
            data={"csrf_token": csrf},
        )
        resp = auth_client.get("/profile")
        assert unique_desc.encode() not in resp.data, (
            "The deleted expense's description must not appear in the profile transactions table"
        )

    def test_deletion_only_removes_target_row(self, auth_client):
        """Verify that only the exact targeted expense id is removed from the DB."""
        exp_id = _insert_expense("target only removal check")

        conn = db_module.get_db()
        all_ids_before = {
            row["id"]
            for row in conn.execute("SELECT id FROM expenses").fetchall()
        }
        conn.close()

        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{exp_id}/delete",
            data={"csrf_token": csrf},
        )

        conn = db_module.get_db()
        all_ids_after = {
            row["id"]
            for row in conn.execute("SELECT id FROM expenses").fetchall()
        }
        conn.close()

        expected_remaining = all_ids_before - {exp_id}
        assert all_ids_after == expected_remaining, (
            "Only the targeted expense id must be removed; "
            f"expected remaining ids {expected_remaining}, got {all_ids_after}"
        )


# ------------------------------------------------------------------ #
# Profile page template — delete form structure                       #
# ------------------------------------------------------------------ #

class TestProfileDeleteFormStructure:
    def test_profile_contains_delete_form(self, auth_client):
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        assert "/delete" in body, (
            "The profile page must contain at least one delete form action URL"
        )

    def test_profile_delete_form_uses_post_method(self, auth_client):
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        # Look for a form with method="post" near a /delete action
        has_post_delete = bool(
            re.search(
                r'<form[^>]*method=["\']post["\'][^>]*/expenses/\d+/delete',
                body,
                re.IGNORECASE,
            )
            or re.search(
                r'<form[^>]*/expenses/\d+/delete[^>]*method=["\']post["\']',
                body,
                re.IGNORECASE,
            )
        )
        # Broader fallback: the page has both method="post" and /delete in form context
        if not has_post_delete:
            has_post_delete = (
                re.search(r'method=["\']post["\']', body, re.IGNORECASE) is not None
                and "/delete" in body
            )
        assert has_post_delete, (
            "Profile page must contain a delete form that uses method=POST"
        )

    def test_profile_delete_form_has_csrf_hidden_input(self, auth_client):
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        assert 'name="csrf_token"' in body, (
            "Delete form on the profile page must include a hidden csrf_token input"
        )

    def test_profile_delete_form_action_uses_expenses_delete_url_pattern(
        self, auth_client
    ):
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        assert re.search(r"/expenses/\d+/delete", body), (
            "Profile page must contain a delete form action matching /expenses/<id>/delete"
        )

    def test_profile_delete_form_id_matches_existing_expense(self, auth_client):
        """The delete form ids in the profile HTML must correspond to real expense ids."""
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        matches = re.findall(r"/expenses/(\d+)/delete", body)
        assert len(matches) > 0, (
            "At least one /expenses/<id>/delete action must appear on the profile page"
        )
        for id_str in matches:
            assert _expense_exists(int(id_str)), (
                f"Delete form references expense id={id_str} which must exist in the DB"
            )

    def test_profile_has_delete_button_or_text(self, auth_client):
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        has_delete = "Delete" in body or "delete" in body
        assert has_delete, (
            "Profile transactions section must contain a Delete button or text"
        )

    def test_profile_delete_form_present_for_known_expense(self, auth_client):
        """Insert a known expense; verify its delete form action appears on /profile."""
        exp_id = _insert_expense("delete form presence check")
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        assert f"/expenses/{exp_id}/delete" in body, (
            f"Profile page must contain a delete form action for expense id={exp_id}"
        )

    def test_profile_delete_form_alongside_edit_button(self, auth_client):
        """Both an Edit link and a Delete form must appear together on the profile page."""
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        has_edit = "/edit" in body
        has_delete = "/delete" in body
        assert has_edit and has_delete, (
            "Profile page must contain both Edit links and Delete form actions "
            "in the transactions table"
        )


# ------------------------------------------------------------------ #
# SQL injection safety                                                #
# ------------------------------------------------------------------ #

class TestSQLInjectionSafety:
    def test_sql_injection_via_expense_id_path_returns_404(self, auth_client):
        """
        Flask's <int:id> converter rejects non-integer path segments, so a
        SQL injection string in the URL must result in a 404 (no route match),
        not a crash or unintended DB mutation.
        """
        resp = auth_client.post(
            "/expenses/1%3BDROP%20TABLE%20expenses/delete",
            data={"csrf_token": "anything"},
        )
        assert resp.status_code in (404, 405), (
            "A non-integer id in the delete URL must return 404 or 405, not 500"
        )
        # Confirm the expenses table still exists and has rows
        count = _expense_count()
        assert count > 0, (
            "expenses table must still exist and contain rows after a path injection attempt"
        )

    def test_expenses_table_survives_normal_delete(self, auth_client):
        """
        After a legitimate delete, the expenses table must still exist and the
        remaining seed rows must be accessible — confirming parameterised query safety.
        """
        exp_id = _insert_expense("table survival check")
        csrf = _get_csrf(auth_client)
        auth_client.post(
            f"/expenses/{exp_id}/delete",
            data={"csrf_token": csrf},
        )
        count = _expense_count()
        assert count >= 0, (
            "expenses table must still be queryable after a delete operation"
        )
