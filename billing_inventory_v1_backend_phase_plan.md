# Billing & Inventory Management System - V1 Backend Phase Plan

Purpose: a self-contained specification for building the complete V1 backend with an LLM coding assistant, one module (phase) at a time.
Scope: backend only (Django + Django REST Framework + PostgreSQL). The frontend is planned and built afterwards, from the API contract this backend produces (Phase 11).
Scope authority: the client-reviewed V1 plan, `billing_inventory_v1_backend_frontend_execution_plan.md` and `billing_inventory_v1_complete_workflows.md`. This file reorganizes them for backend work. It does not add scope.

---

## 0. How to use this file with an LLM

### 0.1 Rules for the coding assistant (apply to every phase)

1. Read Sections 0 to 6 and the current phase in full before changing code.
2. Work on one phase at a time. Do not start the next phase until the current phase's completion gate passes.
3. Follow the approved V1 scope exactly. Do not build anything in Section 1.3 (change requests) or Section 1.4 (out of scope).
4. Do not invent fields, tax rules, numbering rules, or document layouts. Items marked **PENDING DECISION** are not to be guessed. Build what the phase says can be built now, and use the stated default for the rest.
5. If something is unclear or conflicts with this file, stop and ask.
6. Keep business logic in service functions (`services.py`). Keep views and serializers thin.
7. Money is `Decimal`. Multi-record changes use transactions. Validate everything on the backend (Section 3).
8. Keep the existing structure and naming. No unrelated rewrites.
9. Commit migrations with the code. Never edit an applied migration; add a new one.
10. Write tests for every rule in the phase (Section 3.9). Tests run against PostgreSQL.
11. Verify each endpoint manually through the API docs page or `curl` and report what you checked.
12. When modifying existing code, return only the changed files, not the whole project.
13. End every phase with the handoff report in Section 0.3.

### 0.2 Prompt to paste for each phase

```text
You are building backend Phase <N> (<name>) of the Billing & Inventory V1 project.
Read Sections 0 to 6 and Phase <N> of the attached plan completely.
Implement only Phase <N>. Do not implement anything marked PENDING DECISION beyond its stated default,
and do not implement anything listed as a change request or out of scope.
If a requirement is unclear, stop and ask.
Return only the files you created or changed.
Finish with the handoff report from Section 0.3.
```

### 0.3 Phase handoff report (required at the end of each phase)

- What was implemented.
- Files and modules created or changed.
- Models and migrations added.
- Endpoints completed (method, path, permission).
- Tests added and their results.
- Manual verification performed.
- Known issues and client decisions still required.
- Confirmation that the phase completion gate passes.

---

## 1. Scope baseline

### 1.1 Approved modules (final navigation)

1. Dashboard
2. Customers
3. Products
4. Invoices
5. Payments
6. Delivery Challan
7. Expenses
8. Other Income
9. Settings
10. Staff

Plus authentication (login, logout, current user).

### 1.2 What the V1 backend does

- Authenticates users. Admin registers staff.
- Stores basic business details and a logo once, for use on documents.
- Maintains customers and products. Products have three item types: Goods, Goods (Hardware), Service. The first two track stock. Service does not.
- Creates draft invoices and issues them. Issuing deducts stock exactly once. Generates the invoice document in the exact format the client supplies.
- Records payments, allocates them to invoices, and derives invoice balances and customer outstanding.
- Records delivery challans against issued invoices (including partial dispatch) without deducting stock again, and derives delivery status.
- Records expenses and other income. Each exports to a real `.xlsx` file for a From Date and To Date range.
- Returns the summary figures for the reviewed dashboard.

### 1.3 Change requests: do NOT build unless the client approves in writing

- Invoice cancellation or reversal.
- GST document types and tax-splitting rules beyond what the client sample confirms.
- Gapless financial-year numbering and number-sequence tables.
- Payment void, refund and receipt workflows; an unallocated-credit model (see Phase 6).
- Challan cancellation.
- Audit log, CSV import, invoice-register export.
- A more detailed dashboard than the reviewed one.

### 1.4 Out of scope for V1

Quotations and estimates, sales returns and credit notes, suppliers and purchases, purchase orders, automatic stock-in from purchases, multiple warehouses, separate physical/reserved stock, barcode scanning, full accounting, bank reconciliation, payroll/attendance/HR, complex roles and permission matrices, WhatsApp/SMS/email automation, loyalty/CRM, advanced analytics, mobile apps, e-invoicing/IRN and e-way bills, multi-company, microservices.

---

## 2. Backend architecture

### 2.1 Stack

- Python 3.12 or newer, current Django LTS (check at project start), Django REST Framework, PostgreSQL.
- Suggested packages: `djangorestframework`, `drf-spectacular` (OpenAPI), `psycopg` (PostgreSQL driver), `django-environ` or `python-dotenv`, `django-cors-headers`, `Pillow` (logo validation), `openpyxl` (Excel), `WeasyPrint` (PDF, Phase 5B and 7), `pytest-django`, `factory-boy`, `gunicorn`.
- Modular monolith. One Django project. No microservices, Celery, Redis, or generic repository layers.

### 2.2 Project structure

```text
backend/
  config/                 settings (base, dev, prod), urls, wsgi/asgi
  apps/
    accounts/             user model, authentication, staff
    company/              business details and logo
    customers/            customers
    products/             products, item types, units
    inventory/            stock movements and the stock service
    invoices/             invoices, items, calculation, issue workflow, document output
    payments/             payments, allocations, balances
    delivery/             delivery challans, dispatch quantities
    expenses/             expenses and Excel export
    other_income/         other income and Excel export
    dashboard/            dashboard summary endpoint
  common/                 pagination, error handling, permissions, validators,
                          decimal helpers, date-range helper, export helper, constants
  manage.py
  requirements.txt
  .env.example
  README.md
```

Each app: `models.py`, `services.py` (business workflows), `serializers.py`, `views.py`, `urls.py`, `filters.py` (if needed), `tests/`.

---

## 3. Global backend rules (apply to every phase)

### 3.1 Backend owns correctness

The backend is the source of truth for authentication and access, validation, invoice calculations, stock, payment allocations and balances, delivery quantities and status, date filtering and Excel generation, dashboard values, and historical invoice details. It never trusts totals, balances, statuses or stock values sent by a client.

### 3.2 Data types and formats

