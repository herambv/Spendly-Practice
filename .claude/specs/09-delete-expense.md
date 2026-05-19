# Spec: Delete Expense

## Overview
Allows a logged-in user to permanently delete one of their own expenses from the profile page. The stub route `GET /expenses/<id>/delete` already exists in `app.py` and must be replaced with a `POST`-only handler that validates CSRF and ownership before deleting. A small inline form on the profile transactions table triggers the delete; a JavaScript `confirm()` dialog prevents accidental deletions.

## Depends on
- 05 backend-routes-for-profile-page (transactions table in profile.html)
- 08 edit-expense (edit buttons already present on each transaction row — delete sits beside them)

## Routes
- `POST /expenses/<int:id>/delete` — deletes the expense if it belongs to the current user — logged-in only

The existing `GET /expenses/<int:id>/delete` stub must be replaced entirely with this POST handler.

## Database changes
No new tables or columns. One new helper function in `database/db.py`:

```python
def delete_expense(expense_id, user_id): ...
```

Uses `DELETE FROM expenses WHERE id = ? AND user_id = ?` (parameterised, ownership enforced in SQL).

## Templates
- **Modify:** `templates/profile.html`
  - Add a delete `<form>` (method POST, action `/expenses/<id>/delete`) next to the existing Edit button on each transaction row
  - Include a hidden `csrf_token` input
  - The submit button should have `onclick="return confirm('Delete this expense?')"` for a browser-native confirmation guard

## Files to change
- `app.py` — replace the stub `delete_expense` route; import `delete_expense` from `database/db.py`
- `database/db.py` — add `delete_expense(expense_id, user_id)` helper
- `templates/profile.html` — add inline delete form per transaction row

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` only
- Parameterised queries only — never string-format SQL
- CSRF token must be validated before any database mutation
- Ownership enforced both in Python (`get_expense_by_id` check) and in the SQL `WHERE user_id = ?` clause
- If the expense does not exist or belongs to another user, `abort(404)`
- Passwords hashed with `werkzeug` (no changes here, just maintain the rule)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- The delete button must share the same visual row as the Edit button; style with existing `.btn-*` classes — no new CSS rules unless a `.btn-danger` variant is needed (use `--danger` token if so)
- Pass `csrf_token=_get_csrf_token()` into the profile template render call so the delete forms have access to it

## Definition of done
- [ ] Visiting `GET /expenses/<id>/delete` no longer returns the stub string; the route only accepts POST
- [ ] A Delete button appears next to the Edit button on each row in the transactions table on the profile page
- [ ] Clicking Delete shows a browser `confirm()` dialog before submitting
- [ ] Cancelling the confirm dialog does not delete the expense
- [ ] Confirming the dialog submits the form, deletes the expense, flashes "Expense deleted.", and redirects to `/profile`
- [ ] A user cannot delete another user's expense (returns 404)
- [ ] Submitting the delete form without a valid CSRF token returns 403
- [ ] After deletion the expense no longer appears in the transactions table and the summary stats update accordingly
