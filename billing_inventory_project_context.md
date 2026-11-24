# Billing & Inventory Management System - Project Context

Read this file first, in every session. It explains what the app is, how the business flows through it, and which rules must never break. It is the shared background for all phases. The build instructions for each phase are in the backend phase plan, which is attached separately with each phase prompt (Section 1).

---

## 1. How this file is used

This file is the project knowledge base. It is available in every session and is read first. It contains everything needed to understand the app: its purpose, terms, data, flows, rules and status. The earlier client-reviewed plans and the clickable prototype have already been folded into this file and into the phase plan. They are not part of the knowledge base, so do not look for them.

Two other documents are used together with this file:

| Document | Role | How it is provided |
|---|---|---|
| `billing_inventory_project_context.md` (this file) | What the app is, how it flows, which rules never break, current status | Always available. Read first. |
| `billing_inventory_v1_backend_phase_plan.md` | How to build the backend, one phase at a time | Attached with each phase prompt |
| Frontend phase plan | How to build the frontend | Written later, after the backend API contract exists |

Order of authority when something is unclear:

1. The client's written decisions (recorded in Section 13).
2. This file, for what the app is and which rules must never break.
3. The backend phase plan, for how to build each phase.

If this file and the phase plan disagree, stop and ask. If neither covers a point, stop and ask. Do not guess.

---

## 2. What the app is

A web application for a business that sells products and needs everyday billing and stock control. It is used by the owner and a few staff members. Everything is in Indian rupees (INR), dates are shown as DD/MM/YYYY, and the business timezone is Asia/Kolkata.

The app lets the business:

- Keep a list of customers and a catalogue of products, with stock counted for physical goods.
- Create invoices, in the exact format the client supplies, and issue them. Issuing an invoice reduces stock.
- Record payments from customers and see how much each customer still owes.
- Record deliveries (delivery challans) of goods against invoices, including partial deliveries.
- Record expenses and other income, and download either one as an Excel file for a date range.
- See a small dashboard of the business's current numbers.
- Register staff who can sign in.

It is not an ERP or an accounting system. Keep it small and reliable. Anything not listed above is out of scope unless the client approves it (see Section 10).

---

## 3. Users

- Admin (the owner): can do everything, including Settings and Staff.
- Staff: signs in and uses the day-to-day modules (customers, products, invoices, payments, challans, expenses, other income, dashboard).
- Only two roles. No permission matrix. All access rules are enforced by the backend.

---

## 4. Glossary

| Term | Meaning |
|---|---|
| Customer | A person or business the company sells to. Registered once, reused on every invoice. |
| Product | An item in the catalogue. Has an item type, unit, selling price, optional HSN/SAC and GST rate. |
| Item type | `GOODS`, `GOODS_HARDWARE` (shown as Goods (Hardware)), or `SERVICE`. |
| Stock-tracked | Goods and Goods (Hardware). Their stock is counted. Service is never counted. |
| Stock movement | A record of every change to a product's stock: opening, stock-in, adjustment, sale. |
| Opening stock | The quantity entered when a goods product is first created. |
| Stock-in | Manually adding received stock. |
| Adjustment | Manually correcting stock up or down, with a reason. |
| Draft invoice | An invoice being prepared. Changes nothing in stock. Can be edited. |
| Issued invoice | A finished invoice. Deducted stock once. Cannot be edited. |
| Snapshot | A saved copy of business, customer and product details taken when an invoice is issued, so old invoices never change. |
| Payment | Money received from a customer. |
| Allocation | The part of a payment applied to one invoice. One payment can pay several invoices; one invoice can receive several payments. |
| Balance due | An invoice's total minus the allocations applied to it. |
| Outstanding | The sum of balance due across a customer's issued invoices. |
| Delivery challan | A document recording goods physically dispatched against an issued invoice. Records dispatch only. |
| Remaining quantity | For an invoice line: invoiced quantity minus quantity already on challans. |
| HSN/SAC | Tax classification code for goods (HSN) or services (SAC). |
| GSTIN | The 15-character Indian GST registration number. |
| PENDING DECISION (D1 to D17) | A point the client has not confirmed. The phase plan gives a default until it is answered. |

---

## 5. Modules

