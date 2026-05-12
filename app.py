import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import check_password_hash
from database.db import init_db, seed_db, create_user, get_user_by_email

app = Flask(__name__)
app.secret_key = "spendly-dev-secret"

with app.app_context():
    init_db()
    seed_db()


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

    user = {
        "name": "Demo User",
        "email": "demo@spendly.com",
        "initials": "DU",
        "member_since": "01 May 2026",
    }
    stats = {
        "total_spent": "₹360.50",
        "transaction_count": 8,
        "top_category": "Food",
    }
    transactions = [
        {"date": "07 May 2026", "description": "Restaurant dinner",  "category": "Food",          "amount": "₹55.00"},
        {"date": "07 May 2026", "description": "Miscellaneous",       "category": "Other",         "amount": "₹10.00"},
        {"date": "06 May 2026", "description": "New shirt",           "category": "Shopping",      "amount": "₹60.00"},
        {"date": "05 May 2026", "description": "Movie tickets",       "category": "Entertainment", "amount": "₹25.00"},
        {"date": "04 May 2026", "description": "Vitamins",            "category": "Health",        "amount": "₹30.00"},
        {"date": "03 May 2026", "description": "Electricity bill",    "category": "Bills",         "amount": "₹120.00"},
        {"date": "02 May 2026", "description": "Bus pass",            "category": "Transport",     "amount": "₹15.00"},
        {"date": "01 May 2026", "description": "Grocery shopping",    "category": "Food",          "amount": "₹45.50"},
    ]
    categories = [
        {"name": "Bills",         "total": "₹120.00", "pct": 33},
        {"name": "Food",          "total": "₹100.50", "pct": 28},
        {"name": "Shopping",      "total": "₹60.00",  "pct": 17},
        {"name": "Health",        "total": "₹30.00",  "pct":  8},
        {"name": "Entertainment", "total": "₹25.00",  "pct":  7},
        {"name": "Transport",     "total": "₹15.00",  "pct":  4},
        {"name": "Other",         "total": "₹10.00",  "pct":  3},
    ]
    return render_template("profile.html",
                           user=user, stats=stats,
                           transactions=transactions, categories=categories)


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
    app.run(debug=True, port=5001)
