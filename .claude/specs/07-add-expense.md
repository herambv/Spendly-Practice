# Spec: Add Expense

## Overview
This feature lets logged-in users add a new expense via a simple form. It replaces the stub route at `GET /expenses/add` with a full `GET`/`POST` handler that validates input and inserts a row into the existing `expenses` table. On success the user is redirected to `/profile` with a confirmation flash message. This is the core data-entry feature of Spendly — without it, users can only view seeded demo data.

## Depends on
- 01 database-setup — `expenses` table must exist
- 03 login-and-logout — session auth required
- 04/05 profile-page — redirect destination after submission

## Routes
- `GET  /expenses/add` — render the add-expense form — logged-in only
- `POST /expenses/add` — validate and insert expense, redirect to `/profile` — logged-in only

## Database changes
No new tables or columns. The `expenses` table already exists:

```
expenses(id, user_id, amount, category, date, description, created_at)
```

A new helper function `add_expense(user_id, amount, category, date, description)` must be added to `database/db.py`.

## Templates
- **Create:** `templates/expenses/add.html` — full-page form with fields for amount, category, date, and description; extends `base.html`
- **Modify:** none

## Files to change
- `app.py` — replace the stub `add_expense` route with a real `GET`/`POST` handler; import `add_expense` from `database/db.py`
- `database/db.py` — add `add_expense()` helper function
- `static/css/style.css` — add `.expense-form-*` scoped styles for the new page

## Files to create
- `templates/expenses/add.html` — the add-expense form template

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only
- Parameterised queries only — never string-format SQL
- Passwords hashed with werkzeug (not applicable here, but preserve existing pattern)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline `style=""` attributes
- Auth guard: redirect to `/login` if `session.get("user_id")` is falsy
- Allowed categories (fixed list, validated server-side): `Food`, `Transport`, `Bills`, `Health`, `Entertainment`, `Shopping`, `Other`
- Amount must be a positive number (> 0); reject non-numeric or zero/negative values
- Date must be a valid ISO date (`YYYY-MM-DD`); default the field to today's date
- Description is optional (max 200 chars); truncate silently if exceeded
- On validation failure, re-render the form with an error message and preserve filled-in values
- On success, flash a confirmation message and redirect to `url_for("profile")`

## Definition of done
- [ ] Visiting `GET /expenses/add` while logged out redirects to `/login`
- [ ] Visiting `GET /expenses/add` while logged in shows a form with Amount, Category (dropdown), Date, and Description fields
- [ ] Date field defaults to today's date on page load
- [ ] Submitting the form with all valid fields inserts a row into the `expenses` table and redirects to `/profile` with a success flash message
- [ ] The new expense appears in the recent transactions list on `/profile`
- [ ] Submitting with a missing or zero amount shows an inline error and preserves other field values
- [ ] Submitting with an invalid date shows an inline error and preserves other field values
- [ ] Submitting with a category not in the allowed list is rejected with an error
- [ ] The form page is styled consistently with the rest of Spendly (uses CSS variables, matches nav/card aesthetic)