| Module (navigation) | Purpose | Key records | Needs |
|---|---|---|---|
| Authentication | Sign in, sign out, current user | User | none |
| Staff (Admin) | Register and manage staff | User | Authentication |
| Settings (Admin) | Business details and logo, used on documents | CompanySettings | Authentication |
| Customers | Customer list and details | Customer | Authentication |
| Products | Catalogue, item types, stock, stock movements | Product, Unit, StockMovement | Authentication |
| Invoices | Draft, issue, document output | Invoice, InvoiceItem | Settings, Customers, Products |
| Payments | Record and allocate payments, balances, statement | Payment, PaymentAllocation | Customers, Invoices |
| Delivery Challan | Record dispatch, delivery status | DeliveryChallan, DeliveryChallanItem | Invoices |
| Expenses | Record expenses, Excel export | Expense, ExpenseCategory | Authentication |
| Other Income | Record other income, Excel export | OtherIncome, IncomeCategory | Authentication |
| Dashboard | Summary numbers | none (reads other modules) | everything above |

Navigation order in the app: Dashboard, Customers, Products, Invoices, Payments, Delivery Challan, Expenses, Other Income, Settings, Staff.

---

## 6. How the data fits together

```text
User (staff) --- creates/issues/records ---> almost every record below

Customer 1 ---- * Invoice 1 ---- * InvoiceItem * ---- 1 Product
Customer 1 ---- * Payment 1 ---- * PaymentAllocation * ---- 1 Invoice
Invoice    1 ---- * DeliveryChallan 1 ---- * DeliveryChallanItem * ---- 1 InvoiceItem
Product    1 ---- * StockMovement * ---- 0..1 Invoice   (a SALE movement points to its invoice)
Product    * ---- 1 Unit
Expense * ---- 1 ExpenseCategory        OtherIncome * ---- 1 IncomeCategory
CompanySettings: one record only
```

What is stored versus derived:

| Stored | Derived (calculated, never typed in) |
|---|---|
| Product current stock (kept in step with its movements) | Low-stock flag |
| Invoice totals (calculated by the backend at save and issue) | Invoice paid amount, balance due, payment status |
| Allocations and payments | Customer outstanding |
| Challans and their items | Remaining quantity per line, invoice delivery status |
| Issued invoice snapshots | Dashboard numbers, statement running balance |

---

## 7. State and status values

Invoice status (stored):

```text
DRAFT --issue--> ISSUED          (no other states in V1: no cancel, no delete of issued invoices)
```

Payment status of an issued invoice (derived):

```text
UNPAID           nothing allocated
PARTIALLY_PAID   some allocated, balance remains
PAID             allocated total covers the invoice total
```

Delivery status of an issued invoice (derived, from challans):

```text
PENDING              nothing dispatched
PARTIALLY_DELIVERED  some goods dispatched, some remaining
DELIVERED            all stock-tracked lines fully dispatched
(none)               invoice has no stock-tracked lines (service only)
```

The three statuses are independent. An invoice can be Issued, Partially Paid and Pending delivery all at once.

---

## 8. The main flows

### 8.1 First-time setup

1. Create the first Admin account with a command (never a hard-coded password).
2. Admin signs in and saves the business details and logo in Settings.
3. Admin registers staff in Staff.
4. Customers are registered. Products are created, each with an item type and (for goods) opening stock.
5. The system is ready for invoicing.

### 8.2 A sale, end to end

```text
Customer exists  ->  Create DRAFT invoice  ->  Review/edit  ->  ISSUE
                                                                  |
                    +---------------------------------------------+
                    | in one transaction:
                    |  - check stock for goods lines (fail whole issue if short)
                    |  - recalculate totals on the backend
                    |  - save business, customer and line snapshots
                    |  - create one SALE stock movement per goods line (none for services)
                    |  - mark ISSUED
                    v
          Record payment(s)  ----------->  balance due, payment status, customer outstanding
          Create challan(s) (separately) ->  remaining quantity, delivery status
```

Step detail:

1. Staff picks a customer (or adds one on the spot).
2. Staff adds lines: product, quantity, rate (defaults to the product price). The backend calculates totals. A preview endpoint lets the screen show them without saving.
3. Staff saves a draft. Nothing changes in stock. No invoice number yet.
4. Staff issues the invoice. If any goods line lacks stock, the whole issue fails and the error lists each short product. Otherwise the invoice is issued and stock is reduced exactly once. Repeating the request changes nothing.
5. The invoice document (PDF) is produced from the saved snapshot, in the client's format.

