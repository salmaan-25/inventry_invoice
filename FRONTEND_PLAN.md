# Billing & Inventory Management System: Frontend Implementation Plan (V1)

> **Audience:** the developer and any LLM/coding agent building the frontend.
> **Sources of truth:** `API_CONTRACT.md` (backend contract) + this plan + `FRONTEND_SKILL.md` (coding rules).
> **Read order for an LLM:** 1) `FRONTEND_SKILL.md` → 2) this plan → 3) `API_CONTRACT.md` for the phase being built.
> If the contract and this plan disagree, **the contract wins for API shapes**, and this plan wins for structure and conventions. If something is missing from both, **stop and ask**; do not guess.

---

## 1. Tech Stack (fixed)

| Concern | Choice | Notes |
|---|---|---|
| Build tool | **Vite + React 18 + TypeScript (strict)** | Matches repo (`dist/`, `index.html`, `netlify.toml`) |
| UI | **MUI v5/v6 (`@mui/material`, `@mui/icons-material`)** | Only design system allowed. Themed in `src/theme.ts` |
| Dates | `@mui/x-date-pickers` + `dayjs` | MIT-licensed, ISO `YYYY-MM-DD` at the API boundary |
| Server state / API | **RTK Query** (`@reduxjs/toolkit`) | No axios, no raw `fetch` in components |
| Client state | **Redux Toolkit slices** | Only for auth user, UI (snackbar, sidebar), nothing server-owned |
| Forms | `react-hook-form` + `zod` (`@hookform/resolvers`) | Schemas in `src/schemas/` |
| Routing | `react-router-dom` v6 (data router) | Lazy-loaded pages |
| Money math | `decimal.js` | Wrapped in `src/utils/money.ts`. **Never** use `number` for money/qty |
| Lint/format | ESLint (existing `eslint.config.js`) + Prettier | CI fails on warnings |
| Testing | Vitest + React Testing Library + MSW | Utils, schemas, key flows |
| Hosting | Netlify (`netlify.toml`) | See §9 for the cookie/CSRF proxy requirement |

---

## 2. Non-Negotiable Engineering Rules

These are repeated in `FRONTEND_SKILL.md`. Every PR/generation must satisfy them.

1. **Strict TypeScript.** `"strict": true`, `noUncheckedIndexedAccess`, `noImplicitOverride`. No `any`, no `@ts-ignore`/`@ts-expect-error`, no non-null assertion `!`, no unchecked `as` casts.
2. **No `null` in app code.** Use `undefined` / optional props / empty-string for form fields.
   - *Only exception:* DTO fields the contract **literally returns as JSON `null`** (`next`, `previous`, `StockMovement.invoice`, `company.logo` if blank). These are typed `T | null` **only** inside `src/types/api/*` and are converted at the boundary (`transformResponse` or a selector) or handled immediately. Never leak `null` into props, state, form values, or utils.
3. **Reuse before create.** Search `components/common`, `components/form`, `components/data-display`, and `hooks/` first. Pages **compose** components; they contain no styling blobs, no duplicated tables/dialogs/forms.
4. **MUI only.** Use MUI components, the `sx` prop, and theme tokens. No other UI library, no raw CSS colors/px magic numbers in components, no inline hex colors. Global styles only in `index.css`/`App.css` (minimal reset).
5. **RTK Query for every API call; Redux slices for client state.** Endpoints are injected into one `baseApi`, one file per domain in `store/api/`. Components consume generated hooks only.
6. **No unwanted hardcoding.** Routes, enum labels, API paths, error codes, messages, page sizes, debounce delays, tag names, env values → `src/constants/` (or `.env` via `src/constants/config.ts`).
7. **Utilities live in `src/utils/`**, hooks in `src/hooks/`. If a function is used (or obviously reusable) in 2+ places, or is pure formatting/parsing/validation logic, it goes in utils. Utils are pure and unit-tested.
8. **Money & quantity are strings.** Contract: money = 2-decimal string, qty = 3-decimal string. Display via `formatCurrency` / `formatQuantity`. Arithmetic only via `utils/money.ts` (Decimal). Server-calculated totals are authoritative; never recompute GST client-side.
9. **Types mirror the contract.** All DTOs, request bodies, enums, and query params typed in `src/types/`. Enums are `as const` objects + derived union types (not TS `enum`).
10. **Every list = loading, empty, error, and data state.** Every mutation = pending state, success snackbar, and parsed error display (field errors mapped onto form fields).
11. **No secrets/tokens in `localStorage`/`sessionStorage`.** Auth is session cookies only. `credentials: 'include'` on every call.
12. **Accessibility & responsiveness:** labelled inputs, keyboard-operable dialogs, `xs`→`lg` responsive layouts via MUI breakpoints.

---

## 3. Target Repository Structure

Existing folders are kept; folders marked **(new)** are added for industry-standard separation.

