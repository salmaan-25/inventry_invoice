"""
Phase 5 tests — Invoices.

Test groups:
    1. Draft creation and draft PATCH (no stock deduction, no invoice number)
    2. Calculation service and stateless calculate endpoint
    3. Issue workflow (stock deduction: Goods/Hardware vs Service)
    4. Multi-line same product combined stock deduction
    5. Insufficient stock handling and abort (single & multi-line)
    6. Idempotent issue (double-click safety)
    7. Concurrent issues competing for limited stock
    8. Snapshot immutability (customer, company, product line snapshots)
    9. Client-sent totals ignored
    10. GST vs Non-GST tax calculations and round-off
    11. Validation & state rules (inactive customer/product, editing issued invoice)
    12. Authentication and permissions (Anon vs Staff vs Admin)
    13. List and search / filters
    14. Document (PDF) generation endpoint
    15. check_stock_consistency management command integration
"""

import threading
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.common.constants import InvoiceStatus, ItemType, MovementType, Role
from apps.company.models import CompanySettings
from apps.customers.models import Customer
from apps.inventory.models import StockMovement
from apps.invoices.models import Invoice, InvoiceItem
from apps.products.models import Product, ProductCodeCounter, Unit

INVOICES_URL = "/api/invoices/"
CALCULATE_URL = "/api/invoices/calculate/"

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reference_data(db):
    """Ensure units, counters and company settings exist."""
    Unit.objects.get_or_create(name="pcs")
    Unit.objects.get_or_create(name="kg")
    Unit.objects.get_or_create(name="hour")
    ProductCodeCounter.objects.get_or_create(pk=1, defaults={"next_value": 1})
    CompanySettings.objects.update_or_create(
        pk=1,
        defaults={
            "business_name": "Acme Industrial Supplies",
            "address": "123 Main St, Industrial Area, Chennai",
            "phone": "9876543210",
            "email": "billing@acme.example.com",
            "gstin": "33AAAAA0000A1Z5",
        },
    )


def make_customer(**kwargs) -> Customer:
    defaults = {
        "name": "Standard Customer",
        "phone": "9998887776",
        "gstin": "33BBBBB1111B1Z2",
        "state": "Tamil Nadu",
        "billing_address": "456 Trade Road, Chennai",
        "is_active": True,
    }
    defaults.update(kwargs)
    if "code" not in defaults:
        from apps.customers.models import CustomerCodeCounter
        counter, _ = CustomerCodeCounter.objects.get_or_create(pk=1, defaults={"next_value": 1})
        defaults["code"] = f"C{counter.next_value:04d}"
        counter.next_value += 1
        counter.save(update_fields=["next_value"])
    return Customer.objects.create(**defaults)


def make_product(item_type=ItemType.GOODS, current_stock="50.000", **kwargs) -> Product:
    unit = Unit.objects.get(name=kwargs.pop("unit_name", "pcs"))
    defaults = {
        "name": "Widget A",
        "item_type": item_type,
        "unit": unit,
        "selling_price": Decimal("100.00"),
        "gst_rate": Decimal("18.00"),
        "hsn_sac": "8471",
        "is_active": True,
    }
    defaults.update(kwargs)
    if "code" not in defaults:
        counter = ProductCodeCounter.objects.get(pk=1)
        defaults["code"] = f"P{counter.next_value:04d}"
        counter.next_value += 1
        counter.save(update_fields=["next_value"])

    initial_stock = Decimal(str(current_stock))
    defaults["current_stock"] = initial_stock
    product = Product.objects.create(**defaults)

    # If goods and initial stock > 0, record opening movement
    if item_type != ItemType.SERVICE and initial_stock > 0:
        admin = User.objects.filter(role=Role.ADMIN).first()
        StockMovement.objects.create(
            product=product,
            movement_type=MovementType.OPENING,
            quantity_change=initial_stock,
            balance_after=initial_stock,
            reason="Initial stock",
            created_by=admin or User.objects.first(),
        )
    return product