- Primary keys: integer ids.
- Money: `DecimalField(max_digits=14, decimal_places=2)`. Never float.
- Quantities: `DecimalField(max_digits=12, decimal_places=3)` (fractional units possible).
- API output for money and quantities: strings (for example `"1250.00"`, `"10.500"`). API input accepts strings or numbers and converts to `Decimal` without passing through float.
- Dates: `YYYY-MM-DD`. Timestamps: ISO 8601 with offset.
- Business timezone: `TIME_ZONE = "Asia/Kolkata"`, `USE_TZ = True`. "Today" and "this month" mean Asia/Kolkata.
- Enum values are upper-case snake case strings (listed per phase).

### 3.3 Transactions and locking

- Wrap every multi-record operation in `transaction.atomic()`.
- Use `select_for_update()` where concurrent requests could oversell stock, over-allocate money, over-dispatch goods, or double-issue an invoice. Lock rows in a fixed order (by id) to avoid deadlocks.
- Retried requests must not create duplicate side effects (the mechanism is stated in each phase).
- Never hard-delete issued invoices, payments, challans or stock movements. Use `on_delete=PROTECT` for references to them.

### 3.4 Stock rules (used by Phases 4, 5, 7)

- Goods and Goods (Hardware) are stock-tracked. Service is never stock-tracked and never creates stock movements.
- Drafts never change stock. Issuing an invoice deducts stock once. Delivery challans never change stock.
- Negative stock is rejected.
- All stock changes go through one function, `inventory.services.apply_stock_movement(...)` (Phase 4). No other code updates `current_stock`.

### 3.5 Historical records

When an invoice is issued, save the business details, customer details and each line's product details used at that moment. Old invoices and their documents are always rendered from these snapshots, never from current customer, product or business records.

### 3.6 Error format and status codes

Every error response has this shape:

```json
{ "code": "VALIDATION_ERROR", "message": "Human readable summary", "fields": { "field_name": ["message"] }, "details": [] }
```

| HTTP | code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Invalid input; `fields` holds per-field messages |
| 400 | `INVALID_DATE_RANGE` | From date after To date, or a date missing where required |
| 401 | `NOT_AUTHENTICATED` | Not signed in |
| 403 | `PERMISSION_DENIED` | Signed in but not allowed |
| 404 | `NOT_FOUND` | Object does not exist |
| 409 | `INVALID_STATE` | Action not allowed in the current state (for example editing an issued invoice) |
| 409 | `INSUFFICIENT_STOCK` | Stock too low; `details` lists each product with `product`, `name`, `available`, `required` |
| 409 | `OVER_ALLOCATION` | Payment or invoice over-allocated |
| 409 | `OVER_DISPATCH` | Dispatch quantity above remaining |
| 429 | `THROTTLED` | Rate limit reached |
| 500 | `SERVER_ERROR` | Unexpected error (no internal details in the message) |

Implement one DRF exception handler in `common` that produces this shape for all errors, including DRF's own.

### 3.7 Pagination, search and filtering

- List endpoints use page-number pagination, default 20, `?page=` and `?page_size=` (maximum 100).
- Response shape: `{ "count": n, "next": url|null, "previous": url|null, "results": [...] }`.
- Search, filters and ordering are applied on the server. Lists must avoid N+1 queries (use `select_related`, `prefetch_related`, annotations).

### 3.8 Security

- Every endpoint requires authentication except login (and the CSRF token endpoint if used). Permissions are enforced on the backend.
- Passwords hashed by Django, password validators on, login rate-limited.
- Secrets come from environment variables. Nothing secret in Git.
- Uploaded files are validated (type, size). Production file storage is persistent (D17).
- No tokens in `localStorage` (frontend rule recorded here for the contract): authentication uses an httpOnly cookie.

### 3.9 Testing standard

- `pytest-django` against PostgreSQL (not SQLite). `factory-boy` factories for every model.
- Rules involving concurrency use real transactions (`TransactionTestCase` or `pytest.mark.django_db(transaction=True)`) and threads.
- Each phase's test list is mandatory. A phase is not complete with failing or missing tests.
- Money and stock tests assert exact `Decimal` values.

---

## 4. Access model (default, simple)

Two roles: `ADMIN` (owner) and `STAFF`. No permission matrix.

- ADMIN: everything, including Settings and Staff.
- STAFF: can sign in and use every module except Settings (update) and Staff.
- The company settings can be read by any signed-in user (documents need them). Updating settings and all staff endpoints are ADMIN only.
- In the endpoint tables, "Any" means any signed-in, active user, and "Admin" means ADMIN only.

PENDING DECISION D3: the client may want finer limits (for example Staff cannot adjust stock). Ask before adding any.

---

## 5. Phase map

| Phase | Module | Depends on | Blocked by client input? |
|---|---|---|---|
| 0 | Project foundation | none | Auth approach (default available) |
| 1 | Authentication and Staff | 0 | Staff detail fields (default available) |
| 2 | Settings (business details) | 1 | Final field list (default available) |
| 3 | Customers | 1 | No |
| 4 | Products and inventory | 1 | Unit list (default available) |
| 5 | Invoices | 2, 3, 4 | 5A no. 5B needs invoice sample, numbering, tax, discount, rounding |
| 6 | Payments and outstanding | 3, 5 | Advance payment confirmation |
| 7 | Delivery Challan | 5 | Challan sample (layout only) |
| 8 | Expenses and Excel export | 1 | Export columns (default available) |
| 9 | Other Income and Excel export | 1, 8 | Export columns (default available) |
| 10 | Dashboard | 4, 5, 6, 7, 8, 9 | No |
| 11 | Hardening, API contract freeze, staging | all | Hosting choices |

Phases 3, 4, 8 and 9 do not depend on each other and may be built in parallel. Do not delay Phases 0 to 4 while waiting for the invoice sample. Pause only Phase 5B.

---

## 6. Decision register

Until a decision is answered, build exactly what the "Until answered" column says.