```
.github/workflows/ci.yml        # lint + typecheck + test + build
public/
src/
├── assets/                     # logo, illustrations (static only)
├── components/
│   ├── common/                 # PageHeader, ConfirmDialog, EmptyState, LoadingScreen,
│   │                           # StatusChip, MoneyText, DateText, SearchField, SectionCard,
│   │                           # FormDialog, RoleGate, FileDownloadButton
│   ├── data-display/           # DataTable, TablePagination wrapper, FilterBar, StatCard, KeyValueList
│   ├── feedback/               # ErrorBoundary, SnackbarHost, ApiErrorAlert, NotFoundState
│   ├── form/                   # RHF-bound: FormTextField, FormSelect, FormAutocomplete,
│   │                           # FormDatePicker, FormMoneyField, FormQuantityField, FormSwitch
│   ├── layout/                 # AppShell, Sidebar, Topbar, AuthLayout
│   ├── customers/              # CustomerForm, CustomerPicker, OpenInvoicesTable, StatementTable
│   ├── products/               # ProductForm, ProductPicker, StockInDialog, AdjustStockDialog, StockBadge
│   ├── invoices/               # InvoiceForm, InvoiceLineEditor, InvoiceTotalsPanel, InvoiceActions, InvoiceStatusChip
│   ├── challans/               # ChallanForm, DispatchLinesTable
│   ├── payments/               # PaymentForm, AllocationTable
│   ├── expenses/               # ExpenseForm, ExpenseCategoryDialog
│   ├── income/                 # OtherIncomeForm, IncomeCategoryDialog
│   ├── staff/                  # StaffForm, SetPasswordDialog
│   ├── company/                # CompanyProfileForm, LogoUploader
│   └── dashboard/              # KpiGrid, RecentInvoicesCard, LowStockCard
├── constants/                  # (new)
│   ├── routes.ts               # ROUTES map + path builders
│   ├── navigation.ts           # sidebar items + required roles
│   ├── enums.ts                # Role, ItemType, InvoiceStatus, PaymentMethod, MovementType + label maps
│   ├── apiErrorCodes.ts        # VALIDATION_ERROR, INSUFFICIENT_STOCK, ...
│   ├── messages.ts             # all user-facing strings (success/error/confirm)
│   ├── pagination.ts           # DEFAULT_PAGE_SIZE=25, MAX_PAGE_SIZE=100, PAGE_SIZE_OPTIONS
│   ├── validation.ts           # GSTIN regex, phone length 10–15, max logo size 2MB, etc.
│   └── config.ts               # typed access to import.meta.env (VITE_API_BASE_URL, ...)
├── hooks/
│   ├── useAuth.ts              # current user + role helpers
│   ├── useDebounce.ts
│   ├── usePaginationParams.ts  # page/page_size/search/filters synced to URL search params
│   ├── useDateRangeFilter.ts   # from/to + INVALID_DATE_RANGE guard
│   ├── useApiFormErrors.ts     # map field_errors → RHF setError, toast detail
│   ├── useFileDownload.ts      # blob download / open-in-tab with loading state
│   └── useNotify.ts            # dispatches snackbar slice actions
├── pages/                      # route-level screens only (thin, compose components)
│   ├── auth/LoginPage.tsx
│   ├── dashboard/DashboardPage.tsx
│   ├── customers/{CustomerListPage,CustomerFormPage,CustomerDetailPage}.tsx
│   ├── products/{ProductListPage,ProductFormPage,ProductDetailPage}.tsx
│   ├── inventory/StockMovementsPage.tsx
│   ├── invoices/{InvoiceListPage,InvoiceCreatePage,InvoiceEditPage,InvoiceDetailPage}.tsx
│   ├── challans/{ChallanListPage,ChallanCreatePage,ChallanDetailPage}.tsx
│   ├── payments/{PaymentListPage,PaymentCreatePage}.tsx
│   ├── expenses/ExpenseListPage.tsx
│   ├── income/OtherIncomeListPage.tsx
│   ├── settings/{CompanySettingsPage,StaffListPage,CategoriesSettingsPage}.tsx
│   └── system/{ForbiddenPage,NotFoundPage}.tsx
├── routes/                     # (new)
│   ├── AppRouter.tsx           # createBrowserRouter, lazy pages
│   ├── ProtectedRoute.tsx      # session gate (needs auth)
│   └── RoleRoute.tsx           # admin-only gate
├── schemas/                    # (new) zod schemas, one per form (customer, product, invoice, ...)
├── store/
│   ├── api/
│   │   ├── baseApi.ts          # fetchBaseQuery (credentials, CSRF header, 401 handling), tagTypes
│   │   ├── authApi.ts  staffApi.ts  companyApi.ts  customersApi.ts  productsApi.ts
│   │   ├── stockApi.ts  invoicesApi.ts  challansApi.ts  paymentsApi.ts
│   │   ├── expensesApi.ts  incomeApi.ts  dashboardApi.ts
│   ├── slice/
│   │   ├── authSlice.ts        # user, status ('idle'|'loading'|'authenticated'|'unauthenticated')
│   │   └── uiSlice.ts          # snackbar queue, sidebar open
│   ├── hooks.ts                # typed useAppDispatch / useAppSelector
│   └── index.ts                # configureStore (+ setupListeners)
├── types/
│   ├── api/                    # DTOs per domain: auth, staff, company, customer, product, stock,
│   │                           # invoice, challan, payment, expense, income, dashboard, common
│   └── index.ts
├── utils/                      # (new) pure, tested helpers
│   ├── money.ts                # add, sub, sum, compare, isZero, toFixed2 (Decimal-backed)
│   ├── format.ts               # formatCurrency (INR), formatQuantity, formatDate, formatDateTime
│   ├── date.ts                 # toApiDate(dayjs), today(), isValidRange
│   ├── apiError.ts             # parseApiError(unknown) → ApiError; type guards
│   ├── download.ts             # saveBlob, openBlobInNewTab (+ revokeObjectURL)
│   ├── query.ts                # buildQueryParams (drop empty values)
│   ├── csrf.ts                 # readCsrfToken from cookie
│   ├── id.ts                   # generateClientToken (crypto.randomUUID)
│   └── validators.ts           # isValidGstin, isValidPhone
├── App.tsx                     # providers: Redux, Theme, LocalizationProvider, Router, SnackbarHost
├── main.tsx
├── index.css  App.css
└── theme.ts                    # MUI theme (palette, typography, component overrides)
.env  .env.example              # VITE_API_BASE_URL (and nothing secret)
netlify.toml                    # SPA fallback + /api proxy
```

