# Spec: Login and Logout

## Overview
Implement session-based authentication for Spendly. This step wires up the
existing `login.html` form to a POST handler that validates credentials against
the database, starts a Flask session on success, and redirects to the user's
dashboard (placeholder for now). It also implements the logout route that clears
the session and redirects to the landing page. Finally, it updates `base.html`
so the navigation reflects the user's current auth state — showing account links
when logged in and sign-in/register links when logged out.

## Depends on
- Step 01 — Database Setup (users table must exist)
- Step 02 — Registration (users can exist in the database to log in with)

## Routes
- `GET /login` — render login form — public (already exists, no change needed)
- `POST /login` — validate credentials, start session, redirect — public
- `GET /logout` — clear session, redirect to landing page — logged-in (currently a stub)

## Database changes
No new tables or columns. Add a helper function `get_user_by_email(email)` to
`database/db.py` that returns the matching user row (as `sqlite3.Row`) or `None`
if no user exists with that email.

## Templates
- **Modify:** `templates/login.html` — already has `{% if error %}` block and
  correct form action/method; preserve the submitted `email` value on failed
  login so the user does not have to retype it (add `value="{{ email or '' }}"`)
- **Modify:** `templates/base.html` — update `<nav>` to branch on
  `session.get('user_id')`: when logged in show the user's name and a
  "Sign out" link; when logged out show the existing "Sign in" / "Get started"
  links

## Files to change
- `app.py` — implement `POST /login` route and `GET /logout` route; import
  `session` from Flask and `check_password_hash` from `werkzeug.security`;
  import `get_user_by_email` from `database.db`
- `database/db.py` — add `get_user_by_email(email)` function
- `templates/login.html` — repopulate `email` field on failed submission
- `templates/base.html` — add conditional nav links based on session state

## Files to create
None.

## New dependencies
No new dependencies. `werkzeug.security` and Flask's `session` are already
available.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use string formatting in SQL
- Passwords verified with `werkzeug.security.check_password_hash`
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- Store only `user_id` and `user_name` in the session — never store the
  password hash or the full user row
- On failed login (unknown email or wrong password) show a single generic error
  message: "Invalid email or password." — do not reveal which field was wrong
- On success redirect to `/` for now (dashboard route is a future step)
- `GET /logout` must use `session.clear()` and then redirect — never render a
  template
- The `get_user_by_email` function must return `None` (not raise) when no user
  is found

## Definition of done
- [ ] Submitting the login form with a valid email and correct password starts
      a session and redirects away from `/login`
- [ ] Submitting with an unknown email shows "Invalid email or password." inline
      and does not start a session
- [ ] Submitting with a correct email but wrong password shows the same generic
      error and does not start a session
- [ ] The submitted email is repopulated in the form after a failed login
- [ ] Visiting `/logout` clears the session and redirects to the landing page
- [ ] The navbar shows "Sign in" and "Get started" for unauthenticated visitors
- [ ] The navbar shows the logged-in user's name and a "Sign out" link for
      authenticated users
- [ ] App starts without errors and existing seed data is unaffected
- [ ] The demo user (`demo@spendly.com` / `demo123`) can log in successfully
