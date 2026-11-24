# Billing & Inventory Management System — Backend

A Django REST Framework backend for the Billing & Inventory Management System V1.

## Stack

- **Python** 3.12+
- **Django** 4.2 LTS
- **Django REST Framework** 3.14+
- **PostgreSQL** 14+ (primary database)
- **drf-spectacular** (OpenAPI schema + Swagger UI)
- **django-cors-headers** (CORS for SPA frontend)
- **Pillow** (logo image validation)
- **openpyxl** (Excel exports)
- **WeasyPrint** (PDF generation — Phase 5B, 7)
- **gunicorn** (production WSGI server)
- **pytest-django + factory-boy** (testing)

## Prerequisites

- Python 3.12 or newer
- PostgreSQL 14 or newer
- A Python virtual environment tool (`venv` or `virtualenv`)

## Setup

### 1. Clone and create a virtual environment

```bash
cd backend
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and set:

| Variable | Description |
|---|---|
| `SECRET_KEY` | A long random string (use `python -c "import secrets; print(secrets.token_urlsafe(50))"`) |
| `DEBUG` | `True` for development, `False` for production |
| `DB_NAME` | PostgreSQL database name |
| `DB_USER` | PostgreSQL user |
| `DB_PASSWORD` | PostgreSQL password |
| `DB_HOST` | PostgreSQL host (default `localhost`) |
| `DB_PORT` | PostgreSQL port (default `5432`) |
| `CORS_ALLOWED_ORIGINS` | Comma-separated frontend origins, e.g. `http://localhost:3000` |
| `DJANGO_SETTINGS_MODULE` | `config.settings.development` or `config.settings.production` |

### 4. Create the PostgreSQL database

```sql
-- In psql:
CREATE DATABASE billing_inventory;
```

### 5. Run migrations

```bash
python manage.py migrate
```

### 6. Create the initial admin account

```bash
python manage.py create_initial_admin
```

This command reads credentials from environment variables `INITIAL_ADMIN_USERNAME` and
`INITIAL_ADMIN_PASSWORD`, or prompts interactively. It never uses a hard-coded password.

> **Note:** `create_initial_admin` is implemented in Phase 1.

### 7. Start the development server

```bash
python manage.py runserver
```

API is available at <http://localhost:8000/api/>.

## API Documentation

| URL | Description |
|---|---|
| `GET /api/health/` | Liveness + database check (public) |
| `GET /api/schema/` | Download OpenAPI schema |
| `GET /api/docs/` | Swagger UI (public in development) |

### Settings (Phase 2)

| Method | Path | Who | Purpose |
|---|---|---|---|
| `GET` | `/api/settings/company/` | Any signed-in user | Read the business details; `logo` is an absolute URL or `null` |
| `PATCH` | `/api/settings/company/` | Admin | Update details and optionally upload a logo (`multipart/form-data` or JSON) |

The settings record exists exactly once. Logo uploads must be PNG or JPG, at most 2 MB,
and are verified with Pillow. Each upload is stored under a unique file name; replacing a
logo never deletes or overwrites the previous file. In development, uploaded media is
served from `/media/` when `DEBUG=True`; production media storage is decision D17.

### Products and inventory (Phase 4)

| Method | Path | Who | Purpose |
|---|---|---|---|
| `GET` | `/api/units/` | Any signed-in user | Paginated unit list (seeded units) |
| `GET` | `/api/products/` | Any signed-in user | Paginated list; `?search=` (name, code), `?item_type=`, `?is_active=`, `?low_stock=true` |
| `POST` | `/api/products/` | Any signed-in user | Create; optional write-only `opening_stock` for goods |
| `GET` | `/api/products/{id}/` | Any signed-in user | Detail |
| `PATCH` | `/api/products/{id}/` | Any signed-in user | Update details (stock is read-only) |
| `POST` | `/api/products/{id}/stock-in/` | Any signed-in user | `{quantity, reason?}` — quantity must be greater than zero |
| `POST` | `/api/products/{id}/adjust/` | Any signed-in user | `{quantity_change, reason}` — signed and non-zero |
| `GET` | `/api/stock-movements/` | Any signed-in user | Paginated ledger; `?product=`, `?item_type=`, `?movement_type=`, `?from=`, `?to=` |

Phase 4 rules:

