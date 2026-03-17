# EMAIL VERIFIER SAAS - COMPLETE DOCUMENTATION
(ای میل ویریفائر ساس - مکمل دستاویزات)

---

## 1. PROJECT OVERVIEW (پراجیکٹ کا جائزہ)
This project is a high-performance **Email Verification SaaS** platform. It helps users clean their email lists by detecting invalid, disposable, or "catch-all" addresses.
یہ ایک ای میل ویریفیکیشن پلیٹ فارم ہے جو ای میل لسٹوں کو صاف کرنے اور غلط ای میلز کو پہچاننے میں مدد کرتا ہے۔

### Main Features (اہم خصوصیات):
- **Single & Bulk Verification**: Check one or thousands of emails.
- **Batch Processing**: Parallel verification (5 at a time) for speed.
- **DNS/MX Rotation**: Robust lookup using multiple DNS servers.
- **Admin Dashboard**: Manage users, plans, and credits.
- **API Access**: Use `X-API-Key` to integrate with other apps.

### Tech Stack (ٹکنالوجی):
- **Backend**: FastAPI (Python)
- **Database**: SQLite with SQLAlchemy ORM
- **Frontend**: Vanilla HTML/JS/CSS (No heavy frameworks)
- **Security**: JWT (JSON Web Tokens) & Bcrypt hashing

---

## 2. FOLDER STRUCTURE (فولڈر کا ڈھانچہ)

```text
Email Verifier/
├── main.py          → Standard FastAPI entry point. (مین سرور فائل)
├── database.py      → Database models & SQLite setup. (ڈیٹا بیس اور ٹیبلز)
├── requirements.txt → Python dependencies list. (ضروری لائبریریز)
├── .env             → Secret keys & Admin credentials. (خفیہ کیز اور سیٹنگز)
├── api_keys.db      → SQLite Database file (Generated). (ڈیٹا بیس فائل)
├── core/
│   └── verifier.py  → The "Brain" (Verification Engine). (ای میل چیک کرنے کا انجن)
├── routes/
│   ├── api.py       → Main verification API routes. (ویریفیکیشن اینڈ پوائنٹس)
│   ├── auth.py      → Login, Signup, and Admin auth. (لاگ ان اور سائن اپ)
│   ├── admin.py     → Admin controls (Credits/Plans). (ایڈمن کنٹرولز)
│   └── storage.py   → File upload & CSV downloads. (فائل سٹوریج اور ڈاؤن لوڈ)
├── middleware/
│   └── auth.py      → JWT & API Key security guard. (سیکیورٹی اور ٹوکن چیک)
├── static/
│   ├── index.html   → Dashboard & Landing page UI. (مین ویب پیج)
│   ├── app.js       → Frontend logic for dashboard. (فرنٹ اینڈ لاجک)
│   ├── styles.css   → Global styling & Animations. (ڈیزائن اور سٹائل)
│   ├── admin.html   → Admin control panel UI. (ایڈمن پینل پیج)
│   ├── admin.js     → Admin frontend logic. (ایڈمن لاجک)
│   └── admin.css    → Admin specific styling. (ایڈمن سٹائل)
└── uploads/         → Folder for user-saved CSV results. (سیو کی گئی فائلیں)
```

---

## 3. FILE BY FILE EXPLANATION (فائلوں کی تفصیل)

### `main.py`
- **Purpose**: App entry point. Configures CORS, static files, and includes all routers.
- **Connections**: Connects to all files in `routes/`.

### `core/verifier.py`
- **Purpose**: Contains the logic to perform syntax, DNS, and SMTP checks.
- **Functions**: `get_mx_records()`, `smtp_verify_async()`, `verify_email()`.

### `database.py`
- **Purpose**: Defines what data is stored.
- **Classes**: `User` (Users info), `Subscription` (Plan history), `UserFile` (Uploads list).

### `middleware/auth.py`
- **Purpose**: Decodes JWT and validates API keys for every protected request.
- **Functions**: `get_current_user()`, `get_current_admin()`.

### `static/app.js`
- **Purpose**: Handles all frontend interaction. Login, Bulk upload, and Table rendering.
- **Functions**: `startBulkVerify()`, `verifyInBatches()`, `initDash()`.

---

## 4. DATABASE TABLES (ڈیٹا بیس ٹیبلز)

### `users` (Table)
| Column | Type | Description |
|---|---|---|
| `id` | Integer | Unique identifier. |
| `email` | String | User's login email. |
| `password_hash` | String | Encrypted password (Bcrypt). |
| `plan` | String | Subscription tier (Free, Pro, etc). |
| `credits` | Integer | Remaining verification balance. |
| `api_key` | String | Global key for API access. |

