# Event Booking / Ticketing API (Eventflow)

A backend API for creating events and booking tickets using
**JWT auth + RBAC, safe concurrency on limited
inventory, idempotency keys, Stripe test payments, premium tiers, and
analytics.**

Built with **FastAPI + SQLAlchemy 2.0 + PostgreSQL**.

---

## Table of contents

1. [What it does](#what-it-does)
2. [Key backend concepts demonstrated](#key-backend-concepts-demonstrated)
3. [Project structure](#project-structure)
4. [Setup & run](#setup--run)
5. [Roles (RBAC)](#roles-rbac)
6. [API endpoints](#api-endpoints)
7. [Testing with Postman](#testing-with-postman)
8. [How the hard parts work](#how-the-hard-parts-work)

---

## What it does

- **Organizers** create events (title, venue, capacity, ticket price).
- **Attendees** book tickets. Inventory is limited — the API guarantees you can
  never sell more tickets than the capacity, even under heavy concurrency.
- **Payments** go through Stripe (test mode), with a built-in fake processor so
  the project runs with zero setup.
- **Premium** organizers pay a fee to unlock a higher event limit and
  "featured" listings.
- **Analytics**: tickets sold over time and revenue per event; platform-wide
  totals for admins.

---

## Key backend concepts demonstrated

| Concept                         | Where                               | One-liner                                       |
| ------------------------------- | ----------------------------------- | ----------------------------------------------- |
| **JWT auth**                    | `app/core/security.py`, `app/auth/` | Stateless login tokens, signed + expiring       |
| **Password hashing**            | `app/core/security.py`              | bcrypt, never plain text                        |
| **RBAC**                        | `app/auth/dependencies.py`          | `require_role(...)` dependency gates each route |
| **Concurrency / no oversell**   | `app/routers/bookings.py`           | `SELECT ... FOR UPDATE` row lock                |
| **Idempotency keys**            | `app/routers/bookings.py`           | Retries never double-book                       |
| **Stripe payments**             | `app/core/payments.py`              | PaymentIntents in test mode (or faked)          |
| **Premium tier / billing**      | `app/routers/premium.py`            | Paid upgrade unlocks limits/features            |
| **Analytics (SQL aggregation)** | `app/routers/analytics.py`          | `SUM` / `GROUP BY` over paid bookings           |
| **Config management**           | `app/core/config.py`, `.env`        | Secrets isolated, typed, validated              |

---

## Project structure

```
project/
├── app/
│   ├── main.py              # FastAPI app, wires routers, creates tables on startup
│   ├── models.py            # ORM tables: User, Event, Booking
│   ├── schemas.py           # Pydantic request/response shapes + validation
│   ├── core/
│   │   ├── config.py        # Settings loaded from .env (pydantic-settings)
│   │   ├── database.py      # Engine, session, get_db dependency
│   │   ├── security.py      # Password hashing + JWT create/decode
│   │   └── payments.py      # Stripe wrapper (+ fake provider)
│   ├── auth/
│   │   ├── router.py        # /auth/register, /auth/login, /auth/me
│   │   └── dependencies.py  # get_current_user, require_role (RBAC)
│   └── routers/
│       ├── events.py        # event CRUD + featuring + limits
│       ├── bookings.py      # booking (concurrency + idempotency), pay, cancel
│       ├── premium.py       # organizer premium upgrade
│       └── analytics.py     # per-event + platform analytics
├── seed.py                  # creates tables + an admin user
├── requirements.txt
├── .env                     # <-- EDIT THIS for credentials (gitignored)
└── .env.example
```

---

## Setup & run

### 1. Prerequisites

- Python 3.11+
- PostgreSQL running locally (this project assumes user `postgres` / password `1234`)

### 2. Configure

Credentials live in **`.env`** (already filled with your Postgres user/password).
Edit it any time. To use real Stripe test payments, set `STRIPE_ENABLED=true`
and paste your `sk_test_...` key — otherwise the app uses a built-in fake
payment processor and runs out of the box.

> Tip: generate a real JWT secret:
> `python -c "import secrets; print(secrets.token_hex(32))"` and paste it as `JWT_SECRET`.

### 3. Create the database (one time)

```bash
PGPASSWORD=1234 psql -U postgres -h localhost -c "CREATE DATABASE event_booking"
```

### 4. Install dependencies

A virtualenv already exists in `venv/`. If you need to recreate it:

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

### 5. Seed an admin + create tables

```bash
./venv/bin/python seed.py
# -> creates admin@example.com / admin1234
```

### 6. Run the server

```bash
./venv/bin/uvicorn app.main:app --reload
```

- Interactive API docs (Swagger UI): **http://localhost:8000/docs**
- These docs alone are enough to test everything (there's an "Authorize" button
  for your JWT). Postman instructions are below.

---

## Roles (RBAC)

| Role          | Can do                                                                                                                             |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **attendee**  | browse events, book/pay/cancel own tickets, view own bookings                                                                      |
| **organizer** | everything an attendee can + create/edit/cancel own events, feature events (premium), view own event analytics, upgrade to premium |
| **admin**     | everything, on any resource + platform-wide analytics                                                                              |

You pick `attendee` or `organizer` at registration. Admins are created only via
`seed.py` (you can't self-register as admin).

---

## API endpoints

| Method | Path                     | Role                 | Purpose                                      |
| ------ | ------------------------ | -------------------- | -------------------------------------------- |
| POST   | `/auth/register`         | public               | create attendee/organizer                    |
| POST   | `/auth/login`            | public               | get a JWT                                    |
| GET    | `/auth/me`               | any                  | current user info                            |
| POST   | `/events`                | organizer/admin      | create event (limit-checked)                 |
| GET    | `/events`                | any                  | list events (`?featured_only=true`)          |
| GET    | `/events/{id}`           | any                  | event detail                                 |
| PATCH  | `/events/{id}`           | owner/admin          | update event                                 |
| POST   | `/events/{id}/cancel`    | owner/admin          | cancel event                                 |
| POST   | `/events/{id}/feature`   | owner(premium)/admin | toggle featured                              |
| POST   | `/events/{id}/bookings`  | any                  | **book tickets** (concurrency + idempotency) |
| POST   | `/bookings/{id}/pay`     | owner/admin          | confirm payment                              |
| POST   | `/bookings/{id}/cancel`  | owner/admin          | cancel + release seats                       |
| GET    | `/bookings/me`           | any                  | my bookings                                  |
| GET    | `/bookings/{id}`         | owner/admin          | booking detail                               |
| POST   | `/premium/upgrade`       | organizer            | pay to go premium                            |
| GET    | `/events/{id}/analytics` | owner/admin          | per-event analytics                          |
| GET    | `/analytics/platform`    | admin                | platform analytics                           |

---

## Testing with Postman

> You can also just use **http://localhost:8000/docs** — but here's the full
> Postman flow.

### One-time Postman setup

1. Create a new **Collection** named `Event Booking API`.
2. Open the collection → **Variables** tab and add:
   - `base_url` = `http://localhost:8000`
   - `org_token` = _(leave blank — we'll fill it)_
   - `att_token` = _(leave blank)_
   - `admin_token` = _(leave blank)_
3. In every request below, use `{{base_url}}` in the URL.
4. For authenticated requests, go to the request's **Authorization** tab →
   Type = **Bearer Token** → Token = `{{org_token}}` (or `{{att_token}}` /
   `{{admin_token}}` depending on who should call it).

### Flow A — Auth

**1. Register an organizer**

- `POST {{base_url}}/auth/register`
- Body → raw → JSON:

```json
{
  "email": "org@example.com",
  "password": "pass123",
  "full_name": "Olivia Organizer",
  "role": "organizer"
}
```

**2. Register an attendee** — same, with `"email": "att@example.com"` and `"role": "attendee"`.

**3. Login (organizer)**

- `POST {{base_url}}/auth/login`
- Body:

```json
{ "email": "org@example.com", "password": "pass123" }
```

- Copy `access_token` from the response into the `org_token` collection variable.
  _(Optional: paste this into the request's **Tests** tab to auto-save it:)_

```javascript
pm.collectionVariables.set("org_token", pm.response.json().access_token);
```

**4. Login (attendee)** → save to `att_token`.
**5. Login (admin)** with `admin@example.com` / `admin1234` → save to `admin_token`.

### Flow B — Events (as organizer)

**6. Create an event** — Auth: `{{org_token}}`

- `POST {{base_url}}/events`

```json
{
  "title": "Jazz Night",
  "description": "Live jazz",
  "venue": "Blue Room",
  "starts_at": "2026-09-01T18:00:00Z",
  "capacity": 2,
  "price_cents": 1000
}
```

> Note the small `capacity: 2` — we'll use it to test overselling.
> Note the response `id` (say `1`).

**7. RBAC check** — try the same `POST /events` with Auth `{{att_token}}`.
Expect **403 Forbidden** (attendees can't create events).

**8. List events** — `GET {{base_url}}/events` (any token).

### Flow C — Booking, concurrency & idempotency (as attendee)

**9. Book a ticket** — Auth: `{{att_token}}`

- `POST {{base_url}}/events/1/bookings`
- Body:

```json
{ "quantity": 1 }
```

- Response includes the booking (`status: pending`) and a `client_secret`.
  Note the booking `id`.

**10. Test idempotency**

- Add a **Header**: `Idempotency-Key: my-test-key-1`
- Send `POST /events/1/bookings` with `{ "quantity": 1 }` **twice**.
- Both responses return the **same booking id**; the 2nd says
  `"Replay of an existing booking (idempotent)."` — no double booking.

**11. Test overselling (the important one)**

- The event has capacity 2. Send booking requests until seats run out.
- Once `seats_booked == capacity`, further bookings return **409 Conflict**
  `"Not enough seats."`
- To simulate a real race, use Postman's **Runner**: select the booking request,
  set iterations to e.g. 5, run it. You'll see exactly 2 succeed (201) and the
  rest 409 — never an oversell. Confirm with `GET /events/1` that
  `seats_booked` never exceeds `capacity`.

**12. Pay for a booking** — Auth: `{{att_token}}`

- `POST {{base_url}}/bookings/{id}/pay`
- Status flips to `paid`. (With the fake processor it always succeeds; with real
  Stripe it confirms using the test card `pm_card_visa`.)

**13. My bookings** — `GET {{base_url}}/bookings/me`.

**14. Cancel a booking** — `POST {{base_url}}/bookings/{id}/cancel` → seats are
released back to the event.

### Flow D — Premium (as organizer)

**15. Upgrade to premium** — Auth: `{{org_token}}`

- `POST {{base_url}}/premium/upgrade` → `is_premium: true`.
- Now you can feature events and create up to 100 events instead of 3.

**16. Feature an event** — `POST {{base_url}}/events/1/feature?featured=true`
(works only because the organizer is now premium).

### Flow E — Analytics

**17. Per-event analytics** — Auth: `{{org_token}}`

- `GET {{base_url}}/events/1/analytics` → tickets sold, revenue, daily timeline.
- Try with `{{att_token}}` → **403** (not your event).

**18. Platform analytics** — Auth: `{{admin_token}}`

- `GET {{base_url}}/analytics/platform` → totals + top events. Non-admins get 403.

---

## How the hard parts work

### Concurrency — no overselling the last seat

The danger: two people book the last seat at the same time. Both read
"1 seat left", both pass the check, both book → oversold.

The fix (in `app/routers/bookings.py`): we lock the event row inside a DB
transaction before checking/updating seats:

```python
event = db.query(Event).filter(Event.id == event_id).with_for_update().one()
#                                                    ^^^^^^^^^^^^^^^^^ SELECT ... FOR UPDATE
if event.seats_available < qty:   # checked WHILE holding the lock
    raise 409
event.seats_booked += qty
db.commit()                       # releases the lock
```

`FOR UPDATE` makes the second transaction **wait** until the first commits, so
the capacity check and update happen one-at-a-time. Verified by the Postman
Runner test above (5 concurrent → exactly 2 succeed on a capacity-2 event).

### Idempotency — retries don't double-book

The client sends an `Idempotency-Key` header. We store it on the booking with a
**UNIQUE** constraint. On a replay we return the original booking instead of
creating a new one (and a DB-level unique check protects against a simultaneous
race). This is the same pattern Stripe itself uses.

### JWT auth + RBAC

`login` returns a signed JWT containing the user id + role. Every protected
request sends `Authorization: Bearer <token>`. `get_current_user` verifies the
signature/expiry and loads the user; `require_role(...)` rejects wrong roles
with 403.

### Payments

`app/core/payments.py` hides Stripe behind a small interface. With
`STRIPE_ENABLED=false` a fake provider returns realistic PaymentIntents so the
app runs without an account. Flip it to `true` + add your `sk_test_...` key to
use real Stripe test-mode calls — no code changes needed.

### Reservations on pending bookings

Seats are reserved the moment a (pending) booking is created and released if you
cancel or payment fails. A production system would also expire stale pending
reservations (e.g. a background job) and refund paid cancellations — noted as
the natural next step.

```

```