- Item types are `GOODS`, `GOODS_HARDWARE` (Goods (Hardware)) and `SERVICE`.
  Goods and Goods (Hardware) track stock; Service never has stock or movements.
- `tracks_stock` and `is_low_stock` are computed in the API. A product is low
  stock when it tracks stock, has a reorder level, and `current_stock <= reorder_level`.
- Product codes are unique and auto-generated as `P0001`, `P0002`, … when the
  supplied code is blank. A custom code may be supplied.
- Creating a goods product with `opening_stock > 0` records one `OPENING`
  movement in the same transaction. `OPENING` is never created later.
- Stock changes only through the inventory stock service, which locks the
  product row, rejects Service products, and rejects a below-zero result with
  `INSUFFICIENT_STOCK` (HTTP 409).
- `stock-in` adds stock (`STOCK_IN`); `adjust` records a signed `ADJUSTMENT`
  and requires a reason. An item type cannot change to or from `SERVICE` once
  the product has any movement; changing between the two goods types is allowed.
- The stock movement list uses inclusive `from`/`to` dates and requires both
  when either is supplied.
- `python manage.py check_stock_consistency` compares every tracked product's
  stored stock with the sum of its movements and exits non-zero on a mismatch.

### Payments and outstanding balances (Phase 6)

| Method | Path | Who | Purpose |
|---|---|---|---|
| `GET` | `/api/payments/` | Any signed-in user | Paginated list; `?customer=`, `?method=`, `?from=`, `?to=`, `?search=` (reference, customer name) |
| `POST` | `/api/payments/` | Any signed-in user | Record a payment with allocations |
| `GET` | `/api/payments/{id}/` | Any signed-in user | Detail with allocations |
| `GET` | `/api/customers/{id}/open-invoices/` | Any signed-in user | Issued invoices with a balance, oldest first |
| `GET` | `/api/customers/{id}/payments/` | Any signed-in user | The customer's payments |
| `GET` | `/api/customers/{id}/statement/` | Any signed-in user | Debits, credits and a running balance |
| `GET` | `/api/invoices/{id}/payments/` | Any signed-in user | Payments allocated to the invoice |

Phase 6 rules:

- Payments are immutable in V1: there is no edit, delete, void, refund or
  receipt endpoint (D12).
- D11 Path A is in force. Every payment must be fully allocated, so the
  allocation amounts add up exactly to the payment amount. Advances and
  customer credit are not built.
- Every allocation targets an `ISSUED` invoice of the same customer, appears
  once per payment, is greater than zero, and cannot exceed the invoice's
  remaining balance. Over-allocation returns `OVER_ALLOCATION` (HTTP 409).
- Target invoices are locked in id order while the payment is recorded, so
  concurrent payments cannot over-allocate the same invoice.
- A retry carrying the same `client_token` returns the existing payment with
  HTTP 200 and creates nothing new.
- Derived values are calculated from allocations and never stored as editable
  fields: invoice `paid_amount`, `balance_due` and `payment_status`
  (`UNPAID`, `PARTIALLY_PAID`, `PAID`; a zero-total invoice is `PAID`), and
  customer `outstanding_amount` (issued invoices only).
- The statement treats each issued invoice as a debit on its invoice date and
  each payment as a credit on its payment date, ordered by date then creation
  order. Its final running balance equals the customer's outstanding amount.

### Delivery Challans (Phase 7)

| Method | Path | Who | Purpose |
|---|---|---|---|
| `GET` | `/api/challans/` | Any signed-in user | Paginated list; `?invoice=`, `?customer=`, `?from=`, `?to=` |
| `POST` | `/api/challans/` | Any signed-in user | Record a dispatch against an issued invoice |
| `GET` | `/api/challans/{id}/` | Any signed-in user | Detail with dispatched lines |
| `GET` | `/api/challans/{id}/document/` | Any signed-in user | Printable PDF |
| `GET` | `/api/invoices/{id}/dispatch-summary/` | Any signed-in user | Invoiced, dispatched and remaining quantity per line |
| `GET` | `/api/invoices/awaiting-dispatch/` | Any signed-in user | Issued invoices with goods still remaining |

Phase 7 rules:

- A challan can only be created for an `ISSUED` invoice. Draft invoices are
  rejected with `INVALID_STATE` (HTTP 409).
