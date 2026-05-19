import hmac
import os
import secrets
import sqlite3
from datetime import date, datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from werkzeug.security import check_password_hash
from database.db import init_db, seed_db, create_user, get_user_by_email, insert_expense, get_expense_by_id, update_expense, delete_expense as db_delete_expense
from database.queries import (
    get_user_by_id, get_summary_stats, get_recent_transactions, get_category_breakdown
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

with app.app_context():
    init_db()
    seed_db()


def _parse_date(val):
    try:
        return datetime.strptime(val, "%Y-%m-%d").date() if val else None
    except ValueError:
        return None


def _month_start(today, months_back):
    m, y = today.month - months_back, today.year
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


def _get_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]

# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("register.html", csrf_token=_get_csrf_token())

    if request.form.get("csrf_token") != session.get("csrf_token"):
        abort(403)

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name:
        return render_template("register.html", error="Name is required.", name=name, email=email, csrf_token=_get_csrf_token())
    if not email or "@" not in email:
        return render_template("register.html", error="A valid email address is required.", name=name, email=email, csrf_token=_get_csrf_token())
    if len(password) < 8:
        return render_template("register.html", error="Password must be at least 8 characters.", name=name, email=email, csrf_token=_get_csrf_token())
    if password != confirm_password:
        return render_template("register.html", error="Passwords do not match.", name=name, email=email, csrf_token=_get_csrf_token())

    try:
        create_user(name, email, password)
    except sqlite3.IntegrityError:
        return render_template("register.html", error="An account with this email already exists.", name=name, email=email, csrf_token=_get_csrf_token())

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("login.html", csrf_token=_get_csrf_token())

    if request.form.get("csrf_token") != session.get("csrf_token"):
        abort(403)

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    user = get_user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid email or password.", email=email, csrf_token=_get_csrf_token())

    session.clear()
    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("profile"))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    date_from = _parse_date(request.args.get("date_from", ""))
    date_to = _parse_date(request.args.get("date_to", ""))

    if date_from and date_to and date_from > date_to:
        flash("Start date must be before end date.", "warning")
        date_from = date_to = None

    today = date.today()
    today_str = today.isoformat()
    preset_starts = {
        "this_month":    _month_start(today, 0).isoformat(),
        "last_3_months": _month_start(today, 3).isoformat(),
        "last_6_months": _month_start(today, 6).isoformat(),
    }

    active_preset = "all_time"
    if date_from and date_to:
        for key, start_iso in preset_starts.items():
            if date_from.isoformat() == start_iso and date_to.isoformat() == today_str:
                active_preset = key
                break
        else:
            active_preset = "custom"

    date_from_iso = date_from.isoformat() if date_from else None
    date_to_iso = date_to.isoformat() if date_to else None

    user_id = session["user_id"]
    user = get_user_by_id(user_id)
    stats = get_summary_stats(user_id, date_from=date_from_iso, date_to=date_to_iso)
    transactions = get_recent_transactions(user_id, date_from=date_from_iso, date_to=date_to_iso)
    categories = get_category_breakdown(user_id, date_from=date_from_iso, date_to=date_to_iso)

    return render_template(
        "profile.html",
        user=user, stats=stats, transactions=transactions, categories=categories,
        date_from=date_from_iso or "",
        date_to=date_to_iso or "",
        active_preset=active_preset,
        preset_starts=preset_starts,
        today_str=today_str,
        csrf_token=_get_csrf_token(),
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    today_str = date.today().isoformat()

    if request.method == "GET":
        return render_template(
            "add_expense.html",
            categories=CATEGORIES,
            today=today_str,
            csrf_token=_get_csrf_token(),
        )

    if request.form.get("csrf_token") != session.get("csrf_token"):
        abort(403)

    form = {
        "amount":      request.form.get("amount", "").strip(),
        "category":    request.form.get("category", ""),
        "date":        request.form.get("date", "").strip(),
        "description": request.form.get("description", "").strip(),
    }

    def _render_form(error):
        return render_template(
            "add_expense.html",
            categories=CATEGORIES,
            today=today_str,
            csrf_token=_get_csrf_token(),
            error=error,
            **form,
        )

    try:
        amount = round(float(form["amount"]), 2)
        if amount < 0.01:
            raise ValueError
    except ValueError:
        return _render_form("Amount must be a positive number.")

    if form["category"] not in CATEGORIES:
        return _render_form("Please select a valid category.")

    if _parse_date(form["date"]) is None:
        return _render_form("Please enter a valid date.")

    description = form["description"][:200] if form["description"] else None
    insert_expense(session["user_id"], amount, form["category"], form["date"], description)
    flash("Expense added successfully.", "success")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    expense = get_expense_by_id(id, session["user_id"])
    if expense is None:
        abort(404)

    if request.method == "GET":
        return render_template(
            "edit_expense.html",
            expense=expense,
            categories=CATEGORIES,
            csrf_token=_get_csrf_token(),
        )

    form_token = request.form.get("csrf_token")
    session_token = session.get("csrf_token")
    if not form_token or not session_token or not hmac.compare_digest(form_token, session_token):
        abort(403)

    form = {
        "amount":      request.form.get("amount", "").strip(),
        "category":    request.form.get("category", ""),
        "date":        request.form.get("date", "").strip(),
        "description": request.form.get("description", "").strip(),
    }

    def _render_form(error):
        return render_template(
            "edit_expense.html",
            expense=expense,
            categories=CATEGORIES,
            csrf_token=_get_csrf_token(),
            error=error,
            **form,
        )

    try:
        amount = round(float(form["amount"]), 2)
        if amount < 0.01:
            raise ValueError
    except ValueError:
        return _render_form("Amount must be a positive number.")

    if form["category"] not in CATEGORIES:
        return _render_form("Please select a valid category.")

    if _parse_date(form["date"]) is None:
        return _render_form("Please enter a valid date.")

    description = form["description"][:200] if form["description"] else None
    update_expense(id, session["user_id"], amount, form["category"], form["date"], description)
    flash("Expense updated successfully.", "success")
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete", methods=["POST"])
def delete_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    form_token = request.form.get("csrf_token")
    session_token = session.get("csrf_token")
    if not form_token or not session_token or not hmac.compare_digest(form_token, session_token):
        abort(403)

    expense = get_expense_by_id(id, session["user_id"])
    if expense is None:
        abort(404)

    db_delete_expense(id, session["user_id"])
    flash("Expense deleted.", "success")
    return redirect(url_for("profile"))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true", port=5001)