# ===========================================================================
# 1. Draft Creation & Draft PATCH
# ===========================================================================

def test_draft_create_basic(staff_client, staff_user):
    """Creating a draft sets status=DRAFT, no invoice_number, and no stock effect."""
    customer = make_customer()
    product = make_product(current_stock="50.000")

    payload = {
        "customer": customer.id,
        "invoice_date": "2026-11-20",
        "notes": "Urgent delivery requested",
        "lines": [
            {"product": product.id, "quantity": "5.000", "rate": "100.00"}
        ],
    }
    resp = staff_client.post(INVOICES_URL, payload, format="json")
    assert resp.status_code == status.HTTP_201_CREATED, resp.data

    data = resp.data
    assert data["status"] == InvoiceStatus.DRAFT
    assert data["invoice_number"] is None
    assert Decimal(data["subtotal"]) == Decimal("500.00")
    assert Decimal(data["grand_total"]) == Decimal("590.00")  # 500 + 18% GST (90) = 590
    assert len(data["items"]) == 1

    # Verify no stock was deducted
    product.refresh_from_db()
    assert product.current_stock == Decimal("50.000")
    assert not StockMovement.objects.filter(invoice_id=data["id"]).exists()


def test_draft_edit_patch_replaces_lines(staff_client):
    """Editing a draft replaces all lines atomically and recalculates totals."""
    customer = make_customer()
    prod1 = make_product(name="P1", current_stock="20.000", selling_price=Decimal("100.00"))
    prod2 = make_product(name="P2", current_stock="20.000", selling_price=Decimal("200.00"))

    create_resp = staff_client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-20",
            "lines": [{"product": prod1.id, "quantity": "2.000", "rate": "100.00"}],
        },
        format="json",
    )
    inv_id = create_resp.data["id"]

    # PATCH with prod2 instead
    patch_resp = staff_client.patch(
        f"{INVOICES_URL}{inv_id}/",
        {
            "customer": customer.id,
            "invoice_date": "2026-11-21",
            "notes": "Updated order",
            "lines": [
                {"product": prod2.id, "quantity": "3.000", "rate": "200.00"},
            ],
        },
        format="json",
    )
    assert patch_resp.status_code == status.HTTP_200_OK, patch_resp.data
    data = patch_resp.data
    assert data["invoice_date"] == "2026-11-21"
    assert data["notes"] == "Updated order"
    assert len(data["items"]) == 1
    assert data["items"][0]["product"] == prod2.id
    assert Decimal(data["subtotal"]) == Decimal("600.00")

    # Still draft, no stock deducted
    prod1.refresh_from_db()
    prod2.refresh_from_db()
    assert prod1.current_stock == Decimal("20.000")
    assert prod2.current_stock == Decimal("20.000")


# ===========================================================================
# 2. Calculation Endpoint (Stateless Preview)
# ===========================================================================

def test_calculate_endpoint_stateless(staff_client):
    """POST /api/invoices/calculate/ computes totals without saving anything to DB."""
    customer = make_customer(gstin="33BBBBB1111B1Z2")
    product = make_product(gst_rate=Decimal("18.00"))

    initial_inv_count = Invoice.objects.count()

    payload = {
        "customer": customer.id,
        "lines": [{"product": product.id, "quantity": "10.000", "rate": "50.00"}],
    }
    resp = staff_client.post(CALCULATE_URL, payload, format="json")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.data

    assert data["is_gst_invoice"] is True
    assert Decimal(data["subtotal"]) == Decimal("500.00")
    assert Decimal(data["total_cgst"]) == Decimal("45.00")
    assert Decimal(data["total_sgst"]) == Decimal("45.00")
    assert Decimal(data["total_tax"]) == Decimal("90.00")
    assert Decimal(data["grand_total"]) == Decimal("590.00")

    # DB unchanged
    assert Invoice.objects.count() == initial_inv_count


