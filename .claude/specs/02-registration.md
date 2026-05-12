# Spec: Registration

## Overview
Implement user account creation for Spendly. This step wires up the existing
`register.html` form to a POST handler that validates input, hashes the
password, inserts the user into the database, and redirects to the login page.
It also adds the `secret_key` required by Flask's session and flash system,
which all future authenticated steps depend on.

## Depends on
- Step 01 — Database Setup (users table must exist)

## Routes
- `GET /register` — render registration form — public (already exists, no change)
- `POST /register` — process form submission, create account — public

## Database changes
No new tables. Add a helper function `create_user(name, email, password)` to
`database/db.py` that hashes the password and inserts a row into `users`.
Returns the new user's `id` on success, raises an exception on duplicate email.

## Templates
- **Modify:** `templates/register.html` — already has `{% if error %}` block;
  no structural changes needed. Verify `name` field value is preserved on error
  so the user does not have to retype their name.

## Files to change
- `app.py` — add `POST /register` route; import `create_user` and `redirect`,
  `url_for`, `request`, `flash` from Flask; set `app.secret_key`
- `database/db.py` — add `create_user(name, email, password)` function
- `templates/register.html` — wire up form action/method and flash message display

## Files to create
None.

## New dependencies
No new dependencies. `werkzeug.security` is already installed.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use string formatting in SQL
- Passwords hashed with `werkzeug.security.generate_password_hash`
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- `app.secret_key` must be set before any session or flash usage; use a hard-coded
  dev string for now (e.g. `"spendly-dev-secret"`) — a later step will move this
  to an environment variable
- Validate server-side: name required, valid email format, password at minimum
  8 characters — do not rely solely on HTML `required` / `type="email"`
- On duplicate email return the form with a user-friendly error message
- On success redirect to `/login` — do not log the user in automatically (login
  is implemented in a later step)
- Preserve the submitted `name` and `email` values in the form on validation
  failure so the user does not need to retype them

## Definition of done
- [ ] Submitting the form with valid data creates a new row in `users` with a
      hashed password (not plaintext)
- [ ] Submitting a duplicate email shows an inline error on the register page
- [ ] Submitting with a missing name, invalid email, or password shorter than
      8 characters shows an inline error and does not insert a row
- [ ] Successful registration redirects to `/login`
- [ ] `name` and `email` fields are repopulated after a failed submission
- [ ] App starts without errors and existing seed data is unaffected
