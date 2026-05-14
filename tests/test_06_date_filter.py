"""
Tests for Step 06 — Date Filter on the /profile route.

Covers:
- Auth guard
- No-params baseline (All Time, unfiltered)
- Filter bar HTML presence and active-preset CSS class
- This Month / Last 3 Months / Last 6 Months preset detection
- Custom date range filtering (amounts, transaction counts, categories)
- date_from > date_to validation → flash error + fallback to unfiltered
- Malformed date strings → no crash, silent fallback to unfiltered
- Partial params (only one bound provided) → fallback to unfiltered
- Rupee symbol present on all filtered responses
- New user with no expenses + date filter → ₹0.00, 0 transactions, no 500
"""

import datetime
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import database.db as db_module


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
    """A test client already logged in as the seeded demo user."""
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})
    return client


@pytest.fixture
def empty_user_client(client):
    """A test client logged in as a fresh user with zero expenses."""
    db_module.create_user("Empty User", "empty@spendly.com", "password123")
    client.post("/login", data={"email": "empty@spendly.com", "password": "password123"})
    return client


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def _month_start(months_back: int) -> datetime.date:
    """Return the first day of the month that is `months_back` months before today."""
    today = datetime.date.today()
    m, y = today.month - months_back, today.year
    while m <= 0:
        m += 12
        y -= 1
    return datetime.date(y, m, 1)


TODAY_STR = datetime.date.today().isoformat()
THIS_MONTH_START = _month_start(0).isoformat()
LAST_3_START = _month_start(3).isoformat()
LAST_6_START = _month_start(6).isoformat()

# Seed data constants (from database/db.py seed_db)
SEED_TOTAL = "360.50"
SEED_COUNT = 8
MAY_1_3_TOTAL = "180.50"   # 45.50 + 15.00 + 120.00
MAY_1_3_COUNT = 3


# ------------------------------------------------------------------ #
# Auth guard                                                          #
# ------------------------------------------------------------------ #

class TestAuthGuard:
    def test_unauthenticated_get_profile_redirects_to_login(self, client):
        resp = client.get("/profile")
        assert resp.status_code == 302, "Unauthenticated /profile must redirect"
        assert "/login" in resp.headers["Location"], "Redirect must point to /login"

    def test_unauthenticated_with_date_params_also_redirects(self, client):
        resp = client.get("/profile?date_from=2026-05-01&date_to=2026-05-14")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


# ------------------------------------------------------------------ #
# No-params baseline (All Time)                                       #
# ------------------------------------------------------------------ #

class TestNoParamsBaseline:
    def test_returns_200(self, auth_client):
        resp = auth_client.get("/profile")
        assert resp.status_code == 200

    def test_shows_all_8_seed_expenses_total(self, auth_client):
        resp = auth_client.get("/profile")
        assert SEED_TOTAL.encode() in resp.data, "All-Time view must show ₹360.50"

    def test_shows_correct_transaction_count(self, auth_client):
        resp = auth_client.get("/profile")
        assert str(SEED_COUNT).encode() in resp.data, "All-Time view must show 8 transactions"

    def test_shows_bills_as_top_category(self, auth_client):
        resp = auth_client.get("/profile")
        assert b"Bills" in resp.data, "Bills must be the top category in All Time"

    def test_rupee_symbol_present(self, auth_client):
        resp = auth_client.get("/profile")
        assert "₹".encode("utf-8") in resp.data, "₹ symbol must appear on profile page"


# ------------------------------------------------------------------ #
# Filter bar HTML                                                     #
# ------------------------------------------------------------------ #

