# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Activate the virtualenv (Windows)
.\exptracker\Scripts\Activate.ps1

# Run the dev server (port 5001)
python app.py

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest

# Run a single test file
pytest tests/test_auth.py
```

## Architecture

**Spendly** is a Flask expense tracker with server-rendered Jinja2 templates, raw SQLite, and vanilla CSS/JS. No ORM, no frontend framework.

```
app.py              — all routes; imports from database/db.py
database/db.py      — all SQL via sqlite3; get_db(), init_db(), seed_db(), and per-feature helpers
templates/          — Jinja2 templates; all pages extend base.html
static/css/style.css — single stylesheet; all design tokens live in :root {}
static/js/main.js   — vanilla JS; students add interactions here per step
spendly.db          — SQLite file created at startup (gitignored)
```

`app.py` calls `init_db()` and `seed_db()` inside `app.app_context()` on startup. The demo user is `demo@spendly.com` / `demo123`.

The session stores only `user_id` and `user_name`. Auth guard pattern: `if not session.get("user_id"): return redirect(url_for("login"))`.

## Design system

All colours are CSS custom properties defined in `:root` at the top of `style.css` — never use raw hex in templates or new CSS rules. Key tokens: `--ink`, `--ink-muted`, `--paper`, `--paper-card`, `--accent` (dark green), `--accent-2` (amber), `--danger`, `--border`.

Existing component classes to reuse: `.auth-card`, `.auth-section`, `.auth-container`, `.form-group`, `.form-input`, `.btn-submit`, `.btn-primary`, `.nav-cta`. New page-level styles go in `style.css` scoped with a page prefix (`.profile-...`, `.dashboard-...`).

Lucide icons are available via CDN (loaded in `base.html`): use `<i data-lucide="icon-name">` and call `lucide.createIcons()` after DOM updates.

## Development workflow

Features are built in numbered steps. Each step has:
- A spec at `.claude/specs/<NN>-<slug>.md` — written first, describes what to build
- A plan at `.claude/plans/<NN>-<slug>.md` — created in Plan Mode before implementation
- A feature branch `feature/<slug>`

**Completed steps:** 01 database-setup, 02 registration, 03 login-and-logout  
**Current step:** 04 profile-page-design

## Hard rules

- No SQLAlchemy or any ORM — raw `sqlite3` only
- Parameterised queries only — never string-format SQL
- Passwords hashed/verified with `werkzeug.security`
- All new templates must extend `base.html`
- No hardcoded hex values in templates or CSS — use CSS variables
- No inline `style=""` attributes
