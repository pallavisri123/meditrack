# MediTrack — Integrated Patient Care Management System (Patient Portal)

Patient-facing healthcare SaaS web app with full authentication, an analytics dashboard,
and the original patient-care workflow, all connected to one database.

Flow: **Sign Up → Log In → Dashboard (with live charts)** → Doctors → Doctor Availability →
Book Appointment → Confirmation → Consultation → Diagnosis → Treatment → Prescription →
Lab Tests → Medical History → Notifications. Emergency is independently reachable at any time.

## What's new in this upgrade
- **Authentication**: `signup.html`, `login.html`, `forgot-password.html`, `reset-password.html`,
  backed by JWT sessions (`backend/auth.py`), PBKDF2 password hashing, and secure single-use
  password-reset tokens with expiry.
- **Dashboard**: rebuilt with 6 real-data summary cards and 5 interactive Chart.js charts
  (appointment trend, appointment status, monthly activity, prescription overview, lab test
  status) — all fed by new `/api/dashboard/*` endpoints that read from the database, never
  hardcoded values. Includes loading skeletons, empty states, and error/retry states.
- **New modules**: Lab Tests (`lab-tests.html` + `lab_tests` table), a dedicated
  Notifications page, and a Settings page for changing your password.
- **Security**: protected API routes via a `get_current_user` / `require_own_patient`
  dependency, so a logged-in patient can only reach their own records.
- The original no-login **Patient Directory** (`index.html`, `patients.html`) is preserved
  for backward compatibility but is no longer the app's entry point.

## Password reset in this environment
No SMTP provider is wired up here, so `/api/auth/forgot-password` logs the reset link to
the server console and also returns it in the response as `dev_reset_link` for local testing.
Wire up a real provider (SendGrid, AWS SES, SMTP) in `backend/main.py` and drop
`dev_reset_link` from the response before going to production.

## Stack
- Frontend: HTML + CSS + vanilla JavaScript (`fetch()` to the API), theme blue/white/green, red only for emergency & blood.
- Backend: Python + FastAPI + SQLAlchemy
- Database: MySQL (auto-falls back to SQLite `meditrack.db` if MySQL is not running, so demos never break)

## Run
```bash
cd backend
python -m pip install -r requirements.txt

# MySQL (optional but recommended):
#   mysql -u root -p < schema.sql
#   set DATABASE_URL="mysql+pymysql://root:yourpass@localhost:3306/meditrack"
export DATABASE_URL="mysql+pymysql://root:root@localhost:3306/meditrack"

# Recommended: set a real JWT secret (falls back to a random one otherwise,
# which invalidates sessions on every restart)
export JWT_SECRET_KEY="change-me-to-a-long-random-string"

uvicorn main:app --reload
```
Open http://127.0.0.1:8000/ — redirects to the login page (frontend is served by FastAPI).
API docs: http://127.0.0.1:8000/docs

### Deploying for a live link
This app is a stateless FastAPI service + static frontend, so it deploys cleanly to any
Python host:
- **Render / Railway**: create a new Web Service from this repo, build command
  `pip install -r backend/requirements.txt`, start command
  `uvicorn main:app --host 0.0.0.0 --port $PORT --app-dir backend`. Add `DATABASE_URL`
  and `JWT_SECRET_KEY` as environment variables (a managed MySQL/Postgres add-on works,
  or leave `DATABASE_URL` unset to fall back to SQLite for a quick demo).
- **Fly.io / Docker**: wrap the same start command in a `Dockerfile` based on
  `python:3.12-slim`.
I can't provision or host a live server myself from here, so I've kept the app
one command away from a public URL on any of the above — you'll have a working
link within a few minutes of connecting a repo.

Departments, doctors, availability slots and blood stock are seeded automatically on startup.

## Tables
patients, doctors, departments, doctor_availability, appointments, consultations,
prescriptions, prescription_medicines, medical_history, notifications, emergency_contacts,
blood_stock, ambulance_requests — with primary keys, foreign keys and unique constraints
(`uq_doctor_slot`, `uq_appt_slot` prevent double booking).

## Features
CRUD + search everywhere (save/update/edit/delete/cancel/reset/view/back), form validation
(client + Pydantic server-side), auto Patient ID, auto age from DOB, profile photo, profile
completion %, dashboard statistics, notifications & reminders, smart patient summary,
health timeline, multi-medicine prescriptions with print/PDF, emergency health card,
blood availability and ambulance request.

## Round 2 additions
- **Billing & Payments**: `billing.html` + `Bill`/`BillItem`/`Payment` models. Generate invoices,
  view a printable invoice, pay against a balance (simulated backend-side verification —
  no raw card data is ever stored, only a transaction reference). Payment statuses: Paid,
  Pending, Partially Paid, Failed, Refunded.
- **Email/SMS architecture**: `backend/notification_service.py` — every notification is
  always saved in-app; email (SMTP) and SMS (generic HTTP gateway) only activate when their
  environment variables are set (`SMTP_HOST`/`SMTP_USER`/`SMTP_PASSWORD`/..., `SMS_GATEWAY_URL`/
  `SMS_API_KEY`/...). Nothing is hardcoded; the app runs fine with in-app-only notifications
  if those vars are absent.
- **Voice Assistant**: floating mic button on every authenticated page (`js/app.js`,
  `VoiceAssistant`), using the browser's native Web Speech API — no external key needed.
  Supports commands like "show appointments", "open billing", "show notifications", and
  "search patient <name>" (queries the real patient database), plus a typed-command fallback
  when the microphone isn't available.
- Confirmed: **no Reception/Receptionist module** exists anywhere in the app.

## Round 3: dashboard fix + real phone notifications
- **Bug fix**: dashboard charts weren't rendering because Chart.js was pinned to an
  exact CDN patch version that didn't resolve. Switched to jsDelivr with an automatic
  cdnjs fallback, plus a visible on-page error if the chart library still can't load.
- **New accounts start with zero data** by design (no fake/hardcoded chart values) — so a
  fresh signup's charts will show "no data yet" until real activity exists. Added a
  **"Load Sample Data"** button on the dashboard (only shown when you have zero
  appointments) that creates real appointment/consultation/prescription/lab-test/bill
  rows in the database so you can immediately see the charts populated.
- **Real phone notifications**: implemented Web Push (`backend/push_service.py`,
  `frontend/sw.js`, `PushNotifications` in `js/app.js`) — the standard, free,
  no-SMS-carrier-needed protocol that delivers notifications to a phone's browser/lock
  screen (Android Chrome, desktop browsers, iOS 16.4+ after "Add to Home Screen"), even
  when MediTrack isn't open. Turn it on from **Settings → Phone Notifications**.
  Requires a one-time `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_CLAIM_EMAIL`
  setup (see `push_service.py` docstring) — until those are set, this silently no-ops
  and the app still works fine with in-app notifications only.
- Note: the earlier SMS/Email channels (`notification_service.py`) are a *separate*,
  optional layer for actual text messages/emails via a carrier/SMTP provider — you can
  use either or both. Web Push is the free, no-signup-needed way to reach a phone;
  SMS needs a paid gateway account (Twilio/MSG91/etc).