---

## 4. Core Architecture Decisions

### 4.1 `baseApi.ts` (RTK Query)
- `fetchBaseQuery({ baseUrl: config.apiBaseUrl, credentials: 'include' })`.
- `prepareHeaders`: for non-`GET/HEAD/OPTIONS`, attach `X-CSRFToken` from `utils/csrf.ts`. **Do not** force `Content-Type` (needed so `FormData` for the company logo gets a proper multipart boundary).
- **CSRF bootstrap:** `authApi.getCsrf` is called once at app boot, *before* `getMe` and before any login/mutation. If a mutation returns 403 with a CSRF failure, refetch CSRF once and retry.
- **401 handling wrapper:** on `NOT_AUTHENTICATED`, dispatch `authSlice.sessionExpired`, reset API state (`baseApi.util.resetApiState()`), and let `ProtectedRoute` redirect to `/login`. Exclude the login call itself from this logic.
- **Blob endpoints** (`/document/`, `/export/`): `query` returns `{ url, responseHandler: (r) => r.blob() }`; consumed through `useFileDownload` + `utils/download.ts`.
- **`tagTypes`** (constants): `Me, Staff, Company, Customer, CustomerStatement, OpenInvoices, Product, Unit, StockMovement, Invoice, AwaitingDispatch, Challan, Payment, Expense, ExpenseCategory, Income, IncomeCategory, Dashboard`.

### 4.2 Cache invalidation matrix
| Mutation | Invalidates |
|---|---|
| login / logout | reset all (logout) |
| create/update customer | `Customer` |
| create/update product, stock-in, adjust | `Product`, `StockMovement`, `Dashboard` |
| create/update draft invoice | `Invoice` |
| **issue invoice** | `Invoice`, `Product`, `StockMovement`, `OpenInvoices`, `CustomerStatement`, `AwaitingDispatch`, `Dashboard` |
| create challan | `Challan`, `AwaitingDispatch`, `Dashboard` |
| record payment | `Payment`, `OpenInvoices`, `Invoice`, `CustomerStatement`, `Dashboard` |
| create expense / income (+category) | `Expense`/`Income` (+ category tag), `Dashboard` |
| update company | `Company` |
| staff create/update/set-password | `Staff` |

### 4.3 Error model (`utils/apiError.ts`)
```ts
interface ApiError { code: ApiErrorCode | string; detail: string; fieldErrors: Record<string, string[]>; status?: number }
```
- `parseApiError(error: unknown): ApiError` handles RTK `FetchBaseQueryError`, `SerializedError`, and network failures with a safe fallback message from `constants/messages.ts`.
- `useApiFormErrors(setError)` maps `fieldErrors` → form fields; leftover `detail` is shown via `ApiErrorAlert` / snackbar.
- Code-specific UX: `INSUFFICIENT_STOCK` (alert on invoice issue, stay on page), `OVER_DISPATCH` (highlight challan line), `OVER_ALLOCATION` (allocation table banner), `INVALID_DATE_RANGE` (filter-bar error), `THROTTLED` (login: "Too many attempts, wait a minute" + disable submit briefly), `PERMISSION_DENIED` (redirect to Forbidden/hide action).

