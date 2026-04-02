# EMAIL VERIFIER SAAS
**COMPLETE OFFICIAL DOCUMENTATION**

---

## 1. COVER PAGE

- **Project Name:** Email Verifier SaaS
- **Version:** 1.0.0 (Production Release)
- **Date:** 1st April 2026
- **Author:** Senior Software Architect & Technical Documentation Team
- **Document Status:** Final

---

## 2. TABLE OF CONTENTS

1. **Cover Page**
2. **Table of Contents**
3. **Executive Summary**
4. **Project Overview**
5. **System Architecture**
6. **Database Design**
7. **API Documentation**
8. **Core Modules Explanation**
9. **Frontend Documentation**
10. **Security Documentation**
11. **Deployment Guide**
12. **Known Issues & Limitations**
13. **Future Roadmap**
14. **Glossary**

---

## 3. EXECUTIVE SUMMARY

The **Email Verifier SaaS** is a high-performance, scalable platform designed to help businesses, marketers, and developers clean their email lists by detecting invalid, disposable, or "catch-all" email addresses. Email deliverability is a critical factor in modern digital marketing. Sending emails to non-existent or spam-trap addresses can severely damage a sender's root IP reputation and domain trust score, ultimately leading to legitimate emails being marked as spam.

*(Yeh platform khass tor par un businesses aur marketers ke liye design kiya gaya hai jinhein apni email marketing campaigns ki deliverability ko behtar banana hota hai. Is system ka main maqsad bounce rates ko kam karna aur sender ki reputation ko protect karna hai. Agar aap aisi emails par messages bhejte hain jo exist nahi karti, toh aapki domain ko block ya spam mein daal diya jata hai. Is tool ka istemaal karke aap pehle hi apni list ko saf kar sakte hain.)*

### Target Audience
- **Digital Marketers:** Looking to clean bulk CSV lists before blasting campaigns.
- **SaaS Developers:** Needing an API to verify user sign-ups in real time.
- **Enterprise Businesses:** Requiring strict compliance and bounce-rate minimization.

### Problem it Solves
- High bounce rates from outdated CRM data.
- Fraudulent sign-ups using disposable/temporary emails.
- Getting blocked by major ISPs (Gmail, Yahoo) due to poor sender scores.

---

## 4. PROJECT OVERVIEW

### Vision and Goals
The primary vision of this system is to provide an enterprise-grade, blazing-fast email verification solution that is highly accurate but operates with a lightweight footprint. The goal is to verify an email address within milliseconds to seconds, ensuring zero false positives.

*(Hamara main goal ek aisa system banana hai jo na sirf fast ho balki highly accurate bhi ho. Ek aam user ke pas hazaron emails ki file ho sakti hai, isliye system ko itna taqatwar hona chahiye ke wo parallel processing ke zariye chand minutes mein puri file verify kar de.)*

### Core Features List
- **Real-Time Single Verification:** Verify individual emails instantly via Dashboard or API.
- **Bulk CSV Processing:** Upload large CSV lists and process them concurrently.
- **Batch Processing Engine:** Parallel verification workers (e.g., checking 5-10 at a time) for speed optimization.
- **DNS/MX Server Rotation:** Intelligent querying of DNS servers (Google, Cloudflare, Quad9) to avoid rate limits.
- **SMTP Handshake:** Direct connection to destination mail servers (without sending an actual email) to verify mailbox existence.
- **Developer API & Webhooks:** Full RESTful API with API Key authentication.
- **Admin Control Panel:** Dashboard to manage users, update credits, change plans, and view system statistics.

### Technology Stack

| Component | Technology | Purpose |
|---|---|---|
| **Backend Framework** | FastAPI (Python) | High-performance, async REST API handling. |
| **Database** | SQLite & SQLAlchemy ORM | Lightweight relational data storage. |
| **Frontend UI** | HTML5, Vanilla JS, CSS3 | Clean, fast, framework-less client dashboard. |
| **Authentication** | JWT & API Keys | Stateless session management & API security. |
| **Encryption** | Bcrypt | Password hashing and security. |
| **Task Queue** | Python Asyncio/Celery | Background task processing for bulk uploads. |