| ID | Decision | Needed by | Until answered |
|---|---|---|---|
| D1 | Auth approach: session cookie + CSRF, or JWT in httpOnly cookies | Phase 0 | Session cookie + CSRF (with a CSRF token endpoint) |
| D2 | Required staff details | Phase 1 | Full name, username, phone, email (optional), role, active, password |
| D3 | Finer staff access limits | Phase 1 | Section 4 default |
| D4 | Business details fields (and signature, seal) | Phase 2 | Business name, logo, address, phone, email, GSTIN (optional) |
| D5 | Customer fields beyond the approved form | Phase 3 | Add none |
| D6 | Unit list; HSN/SAC and GST fields | Phase 4 | Seeded unit list in Phase 4; HSN/SAC and GST rate stored, optional |
| D7 | Client invoice sample (layout, labels, fields) | Phase 5B | No final layout. Placeholder only. |
| D8 | Invoice numbering practice | Phase 5B | Do not allocate invoice numbers. Use the internal id. |
| D9 | Tax treatment, discount and rounding | Phase 5B | Line total = quantity x rate. No tax, discount or rounding. |
| D10 | Can drafts be deleted? How are mistakes on issued invoices corrected? | Phase 5 | Drafts editable; issued invoices read-only; no delete; no cancel |
| D11 | Advance payments | Phase 6 | Not built (Path A) |
| D12 | Payment void, refund, receipt | Phase 6 | Not built |
| D13 | Challan sample, number format, extra fields | Phase 7 | Delivery date, delivered by, received by; number = internal id |
| D14 | Challan cancellation | Phase 7 | Not built |
| D15 | Excel export columns | Phases 8, 9 | Default columns in those phases |
| D16 | Any dashboard change versus the reviewed design | Phase 10 | Cards exactly as listed in Phase 10 |
| D17 | Hosting, persistent file storage, backup frequency | Phase 11 | Ask |

---

# PHASES

---

## Phase 0 - Project foundation

Goal: a running backend with shared conventions, ready for modules.

### Build

- Create the Django project and the empty apps from Section 2.2.
- Settings split (`base`, `dev`, `prod`). Environment variables via `.env` (`.env.example` committed, `.env` ignored). PostgreSQL connection. `TIME_ZONE = "Asia/Kolkata"`, `USE_TZ = True`.
- DRF configuration: default permission `IsAuthenticated`, JSON only, the exception handler from Section 3.6, the pagination class from Section 3.7.
- CORS and CSRF configuration per D1 (the frontend will run on a different origin in development).
- `common/`: pagination class, exception handler, permission classes (`IsAdmin`, `IsAdminOrReadOnlyForStaff` if needed), decimal helpers (string output, safe input parsing), date-range parser/validator (`parse_date_range(request)` returning inclusive `(from, to)`, raising `INVALID_DATE_RANGE`), constants module (item types, payment methods, Indian states and union territories list).
- OpenAPI schema (`drf-spectacular`) with a docs page (Swagger UI) and a schema download URL.
- A health endpoint `GET /api/health/` (public, returns status and database connectivity). This is the only other public endpoint.
- Test setup: `pytest.ini`, shared fixtures (admin client, staff client, anonymous client), factory base.
- `README.md` with setup, migrate, run, test commands.

### Endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/health/` | Public | Liveness and database check |
| GET | `/api/schema/` | Public in dev | OpenAPI schema |
| GET | `/api/docs/` | Public in dev | Swagger UI |

### Tests

- Health endpoint returns OK with the database reachable.
- Error handler returns the Section 3.6 shape for 400, 401, 403, 404 and unhandled errors.
- Pagination shape and page-size limit.
- Date-range helper: valid range, From after To, missing value, same-day range.
- Decimal helper: string output; input such as `"0.1"` is exact (no float rounding).

### Completion gate

A clean checkout starts from the README. Migrations run on PostgreSQL. The tests pass. API docs open. A protected test route returns `NOT_AUTHENTICATED` when anonymous.

---

## Phase 1 - Authentication and Staff

Goal: users sign in, and the admin registers and manages staff.

### Data model

`accounts.User` (custom user model, set before the first migration):

| Field | Type | Notes |
|---|---|---|
| id | int | |
| username | string | unique, required |
| full_name | string | required |
| phone | string | required (D2) |
| email | string | optional |
| role | enum | `ADMIN`, `STAFF` |
| is_active | bool | default true |
| password | hashed | write-only in API |
| date_joined, last_login | timestamps | |

### Endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/auth/csrf/` | Public | Sets the CSRF cookie (session approach) |
| POST | `/api/auth/login/` | Public | `{username, password}` -> user object, sets session cookie |
| POST | `/api/auth/logout/` | Any | Ends the session |
| GET | `/api/auth/me/` | Any | Current user (id, username, full_name, phone, email, role) |
| GET | `/api/staff/` | Admin | List (search by name, username, phone; filter `is_active`, `role`) |
| POST | `/api/staff/` | Admin | Register staff (includes initial password and confirmation) |
| GET | `/api/staff/{id}/` | Admin | Detail |
| PATCH | `/api/staff/{id}/` | Admin | Edit details, role, `is_active` |
| POST | `/api/staff/{id}/set-password/` | Admin | `{new_password}` |

Also: management command `create_initial_admin` (reads username and password from environment variables or prompts; never a hard-coded password).

### Rules

- Password validators enforced on create and set-password.
- Login is rate limited (for example 5 failed attempts per minute per username and IP). Failed login returns `VALIDATION_ERROR` with a generic message (do not reveal whether the username exists).
- Inactive users cannot sign in. If a user becomes inactive, their existing session is rejected on the next request (check `is_active` on every authenticated request, or delete their sessions when deactivating).
- An Admin cannot deactivate their own account or change their own role. The last active Admin cannot be deactivated or demoted.
- No self-registration. No permission editor.
- Passwords never appear in any response or log.

### Tests

- Login success and failure. Logout. `me` returns the right user.
- Rate limit triggers `THROTTLED`.
- Anonymous requests rejected (`NOT_AUTHENTICATED`). Staff user calling any staff endpoint gets `PERMISSION_DENIED`.
- Admin creates staff; staff can sign in; Admin deactivates; the staff member's next request fails.
- Cannot deactivate self, cannot demote or deactivate the last Admin.
- Password validators reject weak passwords. Passwords are not in responses.

### Completion gate

Admin signs in, registers a staff member, the staff member signs in, the Admin deactivates them, and their next request fails.

---

## Phase 2 - Settings (business details)

Goal: the business identity is stored once and available to documents.

### Data model

`company.CompanySettings` (exactly one row):

| Field | Type | Notes |
|---|---|---|
| business_name | string | required |
| logo | file | optional, PNG or JPG |
| address | text | required |
| phone | string | required |
| email | string | optional |
| gstin | string | optional, validated format when present |
| updated_at, updated_by | | |