### 4.4 Auth & routing
1. App boot → `getCsrf` → `getMe`. While pending render `LoadingScreen` (no flash of login).
2. `200` → store user in `authSlice` → render shell. `401` → `/login`.
3. `ProtectedRoute` guards the shell; `RoleRoute roles={[ROLE.ADMIN]}` guards Staff, Company edit, and Category-creation UI. Sidebar items filtered by role from `constants/navigation.ts`.
4. After login redirect to the originally requested URL (stored in router state, not storage).

### 4.5 Lists (shared pattern)
- `usePaginationParams` keeps `page`, `page_size`, `search` and filters in the URL (shareable, back-button safe). Search debounced via `useDebounce`.
- `DataTable<T>` is generic and typed: `columns: Column<T>[]`, loading skeleton, empty state, error state, server pagination (`count`, `page`, `pageSize`).
- Date-range filters validated with `utils/date.isValidRange` before the request is fired.

### 4.6 Forms (shared pattern)
- zod schema in `src/schemas/*` → `useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema) })`.
- Form field values are strings (money/qty stay strings). The form → request mapper is a pure function (testable) that converts empty optionals to `undefined`.
- Dialog forms use `FormDialog`; page forms use `SectionCard` + sticky action bar.
- Prevent double submit: disable while `isLoading`; dirty-form navigation guard on long forms (invoice).

### 4.7 Files & PDFs
`useFileDownload({ trigger, filename, mode: 'open' | 'save' })`: calls the lazy query, creates object URL, opens/saves, **revokes the URL** after use, surfaces errors through the snackbar. Used by invoice PDF, challan PDF, expense/income `.xlsx` export.

---

## 5. Screen Inventory & Routes

`ROUTES` lives in `constants/routes.ts`; never type a path string in a component.

| # | Route | Page | Access | Key API |
|---|---|---|---|---|
| 1 | `/login` | LoginPage | Public | csrf, login |
| 2 | `/` → `/dashboard` | DashboardPage | Auth | `GET /dashboard/` |
| 3 | `/customers` | CustomerListPage | Auth | `GET /customers/` |
| 4 | `/customers/new`, `/customers/:id/edit` | CustomerFormPage | Auth | create / get / patch |
| 5 | `/customers/:id` | CustomerDetailPage (tabs: Overview · Open Invoices · Statement) | Auth | detail, open-invoices, statement |
| 6 | `/products` | ProductListPage | Auth | `GET /products/`, units |
| 7 | `/products/new`, `/products/:id/edit` | ProductFormPage | Auth | create / patch |
| 8 | `/products/:id` | ProductDetailPage (stock-in, adjust, movement history) | Auth | stock-in, adjust, movements |
| 9 | `/inventory/movements` | StockMovementsPage | Auth | `GET /stock-movements/` |
| 10 | `/invoices` | InvoiceListPage | Auth | `GET /invoices/` |
| 11 | `/invoices/new` | InvoiceCreatePage | Auth | calculate, create |
| 12 | `/invoices/:id/edit` | InvoiceEditPage (DRAFT only) | Auth | get, calculate, patch |
| 13 | `/invoices/:id` | InvoiceDetailPage | Auth | get, issue, document, awaiting-dispatch |
| 14 | `/challans` | ChallanListPage | Auth | `GET /challans/` |
| 15 | `/challans/new?invoice=:id` | ChallanCreatePage | Auth | awaiting-dispatch, create |
| 16 | `/challans/:id` | ChallanDetailPage | Auth | detail, document |
| 17 | `/payments` | PaymentListPage | Auth | `GET /payments/` |
| 18 | `/payments/new` | PaymentCreatePage | Auth | open-invoices, create |
| 19 | `/expenses` | ExpenseListPage (+ create dialog, export) | Auth | expenses, categories, export |
| 20 | `/other-income` | OtherIncomeListPage (+ create dialog, export) | Auth | other-income, categories, export |
| 21 | `/settings/company` | CompanySettingsPage | View: Auth · Edit: **Admin** | company get/patch |
| 22 | `/settings/staff` | StaffListPage (+ create/edit/set-password dialogs) | **Admin** | staff APIs |
| 23 | `/settings/categories` | CategoriesSettingsPage (expense & income categories) | View: Auth · Create: **Admin** | categories |
| 24 | `/forbidden`, `*` | ForbiddenPage, NotFoundPage | n/a | n/a |

---

## 6. Phased Build Plan

> Build **one phase at a time**. At the end of each phase: `tsc --noEmit`, `eslint`, tests, and the **acceptance checklist** must pass before moving on. Each phase lists the exact steps in order.