---

## 5. SYSTEM ARCHITECTURE

The architecture follows a standard client-server model tailored for heavy I/O bound network operations (DNS MX lookups and SMTP connections). 

*(System ka architecture is tarah design kiya gaya hai ke wo bohat saari network requests ko ek waqt mein handle kar sake. FastAPI async hone ki wajah se threads ko block nahi karti, jo is operation ke liye best hai.)*

### High-Level Architecture Diagram

```text
+-------------------------------------------------------------+
|                      CLIENT LAYER                           |
|  [ Web Browser / Dashboard ]       [ Developer API Client ] |
+------------------------------+------------------------------+
                               | (HTTP/HTTPS REST)
                               v
+-------------------------------------------------------------+
|                  API GATEWAY & ROUTING                      |
|  +--------------------+   +---------------------------+     |
|  |   Auth Middleware  |---| Rate Limiter (SlowAPI)    |     |
|  |  (JWT / API Keys)  |   | (Prevents Bot Abuse)      |     |
|  +--------------------+   +---------------------------+     |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                   APPLICATION LOGIC                         |
|  +----------------+  +----------------+  +----------------+ |
|  |  User Routes   |  | Storage Routes |  | Admin Routes   | |
|  +----------------+  +----------------+  +----------------+ |
+------------------------------+------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|             VERIFICATION ENGINE (core/verifier.py)          |
|                                                             |
|  [1. Syntax Check] -> [2. Disposable DB Check]              |
|          |                        |                         |
|          v                        v                         |
|  [3. DNS / MX Lookup] -> [4. SMTP Handshake & Validation]   |
+------------------------------+---------------+--------------+
                               |               |
               (Async Writes)  v               v (Network Calls)
+------------------------------------+  +---------------------+
|        DATA PERSISTENCE LAYER      |  |   EXTERNAL WORLD    |
|  +--------------+ +--------------+ |  |  - Google DNS       |
|  | SQLite DB    | | Local CSV    | |  |  - Target SMTP      |
|  | (api_keys.db)| | Uploads Dir  | |  |    Servers          |
|  +--------------+ +--------------+ |  +---------------------+
+------------------------------------+
```

### Component Descriptions
1. **API Gateway (FastAPI Entry):** The `main.py` entry point routes incoming HTTP requests. It attaches Cross-Origin Resource Sharing (CORS) rules to allow external frontends.
2. **Auth Middleware:** Validates whether a request holds a valid JWT (for dashboard users) or a valid `X-API-Key` header (for automated scripts).
3. **Verification Engine:** The heart of the application. It takes an email, parses the domain, checks local blacklists, resolves MX records via external DNS, and establishes a raw TCP socket connection to the target server's port 25.
4. **Data Persistence:** Uses SQLAlchemy ORM to communicate with SQLite, keeping data properly structured and preventing SQL injection.

### Data Flow Explanation
When a user submits an email for verification:
1. Client sends a `POST` request to `/api/verify` with the email.
2. The Request hits the **Rate Limiter**; if capacity is exceeded, an HTTP 429 is returned.
3. The **Middleware** verifies the user's token and deducts 1 credit from their account in the database.
4. The request is handed to the **Verification Engine**.
5. The Engine performs the 4-layer check (Syntax -> Disposable -> DNS -> SMTP).
6. The engine formulates a detailed JSON response (e.g., status, score, reasons) and sends it back to the client.

---

## 6. DATABASE DESIGN

*(Database relational model par base karti hai. Humne tables ko is tarah link kiya hai ke data duplication na ho aur referential integrity barqarar rahe. Yeh 4 main tables design kiye gaye hain.)*

### 1. `users` Table
Stores primary user accounts, their credentials, and global balances.

| Column Name | Data Type | Constraints | Description |
|-------------|-----------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Unique ID for the user |
| email | VARCHAR | UNIQUE, NOT NULL | User's login email address |
| password_hash| VARCHAR | NOT NULL | Encrypted Bcrypt hash |
| role | VARCHAR | DEFAULT 'user'| Distinguishes 'user' from 'admin'|
| credits | INTEGER | DEFAULT 100 | Remaining email verifications |
| created_at | DATETIME | DEFAULT NOW() | Account creation timestamp |