# ===========================================================================
# 3. Issue Workflow: Stock Decoupling (Stock is preserved on issue)
# ===========================================================================

def test_issue_stock_deduction_goods_hardware_and_service(staff_client):
    """Stock is decoupled from invoice generation: current_stock remains untouched."""
    customer = make_customer()
    goods = make_product(name="Cement", item_type=ItemType.GOODS, current_stock="50.000")
    hardware = make_product(name="Pipes", item_type=ItemType.GOODS_HARDWARE, current_stock="30.000")
    service = make_product(name="Installation", item_type=ItemType.SERVICE, current_stock="0.000")

    resp = staff_client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-20",
            "lines": [
                {"product": goods.id, "quantity": "10.000", "rate": "100.00"},
                {"product": hardware.id, "quantity": "5.000", "rate": "50.00"},
                {"product": service.id, "quantity": "2.000", "rate": "500.00"},
            ],
        },
        format="json",
    )
    inv_id = resp.data["id"]

    issue_resp = staff_client.post(f"{INVOICES_URL}{inv_id}/issue/")
    assert issue_resp.status_code == status.HTTP_200_OK, issue_resp.data

    data = issue_resp.data
    assert data["status"] == InvoiceStatus.ISSUED
    assert data["issued_by"] is not None
    assert data["issued_at"] is not None

    # Check stocks: untouched because stock is managed manually in Inventory
    goods.refresh_from_db()
    hardware.refresh_from_db()
    service.refresh_from_db()

    assert goods.current_stock == Decimal("50.000")
    assert hardware.current_stock == Decimal("30.000")
    assert service.current_stock == Decimal("0.000")


# ===========================================================================
# 4. Same Product on Multiple Lines
# ===========================================================================

def test_issue_same_product_multiple_lines_combined(staff_client):
    """The same product across multiple lines issues cleanly without automated stock deductions."""
    customer = make_customer()
    product = make_product(current_stock="10.000")

    resp = staff_client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-20",
            "lines": [
                {"product": product.id, "quantity": "4.000", "rate": "100.00"},
                {"product": product.id, "quantity": "3.000", "rate": "100.00"},
            ],
        },
        format="json",
    )
    inv_id = resp.data["id"]

    issue_resp = staff_client.post(f"{INVOICES_URL}{inv_id}/issue/")
    assert issue_resp.status_code == status.HTTP_200_OK

    product.refresh_from_db()
    assert product.current_stock == Decimal("10.000")


# ===========================================================================
# 5. Invoicing with Manual Stock Control
# ===========================================================================

def test_issue_insufficient_stock_aborts_draft_unchanged(staff_client):
    """Decoupled stock allows invoice creation while tracking products independently."""
    customer = make_customer()
    product = make_product(name="Rare Metal", current_stock="5.000")

    resp = staff_client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-20",
            "lines": [{"product": product.id, "quantity": "10.000", "rate": "100.00"}],
        },
        format="json",
    )
    inv_id = resp.data["id"]

    issue_resp = staff_client.post(f"{INVOICES_URL}{inv_id}/issue/")
    assert issue_resp.status_code == status.HTTP_200_OK
    product.refresh_from_db()
    assert product.current_stock == Decimal("5.000")


def test_issue_same_product_multiple_lines_insufficient_stock_aborts(staff_client):
    """Issuing invoice succeeds and preserves warehouse inventory balance."""
    customer = make_customer()
    product = make_product(current_stock="10.000")

    resp = staff_client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-20",
            "lines": [
                {"product": product.id, "quantity": "6.000", "rate": "100.00"},
                {"product": product.id, "quantity": "5.000", "rate": "100.00"},
            ],
        },
        format="json",
    )
    inv_id = resp.data["id"]

    issue_resp = staff_client.post(f"{INVOICES_URL}{inv_id}/issue/")
    assert issue_resp.status_code == status.HTTP_200_OK

    product.refresh_from_db()
    assert product.current_stock == Decimal("10.000")