### Phase 0: Foundation (no screens yet)
**Steps**
1. Install deps: `@mui/material @mui/icons-material @emotion/react @emotion/styled @mui/x-date-pickers dayjs @reduxjs/toolkit react-redux react-router-dom react-hook-form zod @hookform/resolvers decimal.js` + dev: `vitest @testing-library/react @testing-library/jest-dom msw prettier`.
2. `tsconfig`: enable strict flags from §2; add path alias `@/* → src/*` (Vite + TS).
3. `.env.example`: `VITE_API_BASE_URL=/api`. Add `src/constants/config.ts` (validates the var, throws on missing).
4. Create `constants/*` (routes, enums + label maps, apiErrorCodes, messages, pagination, validation).
5. Create `types/api/common.ts` (`Paginated<T>`, `ApiError`, `DateRangeParams`, `PaginationParams`) and all enum types derived from `constants/enums.ts`.
6. Create all `utils/*` with unit tests (money, format, date, apiError, query, csrf, validators, download, id).
7. `theme.ts` (palette, typography, shape, component defaults such as `TextField size="small"`, `Button disableElevation`).
8. `store/`: `baseApi.ts`, `authSlice`, `uiSlice`, `hooks.ts`, `index.ts`.
9. Build shared components: `common/*`, `form/*`, `data-display/DataTable`, `feedback/*`, `layout/*`; hooks listed in §3.
10. `App.tsx` providers + `routes/AppRouter.tsx` skeleton + `ProtectedRoute`/`RoleRoute`; `netlify.toml` and Vite dev proxy (see §9).

**Acceptance:** app boots; theme applied; snackbar demo works; `parseApiError` & money utils tested; no `any`/`null` lint errors.

### Phase 1: Authentication & App Shell
**Endpoints:** `GET /auth/csrf/`, `POST /auth/login/`, `POST /auth/logout/`, `GET /auth/me/`
**Steps**
1. `types/api/auth.ts`, `store/api/authApi.ts` (`useGetCsrfQuery`, `useLoginMutation`, `useLogoutMutation`, `useGetMeQuery`).
2. Boot sequence in `App.tsx`/`AuthBootstrap` (csrf → me → populate `authSlice`).
3. `LoginPage` (zod: username/password required) inside `AuthLayout`; handle `401/400` invalid credentials and `THROTTLED`.
4. `AppShell` (Topbar with user menu + logout, responsive Sidebar from `constants/navigation.ts` filtered by role), breadcrumbs via `PageHeader`.
5. Redirect logic (post-login return URL, unauthenticated → `/login`, authenticated visiting `/login` → dashboard).
6. Forbidden and NotFound pages.

**Acceptance:** reload keeps session; logout clears cache; staff users don't see admin nav; expired session redirects to login.

### Phase 2: Company Settings
**Endpoints:** `GET/PATCH /company/`
**Steps**
1. `companyApi.ts` (PATCH accepts `FormData`; JSON when no logo).
2. `CompanyProfileForm` + `LogoUploader` (PNG/JPG ≤ 2 MB client precheck from `constants/validation.ts`; preview).
3. GSTIN validation (15-char Indian GSTIN regex), phone/email validation.
4. Read-only view for STAFF, editable for ADMIN. Show `business_name` + logo in Topbar/Sidebar.

**Acceptance:** admin can update profile + logo; staff sees read-only; server field errors appear under fields.

### Phase 3: Staff Management (Admin)
**Endpoints:** `GET/POST /staff/`, `PATCH /staff/{id}/`, `POST /staff/{id}/set-password/`
**Steps**
1. `staffApi.ts`, `types/api/staff.ts`.
2. `StaffListPage`: filters `search`, `is_active`, `role`; table with role chip, active switch (PATCH `is_active` with confirm dialog).
3. `StaffForm` dialog (create: username, password, confirm_password, full_name, phone, email, role; edit: full_name, phone, email, role, is_active). Password-match validation in zod.
4. `SetPasswordDialog` (`new_password`, `confirm_password`).
5. Guard with `RoleRoute`; prevent admin from deactivating own account in UI.

**Acceptance:** all four endpoints wired; STAFF hitting the URL → Forbidden.

### Phase 4: Customers
**Endpoints:** list/create/detail/patch, `open-invoices`, `statement`
**Steps**
1. `customersApi.ts`, types (`Customer`, `CustomerOpenInvoice`, `CustomerStatement`, `StatementEntry`).
2. `CustomerListPage`: search (name/code/phone), `is_active` filter, pagination; row → detail.
3. `CustomerForm` (name, phone 10–15 digits, GSTIN optional, state, billing_address); `code` is **read-only/auto-generated**, never sent.
4. `CustomerDetailPage` tabs: Overview (+ deactivate/activate), **Open Invoices** (`OpenInvoicesTable`, shows `balance_due`), **Statement** (date range filter, totals cards, ledger table with debit/credit/running balance; `INVALID_DATE_RANGE` handled).
5. `CustomerPicker` (async Autocomplete, debounced search, active only) reused by invoice/payment/challan/expense filters.

**Acceptance:** CRUD works; statement filters; picker reused in later phases.