### 2. `subscriptions` Table
Tracks the billing and plan histories for users.

| Column Name | Data Type | Constraints | Description |
|-------------|-----------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Unique subscription ID |
| user_id | INTEGER | FOREIGN KEY | Links to `users.id` |
| plan_name | VARCHAR | NOT NULL | Name (e.g., 'FREE', 'PRO') |
| start_date | DATETIME | NOT NULL | When the plan started |
| end_date | DATETIME | NULL | When the plan expires |
| is_active | BOOLEAN | DEFAULT TRUE | Is plan currently active? |

### 3. `api_keys` Table
Users can generate multiple API keys for different apps/environments.

| Column Name | Data Type | Constraints | Description |
|-------------|-----------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Unique Key ID |
| user_id | INTEGER | FOREIGN KEY | Links to `users.id` |
| api_key | VARCHAR | UNIQUE, NOT NULL | The actual Bearer Key string |
| label | VARCHAR | NULL | User-defined name (e.g., "Prod")|
| created_at | DATETIME | DEFAULT NOW() | Key generation date |

### 4. `user_files` Table
Records the metadata for CSV/TXT files uploaded by users for bulk checking.

| Column Name | Data Type | Constraints | Description |
|-------------|-----------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Unique File ID |
| user_id | INTEGER | FOREIGN KEY | Links to `users.id` |
| filename | VARCHAR | NOT NULL | Original uploaded file name |
| file_size | INTEGER | NOT NULL | Size in bytes |
| status | VARCHAR | DEFAULT 'pending'| 'pending', 'processing', 'done'|
| created_at | DATETIME | DEFAULT NOW() | Time of upload |

### 5. `email_results` Table
Stores line-by-line verification results corresponding to uploaded files.

| Column Name | Data Type | Constraints | Description |
|-------------|-----------|-------------|-------------|
| id | INTEGER | PRIMARY KEY | Unique Result ID |
| file_id | INTEGER | FOREIGN KEY | Links to `user_files.id` |
| email | VARCHAR | NOT NULL | The target email address |
| status | VARCHAR | NOT NULL | ACCEPTED, REJECTED, etc. |
| score | INTEGER | NOT NULL | Deliverability Score (0-100)|

### Table Relations & ERD Diagram

```text
[Users] 1 ──────< N [Subscriptions]
(PK: users.id) ──> (FK: subscriptions.user_id)
Explanation: One user can have a history of multiple subscriptions over time.

[Users] 1 ──────< N [ApiKeys]
(PK: users.id) ──> (FK: api_keys.user_id)
Explanation: One user can generate multiple API keys for their various apps.

[Users] 1 ──────< N [UserFiles]
(PK: users.id) ──> (FK: user_files.user_id)
Explanation: One user can upload multiple bulk CSV files to clean.

[UserFiles] 1 ──< N [EmailResults]
(PK: user_files.id) ──> (FK: email_results.file_id)
Explanation: A single uploaded CSV file contains many individual email verification results.
```

*(Upar diye gaye diagram mein Relationship lines batati hain ke kis tarah Parent table apni primary key ke zariye Child table ki foreign key se juda hua hai. Yeh database ki consistency ke liye intehai ahem hai.)*

---

## 7. API DOCUMENTATION

This API adheres to RESTful standards, utilizing standard HTTP verbs and JSON for structured payloads. 

### 7.1. Authentication Endpoints

#### User Registration
- **Method:** `POST`
- **URL Path:** `/api/register`
- **Auth Required:** No
- **Request Body:**
  ```json
  {
    "email": "user@example.com",
    "password": "SecurePassword123"
  }
  ```
- **Response Body:**
  ```json
  {
    "message": "User created successfully",
    "user_id": 1
  }
  ```
- **Status Codes:** `201 Created`, `400 Bad Request` (Email already exists).

#### User Login
- **Method:** `POST`
- **URL Path:** `/api/login`
- **Auth Required:** No
- **Request Body:**
  ```json
  {
    "email": "user@example.com",
    "password": "SecurePassword123"
  }
  ```
