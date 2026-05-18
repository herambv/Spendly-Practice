from database.db import get_db

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _date_filter(date_from, date_to):
    if date_from and date_to:
        return " AND date BETWEEN ? AND ?", (date_from, date_to)
    return "", ()


def get_user_by_id(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT name, email, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    raw = row["created_at"]   # "YYYY-MM-DD HH:MM:SS"
    member_since = f"{MONTH_NAMES[int(raw[5:7])]} {raw[0:4]}"
    initials = "".join(w[0].upper() for w in row["name"].split() if w)[:2]
    return {"name": row["name"], "email": row["email"],
            "initials": initials, "member_since": member_since}


def get_summary_stats(user_id, date_from=None, date_to=None):
    conn = get_db()
    date_clause, date_params = _date_filter(date_from, date_to)
    agg = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
        "FROM expenses WHERE user_id = ?" + date_clause,
        (user_id,) + date_params
    ).fetchone()
    top = conn.execute(
        "SELECT category FROM expenses WHERE user_id = ?" + date_clause +
        " GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1",
        (user_id,) + date_params
    ).fetchone()
    conn.close()
    return {
        "total_spent":       f"₹{agg['total']:.2f}",
        "transaction_count": agg["cnt"],
        "top_category":      top["category"] if top else "—",
    }


def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    conn = get_db()
    date_clause, date_params = _date_filter(date_from, date_to)
    rows = conn.execute(
        "SELECT id, date, description, category, amount FROM expenses "
        "WHERE user_id = ?" + date_clause + " ORDER BY date DESC, id DESC LIMIT ?",
        (user_id,) + date_params + (limit,)
    ).fetchall()
    conn.close()
    result = []
    for row in rows:
        d = row["date"]   # "YYYY-MM-DD"
        formatted = f"{int(d[8:10]):02d} {MONTH_NAMES[int(d[5:7])]} {d[0:4]}"
        result.append({
            "id":          row["id"],
            "date":        formatted,
            "description": row["description"],
            "category":    row["category"],
            "amount":      f"₹{row['amount']:.2f}",
        })
    return result


def get_category_breakdown(user_id, date_from=None, date_to=None):
    conn = get_db()
    date_clause, date_params = _date_filter(date_from, date_to)
    rows = conn.execute(
        "SELECT category AS name, SUM(amount) AS cat_total FROM expenses "
        "WHERE user_id = ?" + date_clause + " GROUP BY category ORDER BY cat_total DESC",
        (user_id,) + date_params
    ).fetchall()
    conn.close()
    if not rows:
        return []
    grand = sum(r["cat_total"] for r in rows)
    if grand == 0:
        return []
    result = [{"name": r["name"], "total": f"₹{r['cat_total']:.2f}",
               "pct": int(r["cat_total"] / grand * 100)} for r in rows]
    # Largest category absorbs rounding remainder so pct sums to exactly 100
    result[0]["pct"] += 100 - sum(c["pct"] for c in result)
    return result