### 8.3 Payments

1. Staff opens Record Payment, picks the customer, enters amount, date, method (Cash, UPI, Bank transfer, Cheque) and reference.
2. Staff allocates the amount to the customer's open invoices. An allocation cannot exceed an invoice's remaining balance.
3. In the default build (Path A), allocations must add up to the payment amount.
4. Balances, payment statuses and the customer's outstanding update from the allocations.

Example: invoice total 10,000. Payment 1: 4,000 -> Partially Paid, balance 6,000. Payment 2: 6,000 -> Paid, balance 0.

Advance payments (money before an invoice, or more than the invoices) are a pending decision (D11) and are not built until the client confirms.

### 8.4 Delivery

1. Staff opens the Delivery Challan page (the only place challans are created) and picks an issued invoice with goods still to dispatch.
2. For each goods line, staff enters the quantity dispatched now. It cannot exceed the remaining quantity.
3. The challan is saved. Stock does not change (it was already reduced when the invoice was issued).
4. Delivery status updates. Further challans handle the rest.

Example: invoice for 300 kg of steel. Challan 1: 150 kg -> Partially Delivered, 150 remaining. Challan 2: 150 kg -> Delivered.

### 8.5 Stock maintenance

- Opening stock is entered at product creation.
- Stock-in adds received goods. Adjustment corrects stock up or down and needs a reason.
- Every change is a stock movement with a running balance. Stock can never go below zero.

### 8.6 Expenses and other income

1. Staff records an entry: date, category, description, amount, method, party, notes.
2. The list can be filtered by search and by From and To dates, and shows a total for the filtered records.
3. "Export to Excel" downloads a real `.xlsx` file containing only records between From and To (both dates included), with a total row. Expenses and Other Income each export separately.

### 8.7 Dashboard

Read-only summary: today's sales, this month's sales, payments received this month, outstanding, stock summary and low-stock count, expenses this month, other income this month, challans still to dispatch, the last five issued invoices, and the low-stock products. Every figure must equal the total of the records behind it.

---

## 9. Effects of each action (quick reference)

| Action | Changes stock? | Creates stock movement? | Changes money records? | Changes statuses? |
|---|---|---|---|---|
| Save or edit a draft invoice | No | No | No | No |
| Issue an invoice | Yes, once, goods only | Yes, `SALE` per goods line | No | Invoice becomes Issued; payment status Unpaid; delivery status Pending (if goods) |
| Record a payment | No | No | Creates payment and allocations | Payment status and balances change |
| Create a challan | No | No | No | Delivery status changes |
| Stock-in | Yes (increase) | Yes, `STOCK_IN` | No | No |
| Adjustment | Yes (up or down) | Yes, `ADJUSTMENT` | No | No |
| Create product with opening stock | Yes | Yes, `OPENING` | No | No |
| Add expense or other income | No | No | Creates the record | No |
| Change customer, product or business details | No | No | No | Issued invoices are unchanged (snapshots) |

---

## 10. Rules that must never break

1. Money and quantities are decimals, never floating-point. The API sends them as strings.
2. The backend is the only source of truth for totals, stock, balances, statuses and dates. It never trusts figures sent by a client.
3. Stock changes only through the single stock service, and every change leaves a movement. Stock never goes negative.
4. Drafts never touch stock. Issuing deducts stock exactly once, even if the request is repeated or two requests arrive at the same time.
5. Services never have stock and never create stock movements.
6. Challans never change stock.
7. An issued invoice is never edited or deleted. Its details are frozen in snapshots.
8. Issuing an invoice and its stock deductions succeed or fail together (one database transaction).
9. A payment cannot be allocated beyond its amount, and an invoice cannot be allocated beyond its balance.
10. A dispatch cannot exceed the remaining quantity.
11. Excel exports include both boundary dates, exclude everything else, and the total equals the exported rows.
12. Payments, issued invoices, challans and stock movements are never hard-deleted.
13. Every permission is enforced on the backend, not only by hiding buttons.
14. Do not build, and do not suggest silently adding: invoice cancellation or reversal, payment void/refund/receipt, advance or credit handling (until confirmed), challan cancellation, audit log, CSV import, invoice-register export, gapless financial-year numbering, quotations, returns, credit notes, suppliers and purchases, e-invoicing, e-way bills, extra charts. These need written client approval.