- **Response Body:**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1Ni... (JWT Token)",
    "token_type": "bearer"
  }
  ```
- **Status Codes:** `200 OK`, `401 Unauthorized` (Wrong credentials).

### 7.2. Verification Endpoints

#### Verify Single Email
- **Method:** `POST`
- **URL Path:** `/api/verify`
- **Auth Required:** Yes (JWT Bearer Token OR `X-API-Key` Header)
- **Request Body:**
  ```json
  {
    "email": "contact@targetdomain.com"
  }
  ```
- **Response Body:**
  ```json
  {
    "email": "contact@targetdomain.com",
    "status": "ACCEPTED",
    "score": 98,
    "details": {
      "syntax_valid": true,
      "is_disposable": false,
      "mx_found": true,
      "smtp_connected": true
    }
  }
  ```
- **Status Codes:** `200 OK`, `402 Payment Required` (Out of credits), `429 Too Many Requests`.

#### Bulk Verify (Batch)
- **Method:** `POST`
- **URL Path:** `/api/verify-batch`
- **Auth Required:** Yes
- **Request Body:**
  ```json
  {
    "emails": [
      "test1@gmail.com",
      "test2@yahoo.com",
      "fake@bad-domain.xyz"
    ]
  }
  ```
- **Response Body:** Array of JSON response objects mapping to each email.
- **Status Codes:** `200 OK`, `400 Bad Request` (Array exceeds limit).

### 7.3. Admin Endpoints

#### Get All Users
- **Method:** `GET`
- **URL Path:** `/admin/users`
- **Auth Required:** Yes (Admin JWT Token)
- **Response Body:**
  ```json
  [
    {
      "id": 1,
      "email": "customer@business.com",
      "credits": 450,
      "plan": "PRO"
    }
  ]
  ```

#### Upgrade User Plan
- **Method:** `POST`
- **URL Path:** `/admin/upgrade-plan`
- **Auth Required:** Yes (Admin JWT)
- **Request Body:**
  ```json
  {
    "user_id": 1,
    "new_plan": "ENTERPRISE",
    "add_credits": 500000
  }
  ```

---

## 8. CORE MODULES EXPLANATION

### `verifier.py` - The 4-Layer Verification Engine

*(Yeh module hamare system ka dimagh (Brain) hai. Ismein email validation ke 4 aham steps hote hain jo neechay detail mein bataye gaye hain.)*

1. **Layer 1: Syntax Validation:** 
   Uses strict Regular Expressions (Regex) to ensure the email adheres to RFC 5322 standards. Missing "@" symbols or invalid characters are instantly rejected here, saving computational resources.
   
2. **Layer 2: Domain & Disposable Check:**
   The domain part (after the `@`) is extracted and checked against a hardcoded/cached database of 3000+ known disposable, temporary, or burner email providers (like Mailinator, 10minutemail). If found, it gets marked `DISPOSABLE`.

3. **Layer 3: DNS MX Records Lookup:**
   The `get_mx_records()` async function uses `aiodns` to query external nameservers (Google 8.8.8.8, Cloudflare 1.1.1.1). It asks, "Does this domain have an active Mail Exchange (MX) server to receive emails?" If no MX records exist, it returns `MX ERROR` or `REJECTED`.

4. **Layer 4: Deep SMTP Handshake (Target Server Interaction):**
   The `smtp_verify_async()` function attempts to open a TCP socket connection directly to the MX server identified in Layer 3 (usually on port 25).
   - It sends `HELO`/`EHLO`.
   - It sends `MAIL FROM:<scanner@ourdomain.com>`.
   - It sends `RCPT TO:<target@their-domain.com>`.
   - If the server responds with HTTP Code `250 OK`, the mailbox exists (`ACCEPTED`).
   - If the server responds with a `550` code, the user does not exist (`REJECTED`).
   - If the server accepts EVERYTHING (even random strings), it is marked as `CATCH-ALL`.
   - The connection is cleanly terminated with `QUIT` without ever sending an email payload.

### `middleware/auth.py`
This module acts as the security checkpoint. Before a user accesses `/api/verify` or `/admin/*`, this file executes. 
It supports two methods:
1. It looks for the `Authorization: Bearer <token>` header, decodes the JWT using the secret key, and matches it with the database to verify identity.
2. For backend automations, it accepts an `X-API-Key` header and validates it against the `api_keys` table.

### Batch Processing Logic
When large files are uploaded, verifying them sequentially would take hours. The batch engine logically splits an array of 10,000 emails into groups (chunks) of 5 to 10. `asyncio.gather()` is used to process each group fully concurrently, maximizing server I/O bandwidth and speeding up processing by up to 1000%.

---

## 9. FRONTEND DOCUMENTATION

The frontend is intentionally kept lightweight (Vanilla HTML/JS) to ensure rapid loading without heavy Node.js or React overheads. 

*(Frontend ko bilkul simple aur fast rakha gaya hai taake bina kisi delay ke load ho. Koi heavy framework (jaise React ya Vue) use nahi kiya gaya taake loading time minimize ho sake.)*

### Pages / Screens
- **`index.html`:** The landing page and main user dashboard combined. Shows remaining credits, API key blocks, and features the UI for bulk pasting/uploading emails.
- **`admin.html`:** A secure, visually distinct page solely for server administrators to view global statistics and modify user credits.

### User Journey (Step-by-Step)
1. **Onboarding:** User arrives at the homepage and registers an account.
2. **Dashboard Viewing:** Upon successful login, the UI swaps out the login screen for the dashboard view. The JS fetches `/api/me` and displays the user's credits.
3. **Action:** User pastes 50 emails into the text area and clicks 'Verify'.
4. **Processing State:** The UI shows a loading spinner. The `app.js` script splits the text by line breaks, sanitizes it, and sends batches of 5 to `/api/verify-batch`.
5. **Results Rendering:** As JSON responses return, rows are dynamically injected into the HTML results table. Colors represent statuses (Green=Accepted, Red=Rejected).
6. **Exporting:** A 'Download CSV' button becomes active, allowing the client to download their newly filtered list off the DOM.

---

## 10. SECURITY DOCUMENTATION

*(Security is platform ki bunyad hai. Humne mukhtalif layers par security checks lagaye hain taake data mehfooz rahe aur hackers system ka misuse na kar sakein.)*

### JWT Implementation (JSON Web Tokens)
Instead of relying on server-side sessions, the app uses JWTs. When a user logs in, a token containing their `user_id`, `role`, and expiration timestamp is signed cryptographically by the server using an `HS256` secret hash. Altering the token slightly renders it invalid instantly.

### API Key System
For integrations and server-to-server calls, users generate static API keys. When an API key is used, it directly queries the `api_keys` table. API keys contain more entropy (randomness) than passwords to prevent brute-forcing.

### Password Hashing (Bcrypt)
Plain text passwords are **never** stored. When registering, passwords undergo Bcrypt hashing with random salt generation. Even if the database is compromised, passwords cannot be reverse-engineered or cracked quickly using rainbow tables.

### Rate Limiting (SlowAPI)
To combat DDOS attacks, script kiddies, and free-tier abuse, `SlowAPI` middleware wraps all endpoints.
- `/api/login`: 5 requests per minute.
- `/api/verify-free`: 3 requests per minute per IP.
If breached, the server responds with a 429 status code and drops connection early.

---

## 11. DEPLOYMENT GUIDE

Deploying this software requires administrative access to a Linux Virtual Private Server (VPS). Shared hosting will not work due to the required network architecture.

*(Deployment ke liye aapko VPS server required hoga kyonki humein port 25 open chahiye hota hai SMTP connection ke liye. Shared hosting (like cPanel) is kaam ke liye bilkul theek nahi hai.)*

### System Requirements
- OS: Ubuntu 22.04 LTS (Recommended)
- RAM: Minimum 2GB (4GB+ for high volume Celery workers)
- Network: Open port 25 outbound. No ISP blocks.

### Environment Variables List (`.env`)
You must configure the following in the `.env` root file:
```env
SECRET_KEY=yoursupersecurejwtkey
DATABASE_URL=sqlite:///./api_keys.db
ADMIN_USERNAME=boss
ADMIN_PASSWORD=adminportalpwd
ENVIRONMENT=production
```

### Docker Setup Steps
For isolated environments, utilize Docker Compose.
1. `git clone` the repository onto your server.
2. Ensure Docker and Docker-Compose are installed.
3. Edit your `.env` file credentials.
4. Run: `docker-compose up -d --build`
5. The App will bind to port 8000. Use a reverse proxy like Nginx to route traffic to port 80.

### Cloud Deployment & Nginx Steps
Without Docker, deploy natively:
1. `sudo apt install python3-pip nginx`
2. Configure `systemd` to keep the Python application running continuously (`/etc/systemd/system/verifier.service`).
3. Setup an Nginx block (`/etc/nginx/sites-available/verifier`) targeting your domain and `proxy_pass http://127.0.0.1:8000`.
4. Run `certbot` to secure the domain with Free Let's Encrypt SSL.

---

## 12. KNOWN ISSUES & LIMITATIONS

*(Development ke dauran humne kuch problems face ki hain jinki details aur workarounds (hal) niche mojood hain.)*

### ISP Port 25 Blocking
- **Issue:** Providers like AWS, Azure, and DigitalOcean block outbound Port 25 by default to prevent spam. Our SMTP engine cannot reach remote servers.
- **Workaround:** You must request them to unblock port 25 or move the VPS to specialized unmanaged hosting exactly like Contabo or Hetzner where port 25 is unrestricted.

### Catch-All Servers
- **Issue:** Large Enterprise servers (like Office 365 or Google Workspaces configured strictly) intentionally hide inbox status. They accept everything initially and silently discard it later.
- **Workaround:** The engine safely flags these as `CATCH-ALL`. We recommend clients do not send to them unless strictly necessary.

### SQLite Scaling Issue
- **Issue:** SQLite handles heavy read operations effectively, but concurrent write operations (especially during massive bulk updates) cause database locking overhead.
- **Workaround:** A migration is being drafted. Small batches of 5 updates at a time provide stable concurrency for now.

---

## 13. FUTURE ROADMAP

*(Aane waley waqt mein hum platform ko aur taqatwar banane ke liye kuch baray changes plan kar rahe hain. Yeh roadmap next 6 months ka hai.)*

### PostgreSQL Migration
The transition from SQLite to PostgreSQL is paramount. PostgreSQL handles thousands of concurrent WRITE operations seamlessly, resolving database lock issues.

### Redis / Celery Integration
Implementing a robust message broker like Redis combined with Celery workers. This will allow the API to accept a 1 million email CSV, generate a tracking ID, and process it entirely in the background, pinging the frontend via websockets upon completion.

### Proxy Network Architecture
Large mail servers will eventually rate-limit our VPS IP if we query too fast. Setting up a distributed network of proxy IPs (v4 and v6) managed by HAProxy to randomize the source IP on our outbound port 25 calls.

---

## 14. GLOSSARY

- **Bcrypt:** Ek password hashing algorithm jo secure tariqe se passwords ko encrypt karta hai.
- **Catch-All:** Ek aisi email domain policy jo kisi bhi galat prefix (abc@domain.com, xyz@domain.com) ko bhi qabool kar leti hai, jiski wajah se verification mushkil hoti hai.
- **DNS (Domain Name System):** Internet ki phonebook. Yeh batati hai ke kisi fitoor(domain) ko kis server ki taraf route karna hai.
- **MX Record (Mail Exchange):** DNS ki ek entry jo batati hai ke us domain ke emails kis server par land karenge.
- **JWT (JSON Web Token):** Ek secure digital passport. Jab aap login karte hain toh yeh token milta hai jo aapke sessions ko manage karta hai bina database calls ke.
- **SMTP (Simple Mail Transfer Protocol):** Email bhejney ka aur receive karne ka international standard protocol. Hamara engine isi se baat karta hai.
- **API (Application Programming Interface):** Do software systems ke darmiyan baat-cheet ka zariya. Hamare case mein clients apna backend hamare system se direct connect kar sakte hain.

---
**End of Document**
*Prepared by Antigravity AI | Certified Systems Architecture Documentation*