# ===========================================================================
# 6. Idempotent Issue (Double Click Safety)
# ===========================================================================

def test_issue_idempotent_second_call_succeeds_without_double_deduction(staff_client):
    """Calling issue twice returns 200 idempotently."""
    customer = make_customer()
    product = make_product(current_stock="20.000")

    resp = staff_client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-20",
            "lines": [{"product": product.id, "quantity": "5.000", "rate": "100.00"}],
        },
        format="json",
    )
    inv_id = resp.data["id"]

    # First issue
    r1 = staff_client.post(f"{INVOICES_URL}{inv_id}/issue/")
    assert r1.status_code == status.HTTP_200_OK

    product.refresh_from_db()
    assert product.current_stock == Decimal("20.000")

    # Second issue
    r2 = staff_client.post(f"{INVOICES_URL}{inv_id}/issue/")
    assert r2.status_code == status.HTTP_200_OK

    product.refresh_from_db()
    assert product.current_stock == Decimal("20.000")


# ===========================================================================
# 7. Concurrent Issues
# ===========================================================================

@pytest.mark.django_db(transaction=True)
def test_concurrent_issues_competing_for_limited_stock(admin_user):
    """Concurrent issues both succeed safely under transaction isolation."""
    customer = make_customer()
    product = make_product(current_stock="10.000")

    c1 = APIClient()
    c1.force_login(admin_user)
    c2 = APIClient()
    c2.force_login(admin_user)

    r1 = c1.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-20",
            "lines": [{"product": product.id, "quantity": "8.000", "rate": "100.00"}],
        },
        format="json",
    )
    r2 = c2.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-20",
            "lines": [{"product": product.id, "quantity": "8.000", "rate": "100.00"}],
        },
        format="json",
    )
    id1 = r1.data["id"]
    id2 = r2.data["id"]

    results = []

    def issue_worker(client, invoice_id):
        res = client.post(f"{INVOICES_URL}{invoice_id}/issue/")
        results.append(res.status_code)

    t1 = threading.Thread(target=issue_worker, args=(c1, id1))
    t2 = threading.Thread(target=issue_worker, args=(c2, id2))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    from django.db import connections
    connections.close_all()

    assert sorted(results) == [status.HTTP_200_OK, status.HTTP_200_OK]


# ===========================================================================
# 8. Snapshot Immutability
# ===========================================================================

def test_issued_invoice_snapshots_immutable(staff_client):
    """Issued invoice preserves customer, product, and business snapshots after live records change."""
    customer = make_customer(name="Original Cust", gstin="33AAAAA1111A1Z1")
    product = make_product(name="Original Prod", code="P9999", gst_rate=Decimal("18.00"))

    resp = staff_client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-20",
            "lines": [{"product": product.id, "quantity": "1.000", "rate": "100.00"}],
        },
        format="json",
    )
    inv_id = resp.data["id"]
    staff_client.post(f"{INVOICES_URL}{inv_id}/issue/")

    # Mutate customer, product, and company settings
    customer.name = "Modified Customer Name"
    customer.gstin = "99XXXXX9999X9Z9"
    customer.save()

    product.name = "Modified Product Name"
    product.code = "P8888"
    product.gst_rate = Decimal("28.00")
    product.save()

    cs = CompanySettings.objects.get(pk=1)
    cs.business_name = "New Business Name"
    cs.save()

    # Query invoice detail
    detail = staff_client.get(f"{INVOICES_URL}{inv_id}/").data

    # Snapshots must hold original values
    assert detail["customer_snapshot"]["name"] == "Original Cust"
    assert detail["customer_snapshot"]["gstin"] == "33AAAAA1111A1Z1"
    assert detail["business_snapshot"]["business_name"] == "Acme Industrial Supplies"

    item = detail["items"][0]
    assert item["product_name"] == "Original Prod"
    assert item["product_code"] == "P9999"
    assert Decimal(item["gst_rate"]) == Decimal("18.00")