### `user_files` (Table)
- Stores metadata for CSV results saved in the `uploads/` folder.
- Columns: `id`, `user_id`, `filename`, `file_size`, `created_at`.

---

## 5. API ENDPOINTS (اے پی آئی اینڈ پوائنٹس)

### USER AUTH
- `POST /api/register` (Public): Sign up a new user.
- `POST /api/login` (Public): Get a Bearer Token.
- `GET /api/me` (User): Get current balance & profile.

### VERIFICATION
- `POST /api/verify` (User): Verify a single email. (1 Credit consumed)
- `POST /api/verify-batch` (User): Verify up to 5 emails in parallel.
- `POST /api/verify-free` (Public): Limited free check (Rate limited).

### ADMIN
- `POST /admin/upgrade-plan` (Admin): Change user's credits & tier.
- `GET /admin/users` (Admin): List all platform users.
- `GET /admin/stats` (Admin): Total users & platform health.

---

## 6. USER FLOW (یوزر کیسے کام کرتا ہے)

1. **Visit**: User visits `index.html`.
2. **Auth**: User signs up (gets 100 free credits) or logs in.
3. **Dashboard**: User can see their credits and API key.
4. **Bulk Verify**:
   - User pastes emails or uploads a file.
   - `app.js` splits emails and calls `/api/verify` in batches of 5.
   - Table updates live with results.
5. **Download**: Once finished, the "Download CSV" button appears to save results locally.

---

## 7. VERIFICATION ENGINE (ویریفیکیشن انجن)

1. **Syntax Check**: Uses Regex to ensure the email looks like a real address.
2. **Disposable Check**: Checks the domain against a database of 3,000+ throwaway providers.
3. **MX/DNS Lookup**: Uses Google, Cloudflare, and Quad9 DNS servers to find the mail server.
4. **SMTP Verification**: Connects to the mail server on ports 25, 587, or 465 to ask "Does this inbox exist?".
5. **Provider Short-circuit**: Recognizes Gmail, Yahoo, AOL, and Outlook to provide instant results without getting blocked.

---

## 8. STATUS TYPES EXPLAINED (سٹیٹس کی تفصیل)

| Status | Meaning | Score | Color |
|---|---|---|---|
| **ACCEPTED** | Inbox exists and is ready to receive mail. | 98 | Green |
| **REJECTED** | Inbox does not exist (Bounce). | 0 | Red |
| **CATCH-ALL** | Server accepts all emails; can't confirm existence. | 60 | Purple |
| **DISPOSABLE** | Email belongs to a temporary/throwaway provider. | 10 | Grey |
| **GREYLISTED** | Server asked to retry later. | 45 | Blue |
| **SPAM BLOCK** | Our IP is blocked by the receiver's server. | 35 | Yellow |
| **TIMEOUT** | Server was too slow to respond. | 30 | Yellow |
| **MX ERROR** | DNS lookup failed (Domain might be invalid). | 2 | Red |

---

## 9. PRICING PLANS (پرائسنگ پلانز)

- **FREE**: 100 Credits (Fixed). Basic features.
- **STARTER**: 5,000 Credits. Faster processing.
- **PRO**: 50,000 Credits. Full API & Bulk access.
- **ENTERPRISE**: Unlimited Credits for large scale.

---

## 10. HOW TO RUN THE PROJECT (کیسے چلائیں)

**1. Standard Setup**:
```bash
# Install dependencies
pip install -r requirements.txt

# Run server
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```
**2. Access UI**: Open `http://127.0.0.1:8000/static/index.html`.
**3. Admin Access**: Open `http://127.0.0.1:8000/static/admin.html`.
**4. Admin Login**: Credentials are located in the `.env` file (`ADMIN_USERNAME` and `ADMIN_PASSWORD`).

---

## 11. SECURITY FEATURES (حفاظتی خصوصیات)

- **JWT Auth**: Users receive a signed token upon login. No session storage needed.
- **Role Isolation**: Admin routes require a specific `admin_token` with `role: admin` payload.
- **API Key Security**: Users can use their API Key for server-to-server calls safely.
- **Rate Limiting**: `slowapi` prevents brute-force attacks and bot abuse.

---

## 12. KNOWN ISSUES & LIMITATIONS (مسائل اور حدود)

- **Catch-All Domains**: Major providers (Outlook, GSuite) often hide inbox existence. We mark these as `CATCH-ALL`.
- **IP Reputation**: If your server IP is blacklisted, you will see many `SPAM BLOCK` results.
- **SMTP Blocks**: Port 25 is often blocked by ISPs (Azure/AWS). Use a VPS that allows port 25 for best results.

---
**Documentation Created by Antigravity AI**
(دستاویزات اینٹی گریوٹی اے آئی نے تیار کی ہیں)
