### 0.3 Phase handoff report (required at the end of each phase)

**What was implemented:**

Phase 7 of the Billing & Inventory V1 backend — Delivery Challan. All requirements
from the Phase 7 specification have been built and tested.

- Data model: `DeliveryChallan` and `DeliveryChallanItem` models with constraints
  (unique per invoice_item per challan, quantity must be > 0), PROTECT on-delete
  for all FK references, and snapshots inherited from InvoiceItem for historical
  fidelity.
- Derived values: per-invoice-line remaining quantity, invoice `delivery_status`
  (PENDING / PARTIALLY_DELIVERED / DELIVERED / null), computed via annotations
  to avoid N+1 queries.
- Endpoints (all under `/api/`):
  - `GET /api/challans/` — list with filters `?invoice=`, `?customer=`, `?from=`,
    `?to=`
  - `POST /api/challans/` — create a challan transactionally
  - `GET /api/challans/{id}/` — detail with items
  - `GET /api/challans/{id}/document/` — placeholder PDF
  - `GET /api/invoices/{id}/dispatch-summary/` — per-line invoiced/dispatched/remaining
    with `dispatchable` flag; service lines show math remaining but cannot be dispatched
  - `GET /api/invoices/awaiting-dispatch/` — ISSUED invoices with stock-tracked lines
    still remaining
- Models and migrations: `apps/delivery/models.py` and `migrations/0001_initial.py`
  applied to the development database; no stock movements or `current_stock` changes.
- Serializers, views, URL routes, document renderer/template, and filter
  annotations across invoice list/detail and customer open-invoices views.
- Tests: `tests/test_phase7.py` with 13 passing tests covering partial then full
  delivery, over-dispatch rejection, concurrent challans, stock invariants,
  state/item-type rules, list filters, detail/document, and authentication.

**Files and modules created or changed:**

1. `backend/apps/delivery/models.py` — DeliveryChallan, DeliveryChallanItem
   models with constraints and snapshots.
2. `backend/apps/delivery/selectors.py` — `annotate_invoice_delivery()`,
   `annotate_invoice_item_dispatched()`, `invoice_delivery_status()`.
3. `backend/apps/delivery/services.py` — `create_challan()` with `select_for_update()`
   locking in id order, `OverDispatchError` for > remaining quantity, and
   transactional guarantees.
4. `backend/apps/delivery/serializers.py` — `DeliveryChallanCreateSerializer`,
   `DeliveryChallanItemWriteSerializer`, read serializers for list/detail.
5. `backend/apps/delivery/views.py` — `DeliveryChallanListCreateView`,
   `DeliveryChallanDetailView`, `DeliveryChallanDocumentView`.
6. `backend/apps/delivery/urls.py` — `challan-list-create`, `challan-detail`,
   `challan-document` routes.
7. `backend/apps/delivery/document.py` — `render_challan_pdf()` using xhtml2pdf
   from invoice item and business snapshots; placeholder HTML template.
8. `backend/apps/delivery/templates/delivery/challan.html` — plain placeholder
   challan layout rendering business, customer, and item snapshots.
9. `backend/apps/invoices/serializers.py` — `InvoiceDeliveryFieldsMixin` and
   `delivery_status` field on `InvoiceListSerializer` and `InvoiceDetailSerializer`.
10. `backend/apps/invoices/views.py` — `annotate_invoice_delivery()` in list/
    detail querysets; `InvoiceDispatchSummaryView` and
    `InvoiceAwaitingDispatchView`; delivery filter `?delivery_status=`.
11. `backend/apps/invoices/urls.py` — added `dispatch-summary` and
    `awaiting-dispatch` routes; included in `config/urls.py`.
12. `backend/apps/customers/views.py` — `annotate_invoice_delivery()` in
    `CustomerOpenInvoicesView` queryset.
13. `backend/config/urls.py` — registered `include("apps.delivery.urls")`.
14. `backend/apps/delivery/migrations/0001_initial.py` — migration created and
    applied; no pre-existing migration conflicts.
15. `tests/test_phase7.py` — 13 tests (partial→complete delivery, over-dispatch,
    concurrent challans, stock invariants, state/item rules, filters, detail,
    document, authentication).