### Phase 5: Products & Inventory
**Endpoints:** units, products list/create/patch, stock-in, adjust, stock-movements
**Steps**
1. `productsApi.ts`, `stockApi.ts`, types (`Product`, `Unit`, `StockMovement`).
2. `ProductListPage`: search, `item_type`, `is_active`, `low_stock` toggle; `StockBadge` uses `is_low_stock`; SERVICE rows show "N/A" for stock.
3. `ProductForm`: `item_type` drives conditional fields. **If `SERVICE`: hide/omit `opening_stock` and `reorder_level`** (backend rejects them). `opening_stock` only on create; `current_stock`/`opening_stock` not editable on edit. Blank `code` = auto-generate.
4. `ProductDetailPage`: summary, `StockInDialog` (`quantity`, `reason`), `AdjustStockDialog` (`quantity_change` signed, `reason` **required**, prevents result < 0 message from server), movement history table filtered by product.
5. `StockMovementsPage`: filters `product`, `from`, `to`; movement-type chips; link to invoice when present.
6. `ProductPicker` (async autocomplete, shows code, unit, stock, rate default) reused by invoice form.

**Acceptance:** service vs goods rules enforced; stock actions refresh product and ledger.

### Phase 6: Invoicing (core)
**Endpoints:** calculate, list, create, patch, issue, document (PDF), awaiting-dispatch
**Steps**
1. `invoicesApi.ts`, types (`Invoice`, `InvoiceItem`, `InvoiceCalculation`, `CalculationLine`, `AwaitingDispatchItem`). **Confirm the full invoice-detail shape with backend** (see §10).
2. `InvoiceListPage`: filters `status`, `customer`, `from`, `to`; status chip; row actions (view, PDF).
3. `InvoiceForm` + `InvoiceLineEditor`:
   - Customer picker, invoice date, notes.
   - Line rows: ProductPicker, quantity (3 dp), rate (2 dp, defaults to `selling_price`), remove row, add row.
   - **Live totals:** debounced `POST /invoices/calculate/` (note: this endpoint uses `customer_id` / `product_id`, while create/patch use `customer` / `product`; map in a pure mapper). Render `InvoiceTotalsPanel` (subtotal, CGST, SGST, total tax, round-off, grand total) strictly from the response. Show per-line GST from `lines`.
   - Skip calling when no customer or no valid lines; cancel stale requests.
4. `InvoiceCreatePage` → `POST /invoices/` → navigate to detail (status `DRAFT`).
5. `InvoiceEditPage` (guard: only `DRAFT`; `ISSUED` → redirect to detail). PATCH replaces the full `items` list.
6. `InvoiceDetailPage` (`InvoiceActions`):
   - **DRAFT:** Edit, Issue Invoice (confirm dialog explaining immutability + stock deduction), PDF preview (watermarked).
   - **ISSUED:** read-only, Print PDF, Generate Delivery Challan (→ `/challans/new?invoice=:id`), Awaiting Dispatch panel (`remaining_quantity`), Record Payment shortcut.
   - Handle `INSUFFICIENT_STOCK` with an alert that shows `detail`, with no state change.
7. PDF via `useFileDownload` (`mode: 'open'`).

**Acceptance:** totals always match the backend; ISSUED invoices cannot be edited from UI; caches refresh across product/dashboard after issuing.

### Phase 7: Delivery Challans
**Endpoints:** list, create, detail, document
**Steps**
1. `challansApi.ts`, types (`Challan`, `ChallanItem`). **Confirm list/detail shapes** (§10).
2. `ChallanListPage`: filters `invoice`, `customer`, `from`, `to`.
3. `ChallanCreatePage`: requires `invoice` (query param or picker limited to ISSUED); loads `awaiting-dispatch`; `DispatchLinesTable` prefilled with `remaining_quantity` per line; qty input capped (client check using Decimal) with `OVER_DISPATCH` server fallback; fields `delivery_date`, `delivered_by`, `received_by`. Omit zero-qty lines.
4. `ChallanDetailPage` with PDF button.

**Acceptance:** cannot dispatch more than remaining; invoice detail awaiting-dispatch refreshes.

### Phase 8: Payments & Allocations
**Endpoints:** list, create (+ customer `open-invoices`)
**Steps**
1. `paymentsApi.ts`, types (`Payment`, `PaymentAllocation`, `CreatePaymentRequest`). **Confirm payment list/detail shape** (§10).
2. `PaymentListPage`: filters `customer`, `from`, `to`; shows allocations.
3. `PaymentCreatePage` → `PaymentForm`:
   - Customer picker → loads `open-invoices` → `AllocationTable` (invoice no., date, total, paid, balance_due, allocate amount input).
   - Fields: `payment_date`, `amount`, `method` (**use the `PaymentMethod` enum only**, see §10), `reference`, `note`.
   - "Auto-allocate (oldest first)" helper in `utils/money.ts`/`utils/allocation.ts`; live "Unallocated: ₹x" indicator; validation: sum(allocations) **exactly equals** `amount`; each allocation ≤ `balance_due`; amount > 0.
   - **Idempotency:** `client_token = generateClientToken()` created once per form instance (`useRef`/`useState` initializer) and sent with every retry; regenerate only after a successful save or form reset.
   - Handle `OVER_ALLOCATION`.