---

## 11. Conventions

- Backend: Python, Django, Django REST Framework, PostgreSQL. Business logic in `services.py`, thin views.
- Frontend (later): React, TypeScript, React Router, Redux Toolkit, RTK Query, MUI v5. Built after the API contract is ready.
- Formats: ids are integers; dates `YYYY-MM-DD`; timestamps ISO 8601; money strings with 2 decimals; quantities strings with up to 3 decimals; display currency INR with Indian grouping (12,34,567.00); display dates DD/MM/YYYY.
- Enums (upper case): roles `ADMIN`, `STAFF`; item types `GOODS`, `GOODS_HARDWARE`, `SERVICE`; movement types `OPENING`, `STOCK_IN`, `ADJUSTMENT`, `SALE`; invoice status `DRAFT`, `ISSUED`; payment status `UNPAID`, `PARTIALLY_PAID`, `PAID`; delivery status `PENDING`, `PARTIALLY_DELIVERED`, `DELIVERED`; payment methods `CASH`, `UPI`, `BANK_TRANSFER`, `CHEQUE`.
- Errors: one JSON shape with `code`, `message`, `fields`, `details` (defined in the backend phase plan, Section 3.6).
- Lists: page-number pagination, server-side search and filters.

### Background: the reviewed prototype

The client reviewed a clickable prototype with sample data. It is not part of the knowledge base. The approved screens are described by the flows in Section 8. The prototype also showed features that the final plan holds back until the client approves them: invoice cancel, payment void, refund, receipt, customer credit, challan cancel and an audit log. Do not build them (rule 14 in Section 10). The prototype may be supplied again when the frontend is planned.

---

## 12. Pending client decisions (summary)

The full list, with the default to use until answered, is in the backend phase plan (Section 6). In short:

- The client's invoice sample and layout (D7), invoice numbering (D8), tax/discount/rounding rules (D9). These block only Phase 5B.
- How mistakes on issued invoices are corrected, and whether drafts can be deleted (D10).
- Advance payments (D11), payment void/refund/receipt (D12).
- Challan format and number (D13), challan cancellation (D14).
- Excel export columns (D15), any dashboard change (D16).
- Hosting, file storage, backups (D17).
- Staff details and finer access limits (D2, D3), business detail fields (D4).

---

## 13. Current status (update this as work progresses)

Backend phases (see the backend phase plan):

- [x] Phase 0 - Project foundation  ← completed 2026-11-17
- [x] Phase 1 - Authentication and Staff ← completed 2026-11-17
- [x] Phase 2 - Settings ← completed 2026-11-17
- [x] Phase 3 - Customers ← completed
- [x] Phase 4 - Products and inventory ← completed 2026-11-20
- [x] Phase 5A - Invoice core ← completed 2026-11-20
- [x] Phase 5B - Invoice format, numbering, tax rules, PDF ← completed 2026-11-20 (format & tax rules implemented from client sample `finalinv.pdf`)
- [x] Phase 6 - Payments ← completed 2026-11-20 (D11 Path A, no advances; D12 no void/refund/receipt)
- [x] Phase 7 - Delivery Challan ← completed 2026-11-20 (D13 default fields, challan number = internal id, placeholder PDF; D14 no cancellation/edit/delete)
- [x] Phase 8 - Expenses and export
- [x] Phase 9 - Other Income and export
- [x] Phase 10 - Dashboard
- [x] Phase 11 - Hardening, API contract, staging

Frontend: not started. Plan to be written after the API contract (`openapi.yaml`, `API_NOTES.md`) exists.

Decisions answered so far:
- 2026-11-20: D7 (Sample Invoice) & D9 (Tax treatment & rounding) — Client provided sample PDF (`finalinv.pdf`). GST invoices include CGST/SGST 50/50 split on intra-state, tax summary table, round off to whole rupee, amount in words. Non-GST invoices omit tax columns. Implemented in Phase 5B.

---

## 14. Working agreement for the LLM

- Read this file and the current phase of the phase plan before writing code.
- Work on one phase at a time and stay inside it.
- Do not invent business rules, fields, numbering, tax logic or layouts. If it is not written down, ask.
- Prefer the simplest design that satisfies the written rules.
- When you change existing code, return only the changed files.
- At the end of a phase, give the handoff report and say which items in Section 13 can be ticked.
