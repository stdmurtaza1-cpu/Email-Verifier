# Veridrax

## Overview
A high-performance Email Verification SaaS platform. Users can verify email addresses individually or in bulk, checking for syntax validity, disposable domains, MX records, and performing SMTP handshakes.

## Tech Stack
- **Backend:** Python 3.12 + FastAPI + Celery
- **Database:** PostgreSQL (Replit built-in, via SQLAlchemy ORM)
- **Cache/Queue:** Redis (local, started via start.sh)
- **Frontend:** Vanilla HTML/JS/CSS (SPA served by FastAPI)
- **SMTP Verification:** dnspython, aiosmtplib

## Project Structure
- `main.py` — FastAPI app entry point, mounts routes and static files
- `database.py` — SQLAlchemy models and DB setup (auto-creates tables on startup)
- `cache.py` — Redis async helpers
- `core/verifier.py` — Core email verification logic (syntax, DNS, SMTP)
- `core/worker_registry.py` — Worker heartbeat/identity in Redis
- `routes/` — API endpoints (api, auth, admin, billing, partner, storage)
- `middleware/` — JWT and API key auth middleware
- `static/` — Frontend assets (index.html, admin.html, app.js, etc.)
- `uploads/` — CSV uploads and bulk job results
- `celery_worker.py` — Celery background task worker entry point
- `start.sh` — Startup script: launches Redis then uvicorn on port 5000

## Running the App
```bash
bash start.sh
```
This starts Redis (port 6379) and the FastAPI server (port 5000).

## Environment Variables
Set in Replit Secrets/Env Vars:
- `DATABASE_URL` — PostgreSQL connection string (auto-set by Replit DB)
- `REDIS_URL` — Redis URL (default: redis://127.0.0.1:6379/0)
- `JWT_SECRET` — JWT signing secret
- `ADMIN_JWT_SECRET` — Admin JWT secret
- `ADMIN_USERNAME` / `ADMIN_PASSWORD` — Admin credentials
- `HELO_DOMAIN` — Domain used in SMTP HELO/EHLO probes
- `SMTP_SOURCE_IPS` — Comma-separated IPs for SMTP rotation (optional)
- `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` — Stripe billing (optional)
- `SENDGRID_API_KEY` — Email sending (optional)

## Key Routes
- `/` — Landing page (SPA)
- `/admin-panel` — Admin dashboard
- `/api/` — Verification API endpoints
- `/api/auth/` — Auth (register, login, JWT)
- `/api/admin/` — Admin management
- `/billing/` — Stripe billing webhooks
- `/api/storage/` — File upload/download
- `/api/partner/` — Partner API

## Database
Replit PostgreSQL. Tables are auto-created by SQLAlchemy on startup:
- `users`, `subscriptions`, `user_files`, `email_results`, `smtp_ips`, `page_contents`
