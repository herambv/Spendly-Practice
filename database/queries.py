from database.db import get_db


def get_user_by_id(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT name, email, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    raw = row["created_at"]   # "YYYY-MM-DD HH:MM:SS"
    month_names = ["", "January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    member_since = f"{month_names[int(raw[5:7])]} {raw[0:4]}"
    initials = "".join(w[0].upper() for w in row["name"].split() if w)[:2]
    return {"name": row["name"], "email": row["email"],
            "initials": initials, "member_since": member_since}


def get_summary_stats(user_id):
    conn = get_db()
    agg = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
        "FROM expenses WHERE user_id = ?", (user_id,)
    ).fetchone()
    top = conn.execute(
        "SELECT category FROM expenses WHERE user_id = ? "
        "GROUP BY category ORDER BY SUM(amount) DESC LIMIT 1", (user_id,)
    ).fetchone()
    conn.close()
    return {
        "total_spent":       f"₹{agg['total']:.2f}",
        "transaction_count": agg["cnt"],
        "top_category":      top["category"] if top else "—",
    }


def get_recent_transactions(user_id, limit=10):
    conn = get_db()
    rows = conn.execute(
        "SELECT date, description, category, amount FROM expenses "
        "WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
        (user_id, limit)
    ).fetchall()
    conn.close()
    month_names = ["", "January", "February", "March", "April", "May", "June",
                   "July", "August", "September", "October", "November", "December"]
    result = []
    for row in rows:
        d = row["date"]   # "YYYY-MM-DD"
        formatted = f"{int(d[8:10]):02d} {month_names[int(d[5:7])]} {d[0:4]}"
        result.append({
            "date":        formatted,
            "description": row["description"],
            "category":    row["category"],
            "amount":      f"₹{row['amount']:.2f}",
        })
    return result


def get_category_breakdown(user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT category AS name, SUM(amount) AS cat_total FROM expenses "
        "WHERE user_id = ? GROUP BY category ORDER BY cat_total DESC", (user_id,)
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