4. After success: navigate to list or customer statement, with snackbar.

**Acceptance:** double-click or retry cannot create duplicate payments; open invoices update.

### Phase 9: Expenses & Other Income
**Endpoints:** expense-categories, expenses (list/create/export), income-categories, other-income (list/create/export)
**Steps**
1. `expensesApi.ts`, `incomeApi.ts`, types.
2. `ExpenseListPage`: filters `search`, `category`, `from`, `to`; table + **`total_amount` summary card** (sum of all filtered pages, from server, not computed client-side); "Add Expense" `FormDialog`; **Export .xlsx** button using the same date range.
3. `OtherIncomeListPage` mirrors expenses (`received_from` instead of `paid_to`). Build both on a shared generic list layout where it reduces duplication.
4. `CategoriesSettingsPage` (or inline "Add category" in dialogs) with `RoleGate` for Admin-only create.
5. `payment_method` selects use the shared `PaymentMethod` options.

**Acceptance:** filtered totals and exports respect filters; staff cannot create categories.

### Phase 10: Executive Dashboard
**Endpoint:** `GET /dashboard/`
**Steps**
1. `dashboardApi.ts`, types (`DashboardSummary`, `RecentInvoice`, `LowStockProduct`).
2. `DashboardPage`: `KpiGrid` of `StatCard`s (today sales, month sales + invoice count, payments received, outstanding, month expenses, other income, open challans, stock summary with low-stock count), `RecentInvoicesCard`, `LowStockCard` (links to product / filtered list), "as of" date.
3. Skeletons for loading, refetch on window focus (`refetchOnFocus`) and after relevant mutations (via tags).

**Acceptance:** all figures from the API shown formatted; quick links navigate correctly.

### Phase 11: Hardening & Delivery
**Steps**
1. Route-level code splitting (`React.lazy` + Suspense fallback).
2. Global `ErrorBoundary`, 404/403 polish, offline/network-error messaging.
3. Accessibility pass (labels, focus management in dialogs, color contrast).
4. Tests: utils (100%), zod schemas, `parseApiError`, allocation logic, invoice mapper, plus RTL flows for Login, Invoice create→issue, Payment allocation (MSW).
5. `.github/workflows/ci.yml`: install → lint → `tsc --noEmit` → test → build.
6. README: setup, env vars, scripts, folder structure, contribution rules.

---

## 7. Shared Component Catalogue (build once, reuse everywhere)

| Component | Purpose | Used in |
|---|---|---|
| `PageHeader` | Title, breadcrumbs, primary action slot | All pages |
| `DataTable<T>` | Typed, paginated table with loading/empty/error | All lists |
| `FilterBar` | Search + selects + date range | All lists |
| `SearchField` | Debounced search input | Lists, pickers |
| `StatCard` | KPI tile | Dashboard, statement, expenses |
| `StatusChip` | Maps enum → label + color via constants | Invoice, product, staff, movement |
| `MoneyText` / `DateText` | Consistent formatting (uses utils) | Everywhere |
| `FormDialog` | Dialog with form, submit, cancel, pending state | Stock dialogs, expense, staff, category |
| `ConfirmDialog` | Destructive/irreversible confirmation | Issue invoice, deactivate |
| `ApiErrorAlert` | Renders `ApiError.detail` + code-specific hint | Forms |
| `RoleGate` | Hide children unless role allowed | Buttons/sections |
| `FileDownloadButton` | PDF/XLSX download with loading state | Invoice, challan, exports |
| `Form*` fields | RHF-bound MUI inputs (money/qty masked string inputs) | All forms |
| `CustomerPicker` / `ProductPicker` | Async autocomplete | Invoice, payment, challan, filters |

Add to this table when a new shared component is created.

---

## 8. Type & Constant Conventions (examples)

```ts
// constants/enums.ts
export const INVOICE_STATUS = { DRAFT: 'DRAFT', ISSUED: 'ISSUED' } as const;
export type InvoiceStatus = (typeof INVOICE_STATUS)[keyof typeof INVOICE_STATUS];
export const INVOICE_STATUS_LABEL: Record<InvoiceStatus, string> = { DRAFT: 'Draft', ISSUED: 'Issued' };

// types/api/common.ts
export interface Paginated<T> { count: number; next: string | null; previous: string | null; results: T[] } // null allowed: contract returns JSON null
export type MoneyString = string;      // "1250.00"
export type QuantityString = string;   // "10.500"
export type IsoDate = string;          // "YYYY-MM-DD"
export type IsoDateTime = string;      // "2026-11-20T12:00:00Z"

// constants/routes.ts
export const ROUTES = {
  login: '/login',
  dashboard: '/dashboard',
  customers: { list: '/customers', new: '/customers/new', detail: (id: number) => `/customers/${id}` },
  // ...
} as const;
```