class TestFilterBarHTML:
    def test_filter_bar_contains_this_month(self, auth_client):
        resp = auth_client.get("/profile")
        assert b"This Month" in resp.data, "Filter bar must contain 'This Month' preset"

    def test_filter_bar_contains_last_3_months(self, auth_client):
        resp = auth_client.get("/profile")
        assert b"Last 3 Months" in resp.data, "Filter bar must contain 'Last 3 Months' preset"

    def test_filter_bar_contains_last_6_months(self, auth_client):
        resp = auth_client.get("/profile")
        assert b"Last 6 Months" in resp.data, "Filter bar must contain 'Last 6 Months' preset"

    def test_filter_bar_contains_all_time(self, auth_client):
        resp = auth_client.get("/profile")
        assert b"All Time" in resp.data, "Filter bar must contain 'All Time' preset"

    def test_filter_bar_has_date_inputs(self, auth_client):
        resp = auth_client.get("/profile")
        assert b'name="date_from"' in resp.data, "Filter bar must have date_from input"
        assert b'name="date_to"' in resp.data, "Filter bar must have date_to input"

    def test_filter_bar_has_apply_button(self, auth_client):
        resp = auth_client.get("/profile")
        assert b"Apply" in resp.data, "Filter bar must have an Apply submit button"


# ------------------------------------------------------------------ #
# Active preset detection                                             #
# ------------------------------------------------------------------ #

class TestActivePresetDetection:
    def test_no_params_makes_all_time_active(self, auth_client):
        resp = auth_client.get("/profile")
        body = resp.data.decode("utf-8")
        # The All Time link must carry the active CSS class
        assert "filter-btn--active" in body, "A preset must be marked active"
        # The active class should appear on All Time, not on This Month
        all_time_idx = body.find("All Time")
        this_month_idx = body.find("This Month")
        # The active marker before "All Time" should exist;
        # find the active-class occurrence closest to "All Time"
        active_marker = "filter-btn--active"
        # Verify active marker appears somewhere in the text near "All Time"
        # by checking the segment of HTML containing "All Time"
        assert active_marker in body[max(0, all_time_idx - 200): all_time_idx + 50], (
            "filter-btn--active must appear on the All Time preset when no params are given"
        )

    def test_this_month_dates_make_this_month_active(self, auth_client):
        resp = auth_client.get(
            f"/profile?date_from={THIS_MONTH_START}&date_to={TODAY_STR}"
        )
        body = resp.data.decode("utf-8")
        assert resp.status_code == 200
        this_month_idx = body.find("This Month")
        assert this_month_idx != -1, "'This Month' text must be present"
        assert "filter-btn--active" in body[max(0, this_month_idx - 200): this_month_idx + 50], (
            "filter-btn--active must appear on the This Month preset when its dates are in the URL"
        )

    def test_last_3_months_dates_make_last_3_months_active(self, auth_client):
        resp = auth_client.get(
            f"/profile?date_from={LAST_3_START}&date_to={TODAY_STR}"
        )
        body = resp.data.decode("utf-8")
        assert resp.status_code == 200
        last3_idx = body.find("Last 3 Months")
        assert last3_idx != -1, "'Last 3 Months' text must be present"
        assert "filter-btn--active" in body[max(0, last3_idx - 200): last3_idx + 50], (
            "filter-btn--active must appear on the Last 3 Months preset when its dates are in the URL"
        )

    def test_last_6_months_dates_make_last_6_months_active(self, auth_client):
        resp = auth_client.get(
            f"/profile?date_from={LAST_6_START}&date_to={TODAY_STR}"
        )
        body = resp.data.decode("utf-8")
        assert resp.status_code == 200
        last6_idx = body.find("Last 6 Months")
        assert last6_idx != -1, "'Last 6 Months' text must be present"
        assert "filter-btn--active" in body[max(0, last6_idx - 200): last6_idx + 50], (
            "filter-btn--active must appear on the Last 6 Months preset when its dates are in the URL"
        )

    def test_custom_range_does_not_mark_any_preset_active(self, auth_client):
        # 2026-05-02 to 2026-05-04 matches no preset
        resp = auth_client.get("/profile?date_from=2026-05-02&date_to=2026-05-04")
        body = resp.data.decode("utf-8")
        assert resp.status_code == 200
        # No preset link should carry the active class;
        # check that none of the preset labels are immediately adjacent to the active class
        # by verifying that "This Month", "Last 3 Months", "Last 6 Months", "All Time"
        # do not each have the active marker in their surrounding HTML segment
        for label in ["This Month", "Last 3 Months", "Last 6 Months", "All Time"]:
            idx = body.find(label)
            assert idx != -1, f"'{label}' must still appear in the filter bar"
            segment = body[max(0, idx - 200): idx + 50]
            assert "filter-btn--active" not in segment, (
                f"'{label}' must NOT be active for a custom date range"
            )


