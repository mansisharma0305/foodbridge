# FoodBridge: Smart Food Donation and Redistribution Platform

A Flask web application that connects surplus-food **donors** (restaurants, hotels, canteens, hostels, event
organizers) with **recipients** (NGOs, shelters, community kitchens) so suitable food is collected before it becomes
waste. College-level CSE / Data Science project.

> **Food-safety notice.** FoodBridge is a *coordination* platform. It does not inspect or certify food, and
> appearance, smell or taste never prove food is safe. Users must follow applicable local food-safety rules.

## Objectives
1. Reduce food waste by shortening the path from surplus to recipient.
2. Give donors and NGOs a clear, auditable request → approval → collection → completion workflow.
3. Measure impact honestly (per unit, never mixing kg / servings / packets).

## Features
- Landing page with live impact statistics; public impact dashboard (Chart.js).
- Registration, login/logout, profile and password change; roles: **Donor**, **Recipient/NGO**, **Admin**.
- Donors: post, edit (while unrequested) and cancel listings; approve/reject requests; mark collected/completed.
- Recipients: search & filter (name, category, location, unit + minimum quantity, availability, sort), request food,
  track status with timestamps, confirm receipt.
- Workflow: `available → requested → approved → collected → completed`, plus rejection, cancellation and automatic
  expiry. Duplicate requests, unavailable/expired listings and invalid transitions are blocked on the server, and a
  partial unique index guarantees one active request per listing at the database level.
- Admin dashboard: user / listing / request counts, pending requests, completed donations, quantities by unit,
  user activation, listing removal, reported-issue review.
- Privacy: pickup address and contact phone are revealed only after the donor approves.
- Security: hashed passwords, CSRF protection, server-side authorization, POST-only state changes, secure cookie
  settings, security headers + CSP, basic rate limiting, open-redirect protection.

## Technology
Python 3.10+ · Flask · SQLAlchemy (Flask-SQLAlchemy) · SQLite · Flask-Login · Flask-WTF/WTForms · Jinja2 ·
Bootstrap 5 · Chart.js · pytest.

## Prerequisites
Python 3.10 or newer and pip. Internet access in the browser (Bootstrap and Chart.js load from the jsDelivr CDN; the
app is usable without it but unstyled; see Troubleshooting).

## Installation

**macOS / Linux**
```bash
cd foodbridge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # paste the output as SECRET_KEY in .env
```

**Windows (PowerShell)**
```powershell
cd foodbridge
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
py -c "import secrets; print(secrets.token_hex(32))"
```
(Windows cmd: `.venv\Scripts\activate.bat` and `copy .env.example .env`.)

## Environment variables (`.env`)
| Variable | Purpose |
|---|---|
| `APP_ENV` | `development` (default) or `production` (enforces SECRET_KEY, secure cookies, HSTS) |
| `SECRET_KEY` | Required in production. In development a temporary random key is used if unset |
| `DATABASE_URL` | Default `sqlite:///foodbridge.db` (stored in `instance/`) |
| `APP_TIMEZONE` | Default `Asia/Kolkata`. All stored times are local wall-clock in this zone |
| `MAX_PICKUP_WINDOW_HOURS` | Longest allowed pickup deadline from now (default 168) |
| `ADMIN_EMAIL`, `ADMIN_NAME`, `ADMIN_PASSWORD` | Optional inputs for `create-admin` |
| `DEMO_PASSWORD` | Optional password for sample accounts (default `Demo@1234`) |

## Database setup, admin and sample data
Tables are created automatically at start-up. Explicit commands (same on all platforms):
```bash
flask --app run init-db                 # create tables (idempotent)
flask --app run create-admin            # prompts for email + password (no public admin signup)
flask --app run seed-demo               # clearly labelled SAMPLE users and donations
flask --app run seed-demo --reset       # remove old sample data and recreate it
flask --app run reset-db                # DANGER: drops everything
```
Run the app:
```bash
python run.py        # http://127.0.0.1:5000
# or: flask --app run run --debug
```