---

## 9. Deployment & Environment Notes (important)

- **Session cookies + CSRF require same-site requests.** `document.cookie` can only read `csrftoken` if the cookie belongs to the page's own origin. If the frontend (Netlify) and Django live on different domains, the CSRF cookie won't be readable and `SameSite` rules may block the session cookie.
  **Solution:** keep the browser talking to the *same origin* and proxy `/api/*` to the backend:
  - **Dev:** Vite `server.proxy: { '/api': 'http://localhost:8000' }` (+ `/media`).
  - **Prod:** `netlify.toml` → `[[redirects]] from="/api/*" to="https://<backend-host>/api/:splat" status=200 force=true`, plus SPA fallback `/* → /index.html 200`.
  - Backend must list the frontend origin in `CSRF_TRUSTED_ORIGINS` and use secure cookies in prod.
- `VITE_API_BASE_URL=/api` for both environments; never commit real backend URLs into code.
- Logo/media URLs from the API may be absolute backend URLs; render them as-is.

---

## 10. Contract Gaps & Questions to Resolve Before/While Building

Do **not** invent shapes for these. Ask the backend owner (or inspect the serializers) and record the answer in `types/api/*`.

1. **Full Invoice object** (create/patch/issue response and detail `GET /invoices/{id}/`): the contract says "full invoice object" but does not list the fields (items, snapshots, totals, `total_paid`/`balance_due`, `payment_status`?). Also, no `GET /invoices/{id}/` is explicitly documented; confirm it exists.
2. **Challan object** (list/detail fields) and **Payment object** (list fields, allocation shape) are not shown.
3. **`method: "NEFT"`** appears in the payment example, but the `PaymentMethod` enum is `CASH | BANK_TRANSFER | UPI | CHEQUE`. The frontend will use the enum only; confirm `NEFT` is not valid.
4. **`recent_invoices[].payment_status: "ISSUED"`** on the dashboard looks like a status, not a payment status. Confirm the possible values (e.g. `PAID/PARTIAL/UNPAID`?).
5. **Inconsistent request keys:** `calculate` uses `customer_id`/`product_id`, while create uses `customer`/`product`. Handled by a mapper, but confirm it's intentional.
6. **Dashboard access** is "Authenticated (or Public)". The frontend treats it as authenticated.
7. **No delete endpoints** (customers, products, invoices, expenses). The UI offers deactivate (`is_active`) only. Confirm draft-invoice deletion is not needed.
8. **Expense/income edit** endpoints (`PATCH`) are not in the contract; V1 UI is create + list + export only.
9. **Categories list** endpoints: confirm whether they're paginated (assume `Paginated<T>` per "every list endpoint").
10. **Units**: read-only (no create endpoint); products reference `unit` by id.
11. **Pagination `page_size` max 100**: pickers that need all items (units, categories) should request `page_size=100`.

---

## 11. Definition of Done (per phase/PR)

- [ ] `tsc --noEmit` passes under strict flags; **zero** `any`, `!`, `@ts-ignore`, app-level `null`.
- [ ] ESLint + Prettier clean.
- [ ] No hardcoded routes/labels/messages/error codes/page sizes; all in `constants/`.
- [ ] No duplicated logic; shared pieces extracted to `components/common|form|data-display`, `hooks/`, or `utils/`.
- [ ] Only MUI components & theme tokens used for UI.
- [ ] All API access via RTK Query endpoints with correct tags/invalidations; no `fetch`/axios in components.
- [ ] Loading, empty, error, and success states implemented; server `field_errors` shown on fields.
- [ ] Role checks applied (route guard **and** UI gating).
- [ ] Money/qty handled as strings with `utils/money.ts` + `utils/format.ts`.
- [ ] Unit tests added for new utils/schemas/mappers; key flows covered for the phase.
- [ ] Acceptance checklist of the phase verified manually against the running backend.

---

## 12. Instructions for the LLM / Coding Agent

1. Load `FRONTEND_SKILL.md`, then this plan, then the relevant section of `API_CONTRACT.md`.
2. State which **phase** you are implementing and list the files you will create/modify before writing code.
3. Check existing components/hooks/utils/constants for reuse **first**; extend rather than duplicate.
4. Implement in this order per feature: `types` → `constants` (if new) → `utils` (if new) → `schemas` → `store/api` → shared/feature `components` → `pages` → `routes`/`navigation`.
5. Never guess an undocumented API shape; use §10 and ask.
6. After coding, self-review against §11 and report any deviations or open questions.
7. Keep pages thin: a page wires route params, data hooks, and components; nothing else.
