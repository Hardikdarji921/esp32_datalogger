# Copilot instructions for esp32_datalogger

This file gives focused, actionable context for an AI coding agent working on this repository.
Keep entries short and only reference patterns discoverable in the codebase.

## Big picture
- Backend: a Flask app in `backend/app.py` (uses Flask-SocketIO, Flask-Mail, Flask-Migrate, SQLAlchemy). REST endpoints live under `/api/*` (e.g. `/api/live-data`, `/api/register`, `/api/login`). SocketIO is used to push device updates to web clients (emits on channel `device_update_{device_id}`).
- Frontend: static HTML pages at the repository root (e.g. `login.html`, `HomePage.html`, `reset_password.html`) — the backend uses relative links (e.g. the password reset URL is `reset_password.html?token=...`) so the static files are expected to be served from the same host/container.
- Device integration: ESP32 sketch (`arduino file/ESP32_Data logger_V1.ino`) shows the device-side design. Devices either POST telemetry to `/api/live-data` or use MQTT (sketch contains Mock MQTT logic). The sketch also exposes a web configuration portal (AP mode) — configuration keys map to backend device fields (e.g. VIN, machine name).
- Storage: SQLAlchemy models are defined in `backend/app.py` (Device, User, LogFolder, LogFile). Default DB is SQLite at `backend/database.db`, but `DATABASE_URL` env var overrides to allow Postgres (psycopg2 present in `requirements.txt`). Alembic migrations live under `backend/migrations/`.

## Important run / dev workflows (concrete)
- Install dependencies and run locally (from repo root):
  - cd into backend and install: `pip install -r backend/requirements.txt`
  - initialize DB (drops/creates tables): `python backend/init_db.py` (this resets DB)
  - or seed without dropping: `python backend/seed_db.py` (assumes tables exist)
  - run the server for development: `python backend/app.py` (app starts via `socketio.run(app, debug=True)`).
- Docker: `backend/Dockerfile` uses Gunicorn and expects the Flask app object as `app` in `app.py`. Build & run pattern:
  - Build: `docker build -t esp32_backend ./backend`
  - Run: `docker run -e PORT=8080 -p 8080:8080 -e DATABASE_URL="<your-db>" esp32_backend`
  - Note: container command is `gunicorn --bind :$PORT --workers 1 --threads 8 app:app`.
- Migrations: Flask-Migrate / Alembic present. Typical pattern (run from `backend/`):
  - `export FLASK_APP=app.py`
  - `flask db upgrade` (applies migrations in `backend/migrations/`)

## Authentication & API conventions
- JWT tokens: the backend expects a JWT passed in header `x-access-token` (see `token_required` decorator in `backend/app.py`). Use this header in API requests.
- Admin endpoints require `admin_required` decorator. Example endpoints: `POST /api/admin/approve/<id>`, `GET /api/admin/users`.
- Passwords are stored hashed via Werkzeug `generate_password_hash` / `check_password_hash`.

## Integration points & external dependencies
- Mail: configured with Flask-Mail; credentials are currently set in `backend/app.py` (MAIL_USERNAME, MAIL_PASSWORD). Reset links generated are relative (`reset_password.html`) so mail clients must be able to reach the same host serving static files.
- SocketIO: used to stream live device updates. Use the event name `device_update_{device_id}` to subscribe to live data.
- Devices: The Arduino sketch demonstrates how devices format telemetry and configuration keys (VIN, engine_can_baud, ttc_can_baud, machine name). Use the sketch as a reference when adding or changing fields.

## Project-specific patterns and gotchas
- Static frontend lives at repository root (not in `backend/templates`). When running locally via `python backend/app.py` the backend does not automatically serve all root static HTML files — tests or hosting may expect a static file server or container to serve them. Check how you run the app in production (Dockerfile copies entire repo into the image).
- DB initialization: `init_db.py` will drop all tables and recreate them (use carefully). `seed_db.py` is additive and will skip duplicates.
- Environment-aware DB: `app.config['SQLALCHEMY_DATABASE_URI']` uses `DATABASE_URL` if present; otherwise falls back to SQLite at `backend/database.db`.
- Secret handling: `SECRET_KEY` and mail password are hard-coded in `backend/app.py`. If you modify auth logic, ensure secrets are moved to env vars.

## What to change or verify before code changes
- If you modify models in `backend/app.py`, update or generate a migration (`flask db migrate`) and apply (`flask db upgrade`).
- If you add new API endpoints that should push live updates, follow the pattern: accept JSON in `/api/...`, validate `device_id`, then `socketio.emit(f'device_update_{device_id}', data)`.

## Where to look for examples
- Model/endpoint examples: `backend/app.py` (User, Device, LogFolder, LogFile; token decorators; routes)
- DB scripts: `backend/init_db.py`, `backend/seed_db.py` (shows JSON shapes used in Device.parameters and displayParameters)
- Docker/gunicorn packaging: `backend/Dockerfile`
- Device behavior and field names: `arduino file/ESP32_Data logger_V1.ino` (configuration keys, baud rates, mock telemetry format)

If anything in this file is unclear or you want more details (e.g. example curl requests, SocketIO client snippets, or where static files are expected to be hosted), tell me which area to expand and I'll iterate.