## Demo accounts (after `seed-demo`; password `Demo@1234` unless `DEMO_PASSWORD` is set)
| Role | Email |
|---|---|
| Donor | `donor1@demo.foodbridge.test`, `donor2@…`, `donor3@…` |
| Recipient | `recipient1@demo.foodbridge.test`, `recipient2@…`, `recipient3@…` |
| Admin | none seeded; create yours with `create-admin` |

Suggested live demo: log in as `donor1` and post food → as `recipient1` search, request → as `donor1` approve →
mark collected → as `recipient1` confirm received → open **Impact** and the admin dashboard.
`seed-demo` refuses to run when `APP_ENV=production` unless `--force` is passed.

## Tests
```bash
pytest            # whole suite
pytest tests/test_workflow.py -v
```
The suite covers registration/login, invalid login, role-based access, donation validation, browsing/search,
duplicate requests, approve/reject, unauthorized changes, collection/completion, expired/unavailable listings,
admin access, CSRF, rate limiting, seeding and the one-active-request database guarantee.

## Project layout
```
foodbridge/
  app/  __init__.py (factory)  models.py  forms.py  services.py  constants.py  utils.py
        decorators.py  ratelimit.py  cli.py  seed.py  extensions.py
        main/ auth/ donor/ recipient/ admin/   (blueprints: __init__.py + routes.py)
        templates/ (+ _macros.html, base.html)   static/ (css, js, img)
  tests/  config.py  run.py  requirements.txt  pytest.ini  .env.example  .gitignore
  README.md  PROJECT_REPORT.md
```
Note: the package file is `app/__init__.py` (two underscores each side).

## Security measures implemented
Password hashing (Werkzeug scrypt); CSRF tokens on every form; role checks in decorators and ownership/participant
checks in `services.py`; all state changes are POST; input validated server-side; HttpOnly / SameSite=Lax cookies
(Secure in production); CSP, X-Frame-Options, nosniff, Referrer-Policy, `Cache-Control: no-store`; generic login
errors with timing equalisation; same-site `next` redirects only; LIKE-wildcard escaping; contact data hidden until
approval; in-memory rate limiting on login, registration, password change and reports.

### Still required before a real production deployment
- Serve over HTTPS behind a real server (gunicorn/waitress + nginx), set `APP_ENV=production` and a strong `SECRET_KEY`.
- Replace the in-memory limiter with Flask-Limiter + Redis; configure proxy headers (`ProxyFix`) for correct client IPs.
- Use PostgreSQL/MySQL and add migrations (Flask-Migrate/Alembic); automated backups.
- Email verification, password reset, account lockout/MFA for admins, audit logging, monitoring.
- Self-host Bootstrap/Chart.js or add Subresource Integrity hashes; tighten CSP (remove `'unsafe-inline'` styles).
- Registration reveals whether an email exists; use generic responses plus email verification in production.
- Legal review (liability, food-business registration, data-protection / privacy policy, terms of use).
- Penetration test and dependency vulnerability scanning.

## Troubleshooting
- **`ModuleNotFoundError`**: activate the virtualenv and re-run `pip install -r requirements.txt`.
- **`flask: command not found`**: use `python -m flask --app run ...`.
- **Unstyled pages / no charts**: the CDN is blocked; connect to the internet, or download Bootstrap and Chart.js into
  `app/static/vendor/` and change the URLs in `base.html`, `impact.html`, `admin/dashboard.html` (charts fall back to text).
- **Time zone errors on Windows**: `pip install tzdata` (already in requirements).
- **Logged out after each restart in development**: set `SECRET_KEY` in `.env`.
- **"Sample data already exists"**: use `seed-demo --reset`.
- **Schema changed after pulling new code**: this project has no migrations; run `reset-db` (development only).
- **429 Too many attempts**: wait a few minutes, or restart the dev server (limiter is in memory).

## Known limitations & future improvements
- One active request per listing (first come, first served; donor may reject).
- No partial quantities, images, notifications (email/SMS), maps/geolocation, ratings, or multilingual UI.
- Time stored as local wall-clock time (single time zone).
- Future: Flask-Migrate, email notifications, map-based search, demand forecasting and waste analytics (Data
  Science extension), donor/recipient ratings, REST API + mobile app.