# ------------------------------------------------------------------ #
# Custom date range filtering (May 1–3)                              #
# ------------------------------------------------------------------ #

class TestCustomDateRangeFiltering:
    def test_may_1_to_3_returns_200(self, auth_client):
        resp = auth_client.get("/profile?date_from=2026-05-01&date_to=2026-05-03")
        assert resp.status_code == 200

    def test_may_1_to_3_shows_correct_total(self, auth_client):
        resp = auth_client.get("/profile?date_from=2026-05-01&date_to=2026-05-03")
        assert MAY_1_3_TOTAL.encode() in resp.data, (
            "May 1–3 filter must show ₹180.50 (grocery 45.50 + bus 15.00 + electricity 120.00)"
        )

    def test_may_1_to_3_shows_correct_transaction_count(self, auth_client):
        resp = auth_client.get("/profile?date_from=2026-05-01&date_to=2026-05-03")
        assert str(MAY_1_3_COUNT).encode() in resp.data, (
            "May 1–3 filter must show 3 transactions"
        )

    def test_may_1_to_3_shows_expected_descriptions(self, auth_client):
        resp = auth_client.get("/profile?date_from=2026-05-01&date_to=2026-05-03")
        assert b"Grocery shopping" in resp.data, "Grocery shopping must appear in May 1–3 range"
        assert b"Bus pass" in resp.data, "Bus pass must appear in May 1–3 range"
        assert b"Electricity bill" in resp.data, "Electricity bill must appear in May 1–3 range"

    def test_may_1_to_3_excludes_later_expenses(self, auth_client):
        resp = auth_client.get("/profile?date_from=2026-05-01&date_to=2026-05-03")
        assert b"Movie tickets" not in resp.data, "May 5 expense must not appear in May 1–3 filter"
        assert b"New shirt" not in resp.data, "May 6 expense must not appear in May 1–3 filter"
        assert b"Restaurant dinner" not in resp.data, "May 7 expense must not appear in May 1–3 filter"

    def test_may_1_to_3_category_breakdown_limited_to_3_categories(self, auth_client):
        resp = auth_client.get("/profile?date_from=2026-05-01&date_to=2026-05-03")
        body = resp.data.decode("utf-8")
        # Only Food (May 1), Transport (May 2), Bills (May 3) should appear in breakdown
        assert "Food" in body, "Food category must appear in May 1–3 breakdown"
        assert "Transport" in body, "Transport category must appear in May 1–3 breakdown"
        assert "Bills" in body, "Bills category must appear in May 1–3 breakdown"
        # Categories from outside the range must not appear
        assert "Entertainment" not in body, "Entertainment must not appear in May 1–3 breakdown"
        assert "Shopping" not in body, "Shopping must not appear in May 1–3 breakdown"

    def test_may_1_to_3_rupee_symbol_present(self, auth_client):
        resp = auth_client.get("/profile?date_from=2026-05-01&date_to=2026-05-03")
        assert "₹".encode("utf-8") in resp.data, "₹ symbol must appear even with custom filter active"

    def test_may_1_to_1_shows_single_expense(self, auth_client):
        resp = auth_client.get("/profile?date_from=2026-05-01&date_to=2026-05-01")
        assert b"Grocery shopping" in resp.data
        assert b"Bus pass" not in resp.data, "May 2 expense must not appear in single-day May 1 filter"

    def test_date_inputs_reflect_active_filter_values(self, auth_client):
        resp = auth_client.get("/profile?date_from=2026-05-01&date_to=2026-05-03")
        body = resp.data.decode("utf-8")
        assert "2026-05-01" in body, "date_from value must be reflected in the filter form"
        assert "2026-05-03" in body, "date_to value must be reflected in the filter form"


# ------------------------------------------------------------------ #
# All-seed-expenses visible with This Month preset (May 2026)        #
# ------------------------------------------------------------------ #

class TestThisMonthPreset:
    def test_this_month_returns_200(self, auth_client):
        resp = auth_client.get(
            f"/profile?date_from={THIS_MONTH_START}&date_to={TODAY_STR}"
        )
        assert resp.status_code == 200

    def test_this_month_rupee_symbol_present(self, auth_client):
        resp = auth_client.get(
            f"/profile?date_from={THIS_MONTH_START}&date_to={TODAY_STR}"
        )
        assert "₹".encode("utf-8") in resp.data