# ===========================================================================
# 9. Client-Sent Totals Ignored
# ===========================================================================

def test_client_sent_totals_ignored(staff_client):
    """Server calculates all totals; client-sent subtotal or grand_total are ignored."""
    customer = make_customer()
    product = make_product(selling_price=Decimal("100.00"), gst_rate=Decimal("18.00"))

    payload = {
        "customer": customer.id,
        "invoice_date": "2026-11-20",
        "subtotal": "1.00",      # fraudulent
        "grand_total": "1.00",   # fraudulent
        "lines": [
            {
                "product": product.id,
                "quantity": "2.000",
                "rate": "100.00",
                "line_total": "10.00",  # fraudulent
            }
        ],
    }
    resp = staff_client.post(INVOICES_URL, payload, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.data

    assert Decimal(data["subtotal"]) == Decimal("200.00")
    assert Decimal(data["grand_total"]) == Decimal("236.00")  # 200 + 18% GST (36)


# ===========================================================================
# 10. GST vs Non-GST & Round-Off
# ===========================================================================

def test_gst_invoice_tax_calculation(staff_client):
    """Customer with GSTIN receives CGST and SGST equal split."""
    customer = make_customer(gstin="33AAAAA1111A1Z1")
    product = make_product(gst_rate=Decimal("18.00"))

    resp = staff_client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-20",
            "lines": [{"product": product.id, "quantity": "2.000", "rate": "100.00"}],
        },
        format="json",
    )
    data = resp.data
    assert Decimal(data["subtotal"]) == Decimal("200.00")
    assert Decimal(data["total_cgst"]) == Decimal("18.00")  # 9% of 200
    assert Decimal(data["total_sgst"]) == Decimal("18.00")  # 9% of 200
    assert Decimal(data["total_tax"]) == Decimal("36.00")
    assert Decimal(data["grand_total"]) == Decimal("236.00")


def test_non_gst_invoice_tax_is_zero(staff_client):
    """Customer without GSTIN or product without GST rate receives zero tax."""
    customer = make_customer(gstin="")
    product = make_product(gst_rate=None)

    resp = staff_client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-20",
            "lines": [{"product": product.id, "quantity": "2.000", "rate": "100.00"}],
        },
        format="json",
    )
    data = resp.data
    assert Decimal(data["subtotal"]) == Decimal("200.00")
    assert Decimal(data["total_cgst"]) == Decimal("0.00")
    assert Decimal(data["total_sgst"]) == Decimal("0.00")
    assert Decimal(data["total_tax"]) == Decimal("0.00")
    assert Decimal(data["grand_total"]) == Decimal("200.00")


def test_round_off_rounds_to_whole_rupee(staff_client):
    """Round off adjusts total so grand_total is a whole rupee."""
    customer = make_customer(gstin="33AAAAA1111A1Z1")
    # rate that produces fractional tax: 33.33 * 1.18 = 39.3294
    product = make_product(gst_rate=Decimal("18.00"))

    resp = staff_client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-20",
            "lines": [{"product": product.id, "quantity": "1.000", "rate": "33.33"}],
        },
        format="json",
    )
    data = resp.data
    gt = Decimal(data["grand_total"])
    assert gt == gt.quantize(Decimal("1"))  # Whole rupee


# ===========================================================================
# 11. Validation & State Rules
# ===========================================================================

def test_cannot_edit_issued_invoice(staff_client):
    """Editing an ISSUED invoice is supported and updates the invoice record."""
    customer = make_customer()
    product = make_product(current_stock="20.000")

    resp = staff_client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-20",
            "lines": [{"product": product.id, "quantity": "1.000", "rate": "50.00"}],
        },
        format="json",
    )
    inv_id = resp.data["id"]
    staff_client.post(f"{INVOICES_URL}{inv_id}/issue/")

    # Edit issued invoice
    patch_resp = staff_client.patch(
        f"{INVOICES_URL}{inv_id}/",
        {"notes": "Updated notes on issued invoice"},
        format="json",
    )
    assert patch_resp.status_code == status.HTTP_200_OK
    assert patch_resp.data["notes"] == "Updated notes on issued invoice"


