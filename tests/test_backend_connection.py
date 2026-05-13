import pytest
from tests.conftest import do_login
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
)


# ------------------------------------------------------------------ #
# get_user_by_id                                                      #
# ------------------------------------------------------------------ #

class TestGetUserById:
    def test_valid_id_returns_correct_fields(self, app, demo_user_id):
        result = get_user_by_id(demo_user_id)
        assert result is not None
        assert result["name"] == "Demo User"
        assert result["email"] == "demo@spendly.com"
        assert result["initials"] == "DU"

    def test_member_since_format(self, app, demo_user_id):
        result = get_user_by_id(demo_user_id)
        parts = result["member_since"].split()
        assert len(parts) == 2
        assert parts[1].isdigit() and len(parts[1]) == 4

    def test_nonexistent_id_returns_none(self, app):
        assert get_user_by_id(99999) is None


# ------------------------------------------------------------------ #
# get_summary_stats                                                   #
# ------------------------------------------------------------------ #

class TestGetSummaryStats:
    def test_user_with_expenses(self, app, demo_user_id):
        result = get_summary_stats(demo_user_id)
        assert result["total_spent"] == "₹360.50"
        assert result["transaction_count"] == 8
        assert result["top_category"] == "Bills"

    def test_user_with_no_expenses(self, app, empty_user_id):
        result = get_summary_stats(empty_user_id)
        assert result["total_spent"] == "₹0.00"
        assert result["transaction_count"] == 0
        assert result["top_category"] == "—"


# ------------------------------------------------------------------ #
# get_recent_transactions                                             #
# ------------------------------------------------------------------ #

class TestGetRecentTransactions:
    def test_user_with_expenses_returns_correct_count(self, app, demo_user_id):
        result = get_recent_transactions(demo_user_id)
        assert len(result) == 8

    def test_ordered_newest_first(self, app, demo_user_id):
        result = get_recent_transactions(demo_user_id)
        assert "07" in result[0]["date"]
        assert "01" in result[-1]["date"]

    def test_required_keys_present(self, app, demo_user_id):
        result = get_recent_transactions(demo_user_id)
        for tx in result:
            assert "date" in tx
            assert "description" in tx
            assert "category" in tx
            assert "amount" in tx

    def test_amount_has_rupee_symbol(self, app, demo_user_id):
        result = get_recent_transactions(demo_user_id)
        for tx in result:
            assert tx["amount"].startswith("₹")

    def test_limit_parameter(self, app, demo_user_id):
        result = get_recent_transactions(demo_user_id, limit=3)
        assert len(result) == 3

    def test_user_with_no_expenses_returns_empty_list(self, app, empty_user_id):
        assert get_recent_transactions(empty_user_id) == []


# ------------------------------------------------------------------ #
# get_category_breakdown                                              #
# ------------------------------------------------------------------ #

class TestGetCategoryBreakdown:
    def test_user_with_expenses_returns_all_categories(self, app, demo_user_id):
        result = get_category_breakdown(demo_user_id)
        assert len(result) == 7

    def test_required_keys_present(self, app, demo_user_id):
        result = get_category_breakdown(demo_user_id)
        for cat in result:
            assert "name" in cat
            assert "total" in cat
            assert "pct" in cat
            assert isinstance(cat["pct"], int)

    def test_pct_sums_to_100(self, app, demo_user_id):
        result = get_category_breakdown(demo_user_id)
        assert sum(cat["pct"] for cat in result) == 100

    def test_ordered_by_total_descending(self, app, demo_user_id):
        result = get_category_breakdown(demo_user_id)
        assert result[0]["name"] == "Bills"

    def test_total_has_rupee_symbol(self, app, demo_user_id):
        result = get_category_breakdown(demo_user_id)
        for cat in result:
            assert cat["total"].startswith("₹")

    def test_user_with_no_expenses_returns_empty_list(self, app, empty_user_id):
        assert get_category_breakdown(empty_user_id) == []


# ------------------------------------------------------------------ #
# /profile route                                                      #
# ------------------------------------------------------------------ #

class TestProfileRoute:
    def test_unauthenticated_redirects_to_login(self, client):
        resp = client.get("/profile")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_authenticated_returns_200(self, client):
        do_login(client)
        resp = client.get("/profile")
        assert resp.status_code == 200

    def test_shows_real_user_name(self, client):
        do_login(client)
        assert b"Demo User" in client.get("/profile").data

    def test_shows_real_user_email(self, client):
        do_login(client)
        assert b"demo@spendly.com" in client.get("/profile").data

    def test_shows_correct_total_spent(self, client):
        do_login(client)
        assert "360.50".encode() in client.get("/profile").data

    def test_shows_top_category(self, client):
        do_login(client)
        assert b"Bills" in client.get("/profile").data

    def test_shows_all_7_categories(self, client):
        do_login(client)
        body = client.get("/profile").data
        for cat in [b"Bills", b"Food", b"Shopping", b"Health",
                    b"Entertainment", b"Transport", b"Other"]:
            assert cat in body

    def test_shows_rupee_symbol(self, client):
        do_login(client)
        assert "₹".encode("utf-8") in client.get("/profile").data

    def test_empty_user_shows_zero_stats(self, client, empty_user_id):
        do_login(client, email="empty@spendly.com", password="password123")
        resp = client.get("/profile")
        assert resp.status_code == 200
        assert "₹0.00".encode("utf-8") in resp.data
