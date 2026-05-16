import os
import secrets
import sqlite3
from datetime import date, datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from database.db import init_db, seed_db, create_user, get_user_by_email
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
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name:
        return render_template("register.html", error="Name is required.", name=name, email=email)
    if not email or "@" not in email:
        return render_template("register.html", error="A valid email address is required.", name=name, email=email)
    if len(password) < 8:
        return render_template("register.html", error="Password must be at least 8 characters.", name=name, email=email)
    if password != confirm_password:
        return render_template("register.html", error="Passwords do not match.", name=name, email=email)

    try:
        create_user(name, email, password)
    except sqlite3.IntegrityError:
        return render_template("register.html", error="An account with this email already exists.", name=name, email=email)

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    user = get_user_by_email(email)
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="Invalid email or password.", email=email)

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
        flash("Start date must be before end date.")
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
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true", port=5001)