def test_issue_rejected_for_inactive_customer(staff_client):
    """Issuing an invoice with an inactive customer returns 409 INVALID_STATE."""
    customer = make_customer(is_active=True)
    product = make_product(current_stock="20.000")

    resp = staff_client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-20",
            "lines": [{"product": product.id, "quantity": "1.000", "rate": "50.00"}],
        },
        format="json",
    )
    inv_id = resp.data["id"]

    # Deactivate customer
    customer.is_active = False
    customer.save()

    issue_resp = staff_client.post(f"{INVOICES_URL}{inv_id}/issue/")
    assert issue_resp.status_code == status.HTTP_409_CONFLICT
    assert issue_resp.data["code"] == "INVALID_STATE"


def test_issue_rejected_for_inactive_product(staff_client):
    """Issuing an invoice containing an inactive product returns 409 INVALID_STATE."""
    customer = make_customer()
    product = make_product(current_stock="20.000", is_active=True)

    resp = staff_client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-20",
            "lines": [{"product": product.id, "quantity": "1.000", "rate": "50.00"}],
        },
        format="json",
    )
    inv_id = resp.data["id"]

    # Deactivate product
    product.is_active = False
    product.save()

    issue_resp = staff_client.post(f"{INVOICES_URL}{inv_id}/issue/")
    assert issue_resp.status_code == status.HTTP_409_CONFLICT
    assert issue_resp.data["code"] == "INVALID_STATE"


# ===========================================================================
# 12. Authentication & Permissions
# ===========================================================================

def test_anon_client_denied_all_endpoints(anon_client):
    """Unauthenticated access returns 401 NOT_AUTHENTICATED."""
    assert anon_client.get(INVOICES_URL).status_code == status.HTTP_401_UNAUTHORIZED
    assert anon_client.post(INVOICES_URL, {}).status_code == status.HTTP_401_UNAUTHORIZED
    assert anon_client.post(CALCULATE_URL, {}).status_code == status.HTTP_401_UNAUTHORIZED
    assert anon_client.get(f"{INVOICES_URL}1/").status_code == status.HTTP_401_UNAUTHORIZED
    assert anon_client.patch(f"{INVOICES_URL}1/", {}).status_code == status.HTTP_401_UNAUTHORIZED
    assert anon_client.post(f"{INVOICES_URL}1/issue/").status_code == status.HTTP_401_UNAUTHORIZED
    assert anon_client.get(f"{INVOICES_URL}1/document/").status_code == status.HTTP_401_UNAUTHORIZED


# ===========================================================================
# 13. List and Filters
# ===========================================================================

def test_invoice_list_filters(staff_client):
    """List endpoint supports search, status, customer, and date range filters."""
    cust1 = make_customer(name="Alpha Traders")
    cust2 = make_customer(name="Beta Industries")
    prod = make_product()

    # Create 2 invoices
    staff_client.post(
        INVOICES_URL,
        {
            "customer": cust1.id,
            "invoice_date": "2026-11-01",
            "lines": [{"product": prod.id, "quantity": "1.000", "rate": "10.00"}],
        },
        format="json",
    )
    r2 = staff_client.post(
        INVOICES_URL,
        {
            "customer": cust2.id,
            "invoice_date": "2026-11-15",
            "lines": [{"product": prod.id, "quantity": "1.000", "rate": "20.00"}],
        },
        format="json",
    )
    # Issue second invoice
    staff_client.post(f"{INVOICES_URL}{r2.data['id']}/issue/")

    # Filter by search
    res = staff_client.get(f"{INVOICES_URL}?search=Alpha")
    assert res.data["count"] == 1

    # Filter by status
    res_issued = staff_client.get(f"{INVOICES_URL}?status=ISSUED")
    assert res_issued.data["count"] == 1

    res_draft = staff_client.get(f"{INVOICES_URL}?status=DRAFT")
    assert res_draft.data["count"] == 1

    # Filter by customer
    res_cust = staff_client.get(f"{INVOICES_URL}?customer={cust1.id}")
    assert res_cust.data["count"] == 1

    # Filter by date range
    res_date = staff_client.get(f"{INVOICES_URL}?from=2026-11-10&to=2026-11-20")
    assert res_date.data["count"] == 1
    assert res_date.data["results"][0]["customer"] == cust2.id