16. `backend/README.md` — updated test suite listing, Phase 7 completion status.
17. `billing_inventory_project_context.md` — Phase 7 checkbox marked complete;
    D13 and D14 defaults recorded.

**Models and migrations added:**

- `delivery.DeliveryChallan`: id (PK), invoice (FK PROTECT), delivery_date,
  delivered_by, received_by, created_by, created_at.
- `delivery.DeliveryChallanItem`: id (PK), challan (FK PROTECT), invoice_item
  (FK PROTECT), quantity (DecimalField max_digits=12, decimal_places=3).
- Constraints: UniqueConstraint(challan, invoice_item), CheckConstraint
  quantity__gt=0. Meta ordering by invoice_item__line_no, id.

**Endpoints completed (method, path, permission):**

| Method | Path | Who | Purpose |
|---|---|---|---|
| `GET` | `/api/challans/` | Any signed-in user | Paginated list; ?invoice=, ?customer=, ?from=, ?to= |
| `POST` | `/api/challans/` | Any signed-in user | Create a challan against an issued invoice |
| `GET` | `/api/challans/{id}/` | Any signed-in user | Detail with dispatched lines |
| `GET` | `/api/challans/{id}/document/` | Any signed-in user | Printable PDF placeholder |
| `GET` | `/api/invoices/{id}/dispatch-summary/` | Any signed-in user | Per-line invoiced/dispatched/remaining |
| `GET` | `/api/invoices/awaiting-dispatch/` | Any signed-in user | ISSUED invoices with goods remaining |

**Tests added and their results:**

All 13 Phase 7 tests pass. Full test suite: 246 passed, 0 failures (the
pre-existing pytest warning about test DB teardown sessions remains unchanged).

**Manual verification performed:**

- Partial then complete delivery: first challan PENDING → second challan DELIVERED;
  remaining quantities update correctly per line.
- Over-dispatch rejected with 409 OVER_DISPATCH; remaining quantity exposed in
  `details`; second attempt with corrected quantity succeeds.
- Concurrent challans: one succeeds, one rejected with 409; stock unchanged;
  exactly one challan committed.
- Challans never change `current_stock` or create StockMovement records.
- Draft invoice and service-only invoice reject challan creation (409 INVALID_STATE
  or 400 VALIDATION_ERROR).
- Service lines appear in dispatch summary with `dispatchable=False` and show
  mathematical remaining quantity, but cannot be dispatched.
- `?delivery_status=` filter works on invoice list, matching PENDING /
  PARTIALLY_DELIVERED / DELIVERED.
- `?from=` / `?to=` date filters work on challan list.
- `?invoice=` and `?customer=` filters work on challan list.
- PDF document renders from saved snapshots (historical, never changes).

**Known issues and client decisions still required:**

- D13 (challan sample/format): The PDF is a plain placeholder until the client
  supplies the approved format. The layout uses business_snapshot, customer_snapshot,
  and invoice item snapshots; it is designed to be replaced without code changes.
- D14 (challan cancellation/edit/delete): Not built in V1; no endpoints or UI
  for cancelling or editing existing challans. This is a change request for a
  future phase.

**Confirmation that the phase completion gate passes:**

✅ An invoice delivered in several challans shows correct remaining quantities
   and final status (PENDING → PARTIALLY_DELIVERED → DELIVERED).
✅ Stock never changes after challan creation (verified: current_stock identical
   before and after, no StockMovement records created).
✅ Delivery status is derived from annotations; no N+1 queries on list endpoints.
✅ Over-dispatch is rejected with 409 and the exact remaining quantity.
✅ Service lines are rejected; a service-only invoice has null delivery status.
✅ All 13 Phase 7 tests pass; full suite 246 passed.
✅ D13 default (delivery_date, delivered_by, received_by; challan number =
   internal id) implemented per spec.
✅ D14 default (no challan cancellation, edit, or delete) implemented per spec.
✅ Challans never create stock movements or change `current_stock` confirmed.
✅ All Phase 7 endpoints, serializers, views, URL routes, migrations, and tests
   are in place and passing.

---

**Section 0.3 complete.** Phase 7 is complete and ready for the next phase
(Phase 8: Expenses). The project context and handoff report have been updated.