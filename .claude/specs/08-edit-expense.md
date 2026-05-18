# Spec: Edit Expense

## Overview
This feature lets logged-in users edit an existing expense via a pre-filled form. It replaces the stub route at `GET /expenses/<id>/edit` with a real `GET`/`POST` handler that loads the expense, validates ownership, validates input, and updates the row in the `expenses` table. On success the user is redirected to `/profile` with a confirmation flash message. It also wires up the Edit action link in the profile transactions table, which currently has no per-row actions.

## Depends on
- 01 database-setup — `expenses` table must exist
- 03 login-and-logout — session auth required
- 04/05 profile-page — edit link lives in the transactions table on `/profile`
- 07 add-expense — shares the same form pattern and CSS classes

## Routes
- `GET  /expenses/<int:id>/edit` — load the expense and render a pre-filled edit form — logged-in only
- `POST /expenses/<int:id>/edit` — validate and update the expense, redirect to `/profile` — logged-in only

## Database changes
No new tables or columns. Two new helper functions must be added to `database/db.py`:

- `get_expense_by_id(expense_id, user_id)` — fetches a single expense row by `id` WHERE `user_id` matches; returns `None` if not found or not owned by the session user
- `update_expense(expense_id, user_id, amount, category, date, description)` — updates `amount`, `category`, `date`, `description` for the given `id` WHERE `user_id` matches (ownership enforced in SQL)

`get_recent_transactions` in `database/queries.py` must be updated to include the expense `id` in each returned dict so the template can build the edit link.

## Templates
- **Create:** `templates/edit_expense.html` — pre-filled form identical in structure to `add_expense.html`; form action posts to `url_for('edit_expense', id=expense.id)`
- **Modify:** `templates/profile.html` — add an "Actions" `<th>` column to the transactions table and an Edit link (`<a href="{{ url_for('edit_expense', id=tx.id) }}">`) in each `<tr>`

## Files to change
- `app.py` — replace the stub `edit_expense` route with a real `GET`/`POST` handler; import `get_expense_by_id` and `update_expense` from `database/db.py`
- `database/db.py` — add `get_expense_by_id()` and `update_expense()` helpers
- `database/queries.py` — include `id` field in `get_recent_transactions()` return dicts
- `templates/profile.html` — add Actions column header and per-row Edit link
- `static/css/style.css` — add `.tx-actions` style for the actions column (small, muted link)

## Files to create
- `templates/edit_expense.html` — the edit-expense form template

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only
- Parameterised queries only — never string-format SQL
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- No inline `style=""` attributes
- Auth guard: redirect to `/login` if `session.get("user_id")` is falsy
- Ownership guard: if `get_expense_by_id` returns `None`, call `abort(404)`
- CSRF protection: validate `request.form.get("csrf_token") != session.get("csrf_token")` → `abort(403)`
- Allowed categories (same fixed list as add-expense): `Food`, `Transport`, `Bills`, `Health`, `Entertainment`, `Shopping`, `Other`
- Amount must be a positive number (> 0); reject non-numeric or zero/negative values
- Date must be a valid ISO date (`YYYY-MM-DD`)
- Description is optional (max 200 chars); truncate silently if exceeded
- On validation failure, re-render the form with an error message and preserve filled-in values
- On success, flash a confirmation message and redirect to `url_for("profile")`
- The `update_expense` SQL must include `WHERE id = ? AND user_id = ?` to enforce ownership at the DB layer

## Definition of done
- [ ] Visiting `GET /expenses/<id>/edit` while logged out redirects to `/login`
- [ ] Visiting `GET /expenses/<id>/edit` for an expense owned by the logged-in user shows a pre-filled form with the correct amount, category, date, and description
- [ ] Visiting `GET /expenses/<id>/edit` for an expense belonging to a different user returns 404
- [ ] Submitting the form with all valid fields updates the row in `expenses` and redirects to `/profile` with a success flash message
- [ ] The updated values are reflected in the transactions list on `/profile`
- [ ] Submitting with a missing or zero amount shows an inline error and preserves other field values
- [ ] Submitting with an invalid date shows an inline error and preserves other field values
- [ ] Submitting with a category not in the allowed list is rejected with an error
- [ ] Each row in the profile transactions table has an Edit link that navigates to the correct edit URL
- [ ] The edit form is styled consistently with the rest of Spendly (uses CSS variables, matches the add-expense form aesthetic)