- Only `GOODS` and `GOODS_HARDWARE` lines can be dispatched. Service lines
  are rejected with `VALIDATION_ERROR` (HTTP 400); they can never receive a
  challan, and a service-only invoice has a `null` delivery status.
- At least one line is required, each invoice line appears once per challan,
  and every quantity must be greater than zero and no more than the line's
  remaining quantity. Over-dispatch returns `OVER_DISPATCH` (HTTP 409) with
  the remaining quantity in `details`.
- The invoice row and its lines are locked in id order while the challan is
  created, so concurrent challans cannot jointly over-dispatch one line.
- Challans never change stock or create stock movements. Issuing the invoice
  already made the `SALE` movement.
- Several challans per invoice are allowed, which supports partial delivery.
- Delivery status is derived, never stored: `PENDING`,
  `PARTIALLY_DELIVERED`, `DELIVERED`, or `null` when the invoice has no
  stock-tracked lines. It is returned on invoice list/detail rows and can be
  filtered with `?delivery_status=`.
- Challans are immutable in V1 (D14): there is no edit, delete or cancel
  endpoint. The challan number is the internal id until D13 is answered.
- The PDF is a plain placeholder until the client supplies the approved
  challan format (D13). It renders from the invoice item and saved business
  snapshots.

## Running Tests

Tests run against **PostgreSQL** (not SQLite). Make sure the database in `.env` is accessible.

```bash
pytest
```

Run a specific test file:

```bash
pytest tests/test_phase0.py -v
```

Run with coverage:

```bash
pip install pytest-cov
pytest --cov=apps --cov-report=term-missing
```

## Project Structure

```text
backend/
├── manage.py
├── requirements.txt
├── pytest.ini
├── .env.example
├── README.md
├── config/
│   ├── settings/
│   │   ├── base.py          — shared settings
│   │   ├── development.py   — dev overrides
│   │   └── production.py    — prod overrides
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── common/              — shared utilities (pagination, errors, permissions, helpers)
│   ├── accounts/            — custom User model, authentication, staff (Phase 1)
│   ├── company/             — business details and logo (Phase 2)
│   ├── customers/           — customers (Phase 3)
│   ├── products/            — product catalogue and item types (Phase 4)
│   ├── inventory/           — stock movements and stock service (Phase 4)
│   ├── invoices/            — invoices, issue workflow, document output (Phase 5)
│   ├── payments/            — payments, allocations, balances (Phase 6)
│   ├── delivery/            — delivery challans (Phase 7)
│   ├── expenses/            — expenses and Excel export (Phase 8)
│   ├── other_income/        — other income and Excel export (Phase 9)
│   └── dashboard/           — dashboard summary endpoint (Phase 10)
└── tests/
    ├── conftest.py          — shared fixtures
    ├── test_phase0.py       — Phase 0 tests
    ├── test_phase1.py       — Phase 1 tests
    ├── test_phase2.py       — Phase 2 tests
    ├── test_phase3.py       — Phase 3 tests
    ├── test_phase4.py       — Phase 4 tests
    ├── test_phase5.py       — Phase 5 tests
    ├── test_phase6.py       — Phase 6 tests
    └── test_phase7.py       — Phase 7 tests
```

## Environment Variables Reference

See `.env.example` for the full list with descriptions.

## Deployment Notes

- Set `DJANGO_SETTINGS_MODULE=config.settings.production`.
- Set `DEBUG=False` and configure `ALLOWED_HOSTS`.
- Run `python manage.py collectstatic` to gather static files.
- Use `gunicorn config.wsgi:application` as the WSGI server.
- Persistent media storage for logos must be configured (Decision D17).
- Never commit `.env` to version control.

## Build Phases

| Phase | Module | Status |
|---|---|---|
| 0 | Project foundation | ✅ Complete |
| 1 | Authentication and Staff | ✅ Complete |
| 2 | Settings | ✅ Complete |
| 3 | Customers | ✅ Complete |
| 4 | Products and inventory | ✅ Complete |
| 5A | Invoice core | Pending |
| 5B | Invoice format, PDF | Waiting for client sample |
| 6 | Payments | ✅ Complete |
| 7 | Delivery Challan | Pending |
| 8 | Expenses and Excel export | Pending |
| 9 | Other Income and Excel export | Pending |
| 10 | Dashboard | Pending |
| 11 | Hardening, API contract, staging | Pending |