Add other fields (state, bank details, terms, footer, signature, seal) only if the client's invoice or challan format needs them (D4, D7). Each is one migration.

### Endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/settings/company/` | Any | Current details (logo as an absolute URL or null) |
| PATCH | `/api/settings/company/` | Admin | Update details; logo uploaded as multipart |

### Rules

- Exactly one record: create it with a data migration or get-or-create on first read. No create or delete endpoint.
- Logo: PNG or JPG only, maximum 2 MB, verified as a real image (Pillow). Reject everything else with `VALIDATION_ERROR`.
- Save each uploaded logo under a unique file name and never overwrite or delete an old logo file, so issued invoices that reference an older logo still render it (Section 3.5).
- GSTIN format check: 15 characters, pattern `^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$`.
- Changing settings affects new documents only.

### Tests

- Only one record can exist. Admin can update; Staff gets `PERMISSION_DENIED` on update but can read.
- Logo: valid PNG/JPG accepted; wrong type, oversized, and non-image content with an image extension rejected.
- Replacing a logo keeps the old file on disk.
- GSTIN validation.

### Completion gate

Admin saves details and a logo, and a later `GET` returns them.

---

## Phase 3 - Customers

Goal: customers are registered once and reused.

### Data model

`customers.Customer` (approved form):

| Field | Type | Notes |
|---|---|---|
| id | int | |
| code | string | auto-generated, unique, read-only, for example `C0001` |
| name | string | required |
| phone | string | 10 to 15 digits, optional leading `+` (spaces and hyphens ignored) |
| gstin | string | optional, same pattern as Phase 2 |
| state | string | one value from the Indian states and union territories list in `common` |
| billing_address | text | |
| is_active | bool | default true |
| created_at, updated_at | | |

Add email, shipping address or notes only if the invoice or challan format needs them (D5).

Fields added later (read-only, computed): `outstanding_amount` (Phase 6).

### Endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/customers/` | Any | List. `?search=` matches name, phone, code. `?is_active=` filter |
| POST | `/api/customers/` | Any | Create |
| GET | `/api/customers/{id}/` | Any | Detail |
| PATCH | `/api/customers/{id}/` | Any | Update, including `is_active` |

Ordering: name ascending by default.

### Rules

- Code generation is safe under concurrent creation (lock a counter row or use a database sequence). No duplicate codes.
- No delete endpoint. Inactive customers remain in history but cannot be used on new invoices (enforced in Phase 5).
- Search is case-insensitive.

### Tests

- Create, update, search by name, phone and code (case-insensitive), `is_active` filter.
- Codes are unique and sequential, including under concurrent creation.
- Validation: missing name, bad phone, bad GSTIN, unknown state.

### Completion gate

Customers can be created, searched, edited and deactivated through the API.

---

## Phase 4 - Products and inventory

Goal: a catalogue with three item types and correct stock.

### Data model

`products.Unit`: `name` (unique). Seeded: pcs, bag, kg, litre, box, trip, metre, foot, set, pair, roll. Managed through Django admin (D6).

`products.Product`:

| Field | Type | Notes |
|---|---|---|
| id | int | |
| code | string | unique; auto-generated (for example `P0001`) if blank |
| name | string | required |
| description | text | optional |
| item_type | enum | `GOODS`, `GOODS_HARDWARE`, `SERVICE` |
| unit | FK Unit | required |
| selling_price | money | >= 0 |
| hsn_sac | string | optional |
| gst_rate | decimal(5,2) | optional, 0 to 100 |
| reorder_level | quantity | optional, goods only |
| current_stock | quantity | stored; always 0 for Service; never edited directly |
| is_active | bool | default true |
| created_at, updated_at | | |

Computed in the API: `tracks_stock` (true for the two goods types), `is_low_stock` (tracked, reorder level set, stock <= reorder level).

`inventory.StockMovement`:

| Field | Type | Notes |
|---|---|---|
| id | int | |
| product | FK Product | PROTECT |
| movement_type | enum | `OPENING`, `STOCK_IN`, `ADJUSTMENT`, `SALE` |
| quantity_change | quantity | signed, never 0 |
| balance_after | quantity | stock after this movement |
| reason | string | |
| invoice | FK Invoice, nullable | added by the Phase 5 migration; PROTECT |
| created_by | FK User | |
| created_at | timestamp | |

Database constraints: `CHECK (current_stock >= 0)`; `CHECK (quantity_change <> 0)`; item type values restricted to the enum.

### The stock service

`inventory.services.apply_stock_movement(product_id, change, movement_type, reason, user, invoice=None)`:

1. Runs in a transaction (joins the caller's transaction if one is open).
2. Locks the product row (`select_for_update`).
3. Rejects Service products.
4. Rejects a result below zero (`INSUFFICIENT_STOCK`).
5. Updates `current_stock`, writes the movement with `balance_after`.

This is the only code allowed to change `current_stock`.

### Endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/units/` | Any | Unit list |
| GET | `/api/products/` | Any | List. `?search=` (name, code), `?item_type=`, `?is_active=`, `?low_stock=true`. Search and filters combine |
| POST | `/api/products/` | Any | Create. Optional write-only `opening_stock` (goods only) |
| GET | `/api/products/{id}/` | Any | Detail |
| PATCH | `/api/products/{id}/` | Any | Update (not stock) |
| POST | `/api/products/{id}/stock-in/` | Any | `{quantity, reason?}`, quantity > 0 |
| POST | `/api/products/{id}/adjust/` | Any | `{quantity_change, reason}`, may be negative, reason required |
| GET | `/api/stock-movements/` | Any | List. `?product=`, `?item_type=`, `?movement_type=`, `?from=`, `?to=` |

(D3: restrict `adjust` to Admin only if the client asks.)

### Rules

- Creating a Goods or Goods (Hardware) product with `opening_stock` greater than 0 creates one `OPENING` movement in the same transaction. Service products reject `opening_stock` and `reorder_level`.
- `OPENING` is only created at product creation.
- Item type cannot be changed to or from `SERVICE` once the product has any movement. Changing between `GOODS` and `GOODS_HARDWARE` is allowed.
- Stock-in quantity must be greater than 0. Adjustment must be non-zero, with a reason.
- Editing price or details never changes issued invoices (Phase 5 snapshots).
- Inactive products cannot be added to new invoices (enforced in Phase 5). Existing history stays.
- Management command `check_stock_consistency`: for every tracked product, compares `current_stock` with the sum of `quantity_change`, and reports any mismatch (exit code non-zero if any).

### Tests

- Each item type: stock tracked for both goods types; not for Service.
- Search and `item_type` filter combine; `low_stock` filter.
- Opening stock, stock-in and adjustment create correct movements with correct `balance_after`.
- Negative result rejected (`INSUFFICIENT_STOCK`). Service stock operation rejected. Zero or negative stock-in rejected.
- Item-type change rule.
- Two concurrent adjustments cannot take stock below zero.
- `check_stock_consistency` passes after a scenario and detects a manually corrupted value.

### Completion gate

Each item type, the filters, opening stock, stock-in, adjustment and the negative-stock rule are tested and pass before starting Phase 5.

---

## Phase 5 - Invoices

Goal: draft, review and issue invoices; stock is deducted exactly once; the document follows the client's format.

This phase has two parts.

- Phase 5A can be built now.
- Phase 5B needs the client's invoice sample and answers to D7, D8 and D9. Do not invent GST rules, numbering, cancellation, credit notes, or the final layout.

### 5A - Invoice core (build now)

#### Data model

`invoices.Invoice`:

| Field | Type | Notes |
|---|---|---|
| id | int | |
| invoice_number | string, nullable | stays empty until D8 is answered; unique when set |
| customer | FK Customer | PROTECT; must be active |
| invoice_date | date | required |
| notes | text | optional |
| status | enum | `DRAFT`, `ISSUED` |
| subtotal | money | calculated |
| grand_total | money | calculated |
| business_snapshot | JSON | set at issue |
| customer_snapshot | JSON | set at issue |
| created_by, created_at, updated_at | | |
| issued_by, issued_at | | set at issue |

`invoices.InvoiceItem`:

| Field | Type | Notes |
|---|---|---|
| id | int | |
| invoice | FK Invoice | PROTECT |
| line_no | int | order |
| product | FK Product | PROTECT; must be active |
| product_name, product_code, hsn_sac, unit_name, item_type | snapshot | copied from the product when the line is saved, and refreshed at issue |
| quantity | quantity | > 0 |
| rate | money | >= 0, defaults to the product price when omitted |
| line_total | money | calculated |

Snapshot contents:

- `business_snapshot`: business name, address, phone, email, GSTIN, logo file path.
- `customer_snapshot`: code, name, phone, GSTIN, state, billing address.

Computed (read-only) fields added by later phases: `paid_amount`, `balance_due`, `payment_status` (Phase 6); `delivery_status` (Phase 7).

#### Calculation service

`invoices.services.calculate_invoice(lines)` returns line totals, subtotal and grand total.

- It is one isolated function so the client's tax, discount and rounding rules (D9) can be added in 5B without touching anything else.
- Until D9 is answered: line total = quantity x rate; subtotal = sum of line totals; grand total = subtotal.
- Totals sent by a client are ignored.

#### Endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/invoices/` | Any | List. `?search=` (customer name, invoice number), `?status=`, `?customer=`, `?from=`, `?to=` (invoice date) |
| POST | `/api/invoices/` | Any | Create a draft |
| GET | `/api/invoices/{id}/` | Any | Detail with lines, totals and (when issued) snapshots |
| PATCH | `/api/invoices/{id}/` | Any | Edit a draft (customer, date, notes, full `lines` list) |
| POST | `/api/invoices/calculate/` | Any | Stateless: same payload as create, returns calculated line totals and totals, saves nothing (for preview) |
| POST | `/api/invoices/{id}/issue/` | Any | Issue the draft |
| GET | `/api/invoices/{id}/document/` | Any | Printable document (placeholder until 5B) |

Create/update payload:

```json
{
  "customer": 1,
  "invoice_date": "2026-11-17",
  "notes": "",
  "lines": [ { "product": 3, "quantity": "10", "rate": "390.00" } ]
}
```

`lines` on PATCH replaces the whole list (delete and recreate inside one transaction). Ordering for lists: newest invoice date first, then id.

#### Issue service

`invoices.services.issue_invoice(invoice_id, user)`, inside one `transaction.atomic()`:

1. Lock the invoice row. If it is already `ISSUED`, return it as a normal success with no side effects. This makes retries and double clicks safe, including simultaneous requests (the second waits for the lock, then sees the issued invoice).
2. Validate: customer present and active; at least one line; quantity > 0; rate >= 0; products exist and are active.
3. Lock the stock-tracked products in id order. Sum the quantity per product across lines (the same product can appear on several lines). If any product is short, abort the whole issue with `INSUFFICIENT_STOCK`, listing each short product with available and required quantities. The draft stays a draft.
4. Recalculate totals with `calculate_invoice`.
5. Save the business, customer and line snapshots.
6. For each stock-tracked line, call `apply_stock_movement` with type `SALE` and a negative quantity, linked to the invoice. No movement for Service lines.
7. Set `status = ISSUED`, `issued_by`, `issued_at`.

#### Rules

- A draft has no stock effect and no number. Drafts can be edited until issued.
- Issued invoices cannot be edited, and there is no delete or cancel in V1. Editing an issued invoice returns `INVALID_STATE`. (D10: confirm with the client how mistakes are corrected.)
- Draft delete: not built unless D10 approves it.
- Payment status and delivery status are added by Phases 6 and 7.
- Nothing in the invoice API creates a challan.

#### 5A tests

- Draft create and edit change no stock and set no number.
- Issue deducts the right stock for Goods and Goods (Hardware), none for Service.
- The same product on two lines is checked and deducted by the combined quantity.
- Insufficient stock aborts the entire issue, keeps the draft, and the error lists each product.
- Issuing twice deducts once and returns success the second time.
- Two simultaneous issues competing for limited stock: exactly one succeeds.
- Issued invoice keeps its customer, product and business details after those records change.
- Client-sent totals are ignored. `calculate` returns the same numbers `issue` will store.
- Inactive customer or product rejected. Editing an issued invoice returns `INVALID_STATE`.
- Stock consistency check passes after the scenarios.

### 5B - Client format, numbering and rules (after the invoice sample)

Start only after the client supplies the sample and confirms D7, D8 and D9.

- Add the exact fields, labels and layout from the sample.
- Add the confirmed invoice numbering (D8) and assign the number inside the issue transaction so rollback also rolls back the number.
- Add the confirmed tax, discount and rounding calculations (D9) inside `calculate_invoice`, add the extra stored and snapshot fields they need, and expose them in the API. Get worked examples from the client or their CA and turn them into unit tests.
- Build the document output at `GET /api/invoices/{id}/document/` as a PDF (`application/pdf`) from one isolated HTML template. Recommended: server-side HTML-to-PDF (WeasyPrint) with an embedded font that includes the rupee sign. Issued invoices render from their snapshots. Drafts render from live data and are marked as drafts if the format allows. Keep the template separate from models and calculations so the layout can change without touching them.
- Test long invoices (for example 50 lines) for page breaks.
- Client approves a sample PDF before this phase is complete.

### Completion gate

Client-provided worked examples and stock scenarios pass. The client approves the generated invoice.

---

## Phase 6 - Payments and outstanding balances

Goal: record payments, allocate them to invoices, and derive balances and customer outstanding.

### Data model

`payments.Payment`:

| Field | Type | Notes |
|---|---|---|
| id | int | |
| customer | FK Customer | PROTECT |
| payment_date | date | required |
| amount | money | > 0 |
| method | enum | `CASH`, `UPI`, `BANK_TRANSFER`, `CHEQUE` |
| reference | string | optional |
| note | text | optional |
| client_token | UUID, nullable | unique when set; retry safety |
| received_by | FK User | |
| created_at | timestamp | |

`payments.PaymentAllocation`: `payment` (FK, PROTECT), `invoice` (FK, PROTECT), `amount` (money). Constraints: unique (`payment`, `invoice`); `CHECK (amount > 0)`.

### Derived values (calculated by queries/annotations, never stored as editable)

- Invoice `paid_amount` = sum of its allocations.
- Invoice `balance_due` = `grand_total` - `paid_amount`.
- Invoice `payment_status`: `UNPAID` (paid 0), `PARTIALLY_PAID` (0 < paid < total), `PAID` (paid >= total; a zero-total invoice is `PAID`).
- Customer `outstanding_amount` = sum of `balance_due` across the customer's `ISSUED` invoices.

Add `paid_amount`, `balance_due`, `payment_status` to the invoice list and detail serializers (with a `?payment_status=` filter), and `outstanding_amount` to the customer serializers. Use annotations to avoid N+1 queries.

### Endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/payments/` | Any | List. `?customer=`, `?method=`, `?from=`, `?to=`, `?search=` (reference, customer name) |
| POST | `/api/payments/` | Any | Record a payment with allocations |
| GET | `/api/payments/{id}/` | Any | Detail with allocations |
| GET | `/api/customers/{id}/open-invoices/` | Any | Issued invoices of the customer with a balance, oldest first |
| GET | `/api/customers/{id}/payments/` | Any | The customer's payments |
| GET | `/api/customers/{id}/statement/` | Any | Entries with running balance (see below) |
| GET | `/api/invoices/{id}/payments/` | Any | Payments allocated to the invoice |

Create payload:

```json
{
  "customer": 1,
  "payment_date": "2026-11-17",
  "amount": "5000.00",
  "method": "UPI",
  "reference": "UPI-4821",
  "note": "",
  "client_token": "uuid-optional",
  "allocations": [ { "invoice": 12, "amount": "5000.00" } ]
}
```

Statement entries: each issued invoice is a debit (its `grand_total`, on its invoice date); each payment is a credit (its `amount`, on its payment date). Sorted by date then creation order, with a running balance (debits minus credits).

### Rules (create payment, one transaction)

- Amount > 0; method in the list.
- Lock the target invoices in id order before checking balances.
- Every allocation targets an `ISSUED` invoice that belongs to the payment's customer. An invoice appears once per payment. Allocation amounts are > 0.
- An allocation cannot exceed the invoice's remaining balance (`OVER_ALLOCATION`).
- Retry with the same `client_token` returns the existing payment (200) and creates nothing new.
- Payments are never edited or deleted in V1 (D12).

PENDING DECISION D11 (advance payments). The reviewed prototype showed advances and customer credit, but the baseline supports advances only if the client confirms.

- Path A (default, build now): the allocations must add up exactly to the payment amount, so every payment is fully applied to existing invoices. Partial, full and multiple payments per invoice all work. A payment whose allocations do not sum to its amount is rejected with `VALIDATION_ERROR`.
- Path B (only after confirmation): allow an unallocated remainder (advance or overpayment) kept as customer credit, with an "apply credit to invoice" action. First confirm how unused amounts are displayed, applied and returned. Void, refund and receipt (D12) are separate approvals and are not part of Path B.

### Tests

- One invoice with several partial payments, then a full settlement: statuses and balances correct at each step.
- Over-allocation to an invoice, and allocations not summing to the amount (Path A), rejected.
- Allocation to a draft invoice or to another customer's invoice rejected. Duplicate invoice in one payment rejected.
- Two concurrent payments cannot over-allocate one invoice.
- Retry with the same `client_token` creates one payment.
- Customer `outstanding_amount` equals the sum of invoice balances.
- Statement running balance equals outstanding when all entries are included.
- If Path B is approved: advance recorded before an invoice, applied later, statuses and balances correct.

### Completion gate

One invoice with multiple partial payments, a fully settled invoice, and any approved advance scenario pass.

---

## Phase 7 - Delivery Challan

Goal: record dispatch against issued invoices, including partial delivery, without touching stock.

### Data model

`delivery.DeliveryChallan`:

| Field | Type | Notes |
|---|---|---|
| id | int | also the challan number until D13 is answered |
| invoice | FK Invoice | PROTECT; must be `ISSUED` |
| delivery_date | date | required |
| delivered_by | string | |
| received_by | string | |
| created_by, created_at | | |

Add other fields the approved challan format needs (D13).

`delivery.DeliveryChallanItem`: `challan` (FK), `invoice_item` (FK InvoiceItem, PROTECT), `quantity` (> 0). Name and unit come from the invoice item's snapshot.

### Derived values

- Per invoice line: `remaining = invoiced quantity - sum of dispatched on challans`.
- Invoice `delivery_status`: `PENDING` (nothing dispatched), `PARTIALLY_DELIVERED`, `DELIVERED` (every stock-tracked line fully dispatched). `null` when the invoice has no stock-tracked lines.
- Add `delivery_status` (read-only) to the invoice list and detail, with a `?delivery_status=` filter. Use annotations to avoid N+1 queries.

### Endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/challans/` | Any | List. `?invoice=`, `?customer=`, `?from=`, `?to=` |
| POST | `/api/challans/` | Any | Create |
| GET | `/api/challans/{id}/` | Any | Detail with items |
| GET | `/api/challans/{id}/document/` | Any | Printable PDF in the agreed design |
| GET | `/api/invoices/{id}/dispatch-summary/` | Any | Per line: invoiced, dispatched, remaining |
| GET | `/api/invoices/awaiting-dispatch/` | Any | Issued invoices with goods still to dispatch (for the create screen) |

Create payload:

```json
{
  "invoice": 12,
  "delivery_date": "2026-11-18",
  "delivered_by": "Ravi",
  "received_by": "Site supervisor",
  "items": [ { "invoice_item": 31, "quantity": "150" } ]
}
```

### Rules (create challan, one transaction)

- The invoice must be `ISSUED`. Draft invoices are rejected (`INVALID_STATE`).
- Only stock-tracked lines (Goods and Goods (Hardware)) can be dispatched. Service lines are rejected.
- Lock the invoice's lines. Each quantity must be > 0 and not exceed the line's remaining quantity (`OVER_DISPATCH`). At least one item is required. Each invoice line appears once per challan.
- Several challans per invoice are allowed.
- A challan never creates a stock movement and never changes `current_stock`.
- Challan cancellation is a change request (D14) and is not built. No edit or delete in V1.
- Challan document: render from the invoice item snapshots and the saved business snapshot. Layout follows the challan sample (D13). Until then, a plain placeholder.

### Tests

- Partial challan, then a second challan completes delivery; status is right each time; remaining quantities update.
- Over-dispatch rejected, including two simultaneous challans for the same remaining quantity (one succeeds).
- Stock and movements are identical before and after challan creation.
- Draft invoice and service-only invoice cannot receive challans; service lines rejected.
- `awaiting-dispatch` lists only invoices with remaining goods.

### Completion gate

An invoice delivered in several challans shows correct remaining quantities and final status, and stock never changes.

---

## Phase 8 - Expenses (with Excel export)

Goal: record expenses and export a date range to Excel.

### Data model

`expenses.ExpenseCategory`: `name` (unique). Seeded: Rent, Electricity, Transport, Salary, Repairs, Other. Managed through Django admin.

`expenses.Expense`:

| Field | Type | Notes |
|---|---|---|
| id | int | |
| date | date | required |
| category | FK ExpenseCategory | required |
| description | string | |
| amount | money | > 0 |
| payment_method | enum, optional | `CASH`, `UPI`, `BANK_TRANSFER`, `CHEQUE` |
| paid_to | string | optional |
| notes | text | optional |
| recorded_by | FK User | |
| created_at, updated_at | | |

### Endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/expense-categories/` | Any | Category list |
| GET | `/api/expenses/` | Any | List. `?search=`, `?category=`, `?from=`, `?to=` (inclusive). Response adds `total_amount` for all filtered records (not just the page) |
| POST | `/api/expenses/` | Any | Create |
| GET | `/api/expenses/{id}/` | Any | Detail |
| PATCH | `/api/expenses/{id}/` | Any | Update |
| GET | `/api/expenses/export/` | Any | `?from=YYYY-MM-DD&to=YYYY-MM-DD` -> `.xlsx` download |

List ordering: newest date first, then id. No delete in V1 unless the client approves.

### Shared export helper (`common/exports.py`, reused by Phase 9)

- Builds a real `.xlsx` workbook with `openpyxl` and returns an `HttpResponse` with the correct content type and `Content-Disposition: attachment; filename="..."`.
- Validates the range with the Phase 0 date-range helper: both dates required, From not after To, both inclusive. Failures return `INVALID_DATE_RANGE` (400), not a file.
- Date cells are real Excel dates formatted `DD/MM/YYYY`. Amount cells are numeric with 2 decimals so Excel can sum them.
- A title row naming the period (for example `Period: 01/11/2026 to 16/11/2026`), a bold header row, the data rows sorted by date then id, and a bold total row whose value equals the sum of the exported rows.
- Text cells starting with `=`, `+`, `-` or `@` are escaped (prefix with a single quote or store as an explicit string) so Excel never runs them as formulas.
- An empty range returns a valid workbook with headers and a total of 0.

### Expense export specifics

- Default columns (D15): Date, Category, Description, Payment method, Paid to, Notes, Amount, Recorded by.
- File name: `expenses_YYYY-MM-DD_to_YYYY-MM-DD.xlsx`.
- Only expenses dated between From and To inclusive.

### Tests

- Create, update, list, search, category and date filters. `total_amount` matches the filtered records.
- Export: empty range, one-day range, records exactly on both boundary dates included, multi-day range, records outside the range excluded, invalid range rejected, missing date rejected.
- Exported rows and total equal the filtered data. The file opens with `openpyxl` as a valid workbook; dates and amounts are real date and numeric cells.
- A description such as `=SUM(A1)` is escaped.
- Staff and Admin can both export; anonymous cannot.

### Completion gate

Export verified for empty, one-day, boundary, multi-day and invalid ranges.

---

## Phase 9 - Other Income (with Excel export)

Goal: record other income and export a date range to Excel.

### Data model

`other_income.IncomeCategory`: `name` (unique). Seeded: Scrap sale, Commission, Interest, Other. Managed through Django admin.

`other_income.OtherIncome`:

| Field | Type | Notes |
|---|---|---|
| id | int | |
| date | date | required |
| category | FK IncomeCategory | required |
| description | string | |
| amount | money | > 0 |
| payment_method | enum, optional | same values as expenses |
| received_from | string | optional |
| notes | text | optional |
| recorded_by | FK User | |
| created_at, updated_at | | |

### Endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/income-categories/` | Any | Category list |
| GET | `/api/other-income/` | Any | List. `?search=`, `?category=`, `?from=`, `?to=` (inclusive). Response adds `total_amount` |
| POST | `/api/other-income/` | Any | Create |
| GET | `/api/other-income/{id}/` | Any | Detail |
| PATCH | `/api/other-income/{id}/` | Any | Update |
| GET | `/api/other-income/export/` | Any | `?from=...&to=...` -> `.xlsx` download |

### Rules and export

- Same rules as Phase 8. Reuse the shared export helper; do not copy it.
- Default columns (D15): Date, Category, Description, Payment method, Received from, Notes, Amount, Recorded by.
- File name: `other_income_YYYY-MM-DD_to_YYYY-MM-DD.xlsx`.

### Tests

Same as Phase 8, against other-income data.

### Completion gate

Export verified for empty, one-day, boundary, multi-day and invalid ranges.

---

## Phase 10 - Dashboard

Goal: the reviewed dashboard's figures from one endpoint. Do not add metrics, charts or lists that were not approved (D16).

### Endpoint

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/dashboard/` | Any | All dashboard values |

Response shape:

```json
{
  "as_of": "2026-11-17",
  "today_sales": "0.00",
  "month_sales": { "amount": "70529.00", "invoice_count": 3 },
  "month_payments_received": "36830.00",
  "outstanding_amount": "38699.00",
  "stock": { "tracked_product_count": 4, "low_stock_count": 1 },
  "month_expenses": "20000.00",
  "month_other_income": "2500.00",
  "open_challans_to_dispatch": 2,
  "recent_invoices": [
    { "id": 12, "invoice_number": null, "invoice_date": "2026-11-16", "customer_name": "Kumar Hardware",
      "grand_total": "22621.00", "payment_status": "UNPAID" }
  ],
  "low_stock_products": [
    { "id": 4, "name": "Wall putty 20 kg", "current_stock": "8.000", "reorder_level": "10.000", "unit": "bag" }
  ]
}
```

### Definitions (reuse the same queries and rules as the modules)

- Today = `timezone.localdate()` (Asia/Kolkata). This month = the calendar month of today, start to end inclusive.
- `today_sales`: sum of `grand_total` of `ISSUED` invoices with `invoice_date` = today.
- `month_sales`: sum and count of `ISSUED` invoices with `invoice_date` in this month.
- `month_payments_received`: sum of payments with `payment_date` in this month.
- `outstanding_amount`: sum of `balance_due` across `ISSUED` invoices.
- `stock`: count of active Goods and Goods (Hardware) products, and how many of them are low (stock at or below a set reorder level).
- `month_expenses`, `month_other_income`: sums by `date` in this month.
- `open_challans_to_dispatch`: number of `ISSUED` invoices with delivery status `PENDING` or `PARTIALLY_DELIVERED`.
- `recent_invoices`: last 5 issued invoices (by `issued_at`).
- `low_stock_products`: the low-stock products, lowest stock first.

### Tests

- Each value equals the total of its underlying records for the same period (compare against the module list endpoints).
- Date boundaries: an invoice on the first and last day of the month, and "today" around midnight Asia/Kolkata (freeze time, for example with `freezegun`).
- Empty database returns zeros and empty lists, not errors.
- Query count stays small and fixed.

### Completion gate

Dashboard values reconcile with the underlying lists and match the reviewed dashboard.

---

## Phase 11 - Hardening, API contract freeze and staging

Goal: a stable, documented, tested backend that the frontend can be planned against.

### 11.1 Review and hardening

- Walk every endpoint against the approved workflows. Remove anything that is not in the approved scope.
- Automated permission test: iterate every registered route and assert that an anonymous request returns `NOT_AUTHENTICATED` (except the public routes), and that Staff gets `PERMISSION_DENIED` on Admin-only routes.
- Check model relationships, `PROTECT` rules and database constraints (stock >= 0, allocation > 0, unique keys).
- Re-check transaction boundaries and locking for invoice issue, payment creation and challan creation.
- Query review: no N+1 on list endpoints, indexes on foreign keys and filter fields (dates, status, customer, product), `EXPLAIN` on the heaviest lists.
- Decimal serialization and date handling (Asia/Kolkata) verified end to end.
- Logging configured. No sensitive data in logs.

### 11.2 End-to-end API workflow test (automated)

One test that drives the whole workflow through the API:

1. Admin logs in. Saves business details and a logo.
2. Admin registers a staff member; the staff member logs in.
3. Create a customer.
4. Create a Goods product with opening stock, a Goods (Hardware) product with opening stock, and a Service product.
5. Search products and filter by each item type.
6. Create a draft invoice with goods, hardware and service lines. Confirm stock unchanged.
7. Issue the invoice. Confirm stock decreased once for the two goods types and no movement for the service.
8. Retry the issue call. Confirm nothing changed.
9. Record a partial payment, check balance. Record a payment that settles it, check zero balance.
10. Create a challan for part of the quantity; confirm remaining quantity. Create a second challan for the rest; confirm status `DELIVERED` and that stock did not change.
11. Add expenses and other income. Export each for a date range; verify boundaries and totals.
12. Check the dashboard against the lists.
13. Run `check_stock_consistency`.

Also cover: invalid data, insufficient stock, over-dispatch, invalid date ranges, direct-API permission checks.

### 11.3 API contract freeze

Produce and commit:

- `openapi.yaml` generated from `drf-spectacular`, with no schema warnings, every endpoint described, request and response examples, and all enums.
- `API_NOTES.md`: authentication flow (CSRF endpoint, login, cookie behaviour, logout, 401 handling), error format and the error-code table, pagination shape, money/quantity/date formats, enum values (roles, item types, movement types, invoice status, payment status, delivery status, payment methods), file upload and download behaviour (logo upload, PDF and Excel downloads), the list of filters per endpoint, and every PENDING DECISION still open with its current default.
- `seed_demo_data` management command (development only; refuses to run when `DEBUG` is false): creates sample staff, customers, products, invoices, payments, challans, expenses and income for frontend development and demos.
- A Postman collection or equivalent request examples (optional).

This is what to hand over for the frontend plan.

### 11.4 Staging deployment

- Production-style settings with environment variables and secrets (nothing in Git). Staging PostgreSQL.
- HTTPS. CORS, CSRF and cookie settings reviewed for the frontend's origin.
- Persistent media storage for logos (D17).
- Daily database backups, and a restore tested in a separate environment.
- Run migrations, create the initial admin, load business details and categories.
- Smoke test through the API: login, master data, invoice issue, payment, challan, both exports.

Production go-live happens after the frontend is built and the client approves the invoice and challan documents.

### Backend is complete when

- All twelve phases (0 to 11) pass their completion gates.
- The invoice and challan documents are approved by the client.
- Stock, payment and delivery quantities stay consistent under the tests, including concurrency.
- Both Excel exports contain only the selected range and correct totals.
- The dashboard reconciles with the underlying data.
- `openapi.yaml` and `API_NOTES.md` are committed and match the implementation.
- Staging is deployed with a verified backup restore.