# ------------------------------------------------------------------ #
# Validation: date_from > date_to                                     #
# ------------------------------------------------------------------ #

class TestDateOrderValidation:
    def test_date_from_after_date_to_returns_200(self, auth_client):
        resp = auth_client.get("/profile?date_from=2026-05-10&date_to=2026-05-01")
        assert resp.status_code == 200, "Inverted date range must not crash the app"

    def test_date_from_after_date_to_flashes_error_message(self, auth_client):
        resp = auth_client.get(
            "/profile?date_from=2026-05-10&date_to=2026-05-01",
            follow_redirects=True,
        )
        assert b"Start date must be before end date." in resp.data, (
            "Flash message 'Start date must be before end date.' must appear"
        )

    def test_date_from_after_date_to_falls_back_to_unfiltered(self, auth_client):
        resp = auth_client.get(
            "/profile?date_from=2026-05-10&date_to=2026-05-01",
            follow_redirects=True,
        )
        # Falls back to unfiltered → all 8 seed expenses visible
        assert SEED_TOTAL.encode() in resp.data, (
            "After inverted-date error, unfiltered total ₹360.50 must be shown"
        )
        assert str(SEED_COUNT).encode() in resp.data, (
            "After inverted-date error, unfiltered count of 8 must be shown"
        )

    def test_equal_dates_are_valid_and_return_200(self, auth_client):
        # date_from == date_to is a valid single-day range (not inverted)
        resp = auth_client.get("/profile?date_from=2026-05-01&date_to=2026-05-01")
        assert resp.status_code == 200
        assert b"Start date must be before end date." not in resp.data, (
            "Equal dates must not trigger the error flash"
        )


# ------------------------------------------------------------------ #
# Malformed / partial date parameters                                 #
# ------------------------------------------------------------------ #

class TestMalformedDateParams:
    def test_malformed_date_from_returns_200(self, auth_client):
        resp = auth_client.get("/profile?date_from=not-a-date")
        assert resp.status_code == 200, "Malformed date_from must not crash the app"

    def test_malformed_date_from_falls_back_to_unfiltered(self, auth_client):
        resp = auth_client.get("/profile?date_from=not-a-date")
        assert SEED_TOTAL.encode() in resp.data, (
            "Malformed date_from must fall back to unfiltered view (₹360.50)"
        )

    def test_malformed_date_to_returns_200(self, auth_client):
        resp = auth_client.get("/profile?date_to=not-a-date")
        assert resp.status_code == 200, "Malformed date_to must not crash the app"

    def test_malformed_date_to_falls_back_to_unfiltered(self, auth_client):
        resp = auth_client.get("/profile?date_to=not-a-date")
        assert SEED_TOTAL.encode() in resp.data, (
            "Malformed date_to must fall back to unfiltered view (₹360.50)"
        )

    def test_malformed_both_dates_returns_200(self, auth_client):
        resp = auth_client.get("/profile?date_from=abc&date_to=xyz")
        assert resp.status_code == 200

    def test_malformed_both_dates_shows_all_expenses(self, auth_client):
        resp = auth_client.get("/profile?date_from=abc&date_to=xyz")
        assert SEED_TOTAL.encode() in resp.data

    def test_only_date_from_provided_falls_back_to_unfiltered(self, auth_client):
        # A single valid bound without the other must be treated as no filter
        resp = auth_client.get("/profile?date_from=2026-05-01")
        assert resp.status_code == 200
        assert SEED_TOTAL.encode() in resp.data, (
            "Only date_from (no date_to) must fall back to unfiltered view"
        )

    def test_only_date_to_provided_falls_back_to_unfiltered(self, auth_client):
        # A single valid bound without the other must be treated as no filter
        resp = auth_client.get("/profile?date_to=2026-05-07")
        assert resp.status_code == 200
        assert SEED_TOTAL.encode() in resp.data, (
            "Only date_to (no date_from) must fall back to unfiltered view"
        )

    def test_empty_string_params_fall_back_to_unfiltered(self, auth_client):
        resp = auth_client.get("/profile?date_from=&date_to=")
        assert resp.status_code == 200
        assert SEED_TOTAL.encode() in resp.data

    @pytest.mark.parametrize("date_from,date_to", [
        ("2026-13-01", "2026-05-07"),   # month 13 is invalid
        ("2026-05-32", "2026-05-07"),   # day 32 is invalid
        ("20260501",   "2026-05-07"),   # no hyphens
        ("05-01-2026", "2026-05-07"),   # wrong order
        ("2026/05/01", "2026-05-07"),   # slashes instead of hyphens
        ("",           "2026-05-07"),   # empty date_from
        ("2026-05-01", ""),             # empty date_to
    ])
    def test_invalid_date_formats_fall_back_gracefully(
        self, auth_client, date_from, date_to
    ):
        resp = auth_client.get(f"/profile?date_from={date_from}&date_to={date_to}")
        assert resp.status_code == 200, (
            f"date_from='{date_from}' date_to='{date_to}' must not crash the app"
        )