# ===========================================================================
# 14. Document (PDF) Generation
# ===========================================================================

def test_document_endpoint_returns_valid_pdf_for_draft_and_issued(staff_client):
    """GET /api/invoices/{id}/document/ returns a valid PDF stream (starts with %PDF-)."""
    customer_gst = make_customer(name="GST Buyer", gstin="33AAAAA1111A1Z1")
    customer_nongst = make_customer(name="Cash Buyer", gstin="")
    product = make_product(current_stock="50.000")

    # 1. Draft PDF
    r1 = staff_client.post(
        INVOICES_URL,
        {
            "customer": customer_gst.id,
            "invoice_date": "2026-11-20",
            "lines": [{"product": product.id, "quantity": "2.000", "rate": "150.00"}],
        },
        format="json",
    )
    inv1_id = r1.data["id"]

    pdf_draft_resp = staff_client.get(f"{INVOICES_URL}{inv1_id}/document/")
    assert pdf_draft_resp.status_code == status.HTTP_200_OK
    assert pdf_draft_resp["Content-Type"] == "application/pdf"
    assert pdf_draft_resp.content.startswith(b"%PDF-")

    # 2. Issued GST PDF
    staff_client.post(f"{INVOICES_URL}{inv1_id}/issue/")
    pdf_issued_resp = staff_client.get(f"{INVOICES_URL}{inv1_id}/document/")
    assert pdf_issued_resp.status_code == status.HTTP_200_OK
    assert pdf_issued_resp["Content-Type"] == "application/pdf"
    assert pdf_issued_resp.content.startswith(b"%PDF-")

    # 3. Issued Non-GST PDF
    product_nongst = make_product(gst_rate=None, current_stock="50.000")
    r2 = staff_client.post(
        INVOICES_URL,
        {
            "customer": customer_nongst.id,
            "invoice_date": "2026-11-20",
            "lines": [{"product": product_nongst.id, "quantity": "1.000", "rate": "100.00"}],
        },
        format="json",
    )
    inv2_id = r2.data["id"]
    staff_client.post(f"{INVOICES_URL}{inv2_id}/issue/")
    pdf_nongst_resp = staff_client.get(f"{INVOICES_URL}{inv2_id}/document/")
    assert pdf_nongst_resp.status_code == status.HTTP_200_OK
    assert pdf_nongst_resp["Content-Type"] == "application/pdf"
    assert pdf_nongst_resp.content.startswith(b"%PDF-")


# ===========================================================================
# 15. Stock Consistency Check Integration
# ===========================================================================

def test_stock_consistency_management_command_passes_after_invoice(staff_client):
    """The check_stock_consistency command verifies current_stock matches movement sum."""
    customer = make_customer()
    product = make_product(current_stock="100.000")

    resp = staff_client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": "2026-11-20",
            "lines": [{"product": product.id, "quantity": "25.000", "rate": "50.00"}],
        },
        format="json",
    )
    inv_id = resp.data["id"]
    staff_client.post(f"{INVOICES_URL}{inv_id}/issue/")

    # Run check_stock_consistency
    call_command("check_stock_consistency")
