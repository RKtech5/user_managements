# UserHub — Flask + MongoDB User Management System

A local-first learning project with login, registration, password reset, profile photos, user records, search, and CRUD actions.

## Requirements

- Python 3.10 or newer
- MongoDB Community Server running on this computer
- A web browser

The database works offline after MongoDB is installed and running. Google Fonts are optional; the page uses fallback fonts if the internet is unavailable.

## 1. Start MongoDB

Install MongoDB Community Server for your operating system. On Windows, it can run as a Windows service. Confirm that the local server is running on `127.0.0.1:27017`. You do not need MongoDB Atlas.

## 2. Create a virtual environment

Open a terminal in this folder:

### Windows PowerShell
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks activation, use Command Prompt:
```bat
py -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
copy .env.example .env
```

### macOS / Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

## 3. Configure `.env`

Open `.env` and replace `SECRET_KEY` with a long random value. You can generate one by running:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Keep `.env` private; do not commit it to public source control.

Default database:
- MongoDB URI: `mongodb://127.0.0.1:27017/`
- Database: `user_management`
- Collections: `accounts`, `user_records`, `password_resets`

## 4. Run the application

```bash
python app.py
```

Open http://127.0.0.1:5000 in your browser. Register an account, log in, and add records.

## Forgot password in local development

If SMTP settings are blank, a reset link is printed in the terminal where Flask is running. Copy the full link into your browser. This fallback is for local development only. To email reset links, configure the `MAIL_*` values in `.env` with an SMTP provider and set `APP_BASE_URL` to the public HTTPS URL. Never expose reset tokens in logs on a public deployment.

## Features

- Shared responsive design and logo, with footer on each page
- Registration and login with hashed passwords
- CSRF protection on forms
- Forgot/reset password links with 30-minute expiry and single-use tokens
- Profile photo and record photo uploads (JPG/JPEG/PNG/WEBP)
- User-specific records and ownership checks
- Search by name, city, number, and role
- Add, edit/update, and delete with confirmation
- MongoDB indexes for unique email and record lookups

## Important notes

- This is a learning starter, not a fully hardened public production deployment.
- Before public hosting, disable Flask debug mode, use HTTPS, set secure cookies, add login/reset rate limiting, configure email delivery, backups, monitoring, and a production WSGI server.
- Upload size is capped at 5 MB per request. Only common image extensions are accepted. For higher-risk deployments, inspect file content (not just extension), re-encode images, and serve uploads from a separate host.
- A MongoDB TTL index may take a short time to remove expired reset documents, but the route checks expiry directly.
- Do not put sensitive personal information into a public demo.