# ------------------------------------------------------------------ #
# Empty user (no expenses) with date filter                          #
# ------------------------------------------------------------------ #

class TestEmptyUserWithDateFilter:
    def test_no_params_returns_200(self, empty_user_client):
        resp = empty_user_client.get("/profile")
        assert resp.status_code == 200

    def test_no_params_shows_zero_total(self, empty_user_client):
        resp = empty_user_client.get("/profile")
        assert "₹0.00".encode("utf-8") in resp.data, "Empty user must show ₹0.00"

    def test_date_filtered_returns_200_not_500(self, empty_user_client):
        resp = empty_user_client.get("/profile?date_from=2026-05-01&date_to=2026-05-14")
        assert resp.status_code == 200, "Date filter on empty user must not raise 500"

    def test_date_filtered_shows_zero_total(self, empty_user_client):
        resp = empty_user_client.get("/profile?date_from=2026-05-01&date_to=2026-05-14")
        assert "₹0.00".encode("utf-8") in resp.data, (
            "Filtered empty user must show ₹0.00"
        )

    def test_date_filtered_shows_zero_transaction_count(self, empty_user_client):
        resp = empty_user_client.get("/profile?date_from=2026-05-01&date_to=2026-05-14")
        # transaction_count of 0 must appear in the stats section
        assert b"0" in resp.data

    def test_date_filter_no_500_on_inverted_dates(self, empty_user_client):
        resp = empty_user_client.get(
            "/profile?date_from=2026-05-10&date_to=2026-05-01",
            follow_redirects=True,
        )
        assert resp.status_code == 200


# ------------------------------------------------------------------ #
# Rupee symbol across all filter types                               #
# ------------------------------------------------------------------ #

class TestRupeeSymbolConsistency:
    @pytest.mark.parametrize("query", [
        "",
        "?date_from=2026-05-01&date_to=2026-05-03",
        "?date_from=2026-05-01&date_to=2026-05-14",
        f"?date_from={LAST_3_START}&date_to={TODAY_STR}",
        f"?date_from={LAST_6_START}&date_to={TODAY_STR}",
    ])
    def test_rupee_symbol_present_for_filter(self, auth_client, query):
        resp = auth_client.get(f"/profile{query}")
        assert resp.status_code == 200
        assert "₹".encode("utf-8") in resp.data, (
            f"₹ symbol must appear on /profile{query}"
        )


# ------------------------------------------------------------------ #
# Last 3 Months and Last 6 Months preset routes return 200           #
# ------------------------------------------------------------------ #

class TestPresetRoutes:
    def test_last_3_months_returns_200(self, auth_client):
        resp = auth_client.get(
            f"/profile?date_from={LAST_3_START}&date_to={TODAY_STR}"
        )
        assert resp.status_code == 200

    def test_last_6_months_returns_200(self, auth_client):
        resp = auth_client.get(
            f"/profile?date_from={LAST_6_START}&date_to={TODAY_STR}"
        )
        assert resp.status_code == 200

    def test_all_time_clean_url_returns_200(self, auth_client):
        resp = auth_client.get("/profile")
        assert resp.status_code == 200
