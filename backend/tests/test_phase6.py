"""
Phase 6 tests — Payments and outstanding balances.

Test groups:
    1. Partial payments then full settlement (statuses and balances)
    2. Over-allocation and Path A allocation-sum rejection
    3. Draft, other-customer and duplicate-invoice allocation rejection
    4. Concurrent payments cannot over-allocate one invoice
    5. client_token retry safety
    6. Customer outstanding, open invoices, statement and payment history
    7. List filters, search, detail and immutability
    8. Authentication and zero-total invoices
"""

import threading
from decimal import Decimal

import pytest
from django.db import connections
from django.db.models import Sum
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.common.constants import (
    InvoiceStatus,
    ItemType,
    MovementType,
    PaymentStatus,
    Role,
)
from apps.company.models import CompanySettings
from apps.customers.models import Customer, CustomerCodeCounter
from apps.inventory.models import StockMovement
from apps.invoices.models import Invoice
from apps.payments.models import Payment, PaymentAllocation
from apps.products.models import Product, ProductCodeCounter, Unit

PAYMENTS_URL = "/api/payments/"
INVOICES_URL = "/api/invoices/"
CUSTOMERS_URL = "/api/customers/"

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reference_data(db):
    """Ensure units, counters and company settings exist."""
    Unit.objects.get_or_create(name="pcs")
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
        "name": "Payment Customer",
        "phone": "9998887776",
        "gstin": "",
        "state": "Tamil Nadu",
        "billing_address": "456 Trade Road, Chennai",
        "is_active": True,
    }
    defaults.update(kwargs)
    if "code" not in defaults:
        counter, _ = CustomerCodeCounter.objects.get_or_create(
            pk=1, defaults={"next_value": 1}
        )
        defaults["code"] = f"C{counter.next_value:04d}"
        counter.next_value += 1
        counter.save(update_fields=["next_value"])
    return Customer.objects.create(**defaults)


def make_product(current_stock="1000.000", **kwargs) -> Product:
    unit = Unit.objects.get(name=kwargs.pop("unit_name", "pcs"))
    defaults = {
        "name": "Payment Widget",
        "item_type": ItemType.GOODS,
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

    if initial_stock > 0:
        creator = User.objects.filter(role=Role.ADMIN).first() or User.objects.first()
        StockMovement.objects.create(
            product=product,
            movement_type=MovementType.OPENING,
            quantity_change=initial_stock,
            balance_after=initial_stock,
            reason="Initial stock",
            created_by=creator,
        )
    return product


def create_invoice(
    client,
    customer,
    *,
    quantity="10.000",
    rate="100.00",
    invoice_date="2026-11-20",
    issue=True,
):
    """Create (and by default issue) an invoice through the API."""
    product = make_product(current_stock="1000.000")
    response = client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": invoice_date,
            "invoice_type": "NON_GST",
            "lines": [
                {
                    "product": product.id,
                    "quantity": quantity,
                    "rate": rate,
                }
            ],
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED, response.data
    invoice_id = response.data["id"]

    if issue:
        issued = client.post(f"{INVOICES_URL}{invoice_id}/issue/")
        assert issued.status_code == status.HTTP_200_OK, issued.data

    return Invoice.objects.get(pk=invoice_id)


def pay(client, customer, allocations, *, amount=None, **kwargs):
    """
    Record a payment.

    `allocations` is a list of (invoice, amount) pairs. When `amount` is
    omitted it is the sum of the allocations.
    """
    if amount is None:
        amount = sum((value for _, value in allocations), Decimal("0.00"))

    payload = {
        "customer": customer.id,
        "payment_date": kwargs.pop("payment_date", "2026-11-20"),
        "amount": str(amount),
        "method": kwargs.pop("method", "UPI"),
        "reference": kwargs.pop("reference", ""),
        "note": kwargs.pop("note", ""),
        "allocations": [
            {"invoice": invoice.id, "amount": str(value)}
            for invoice, value in allocations
        ],
    }
    payload.update(kwargs)
    return client.post(PAYMENTS_URL, payload, format="json")


# ===========================================================================
# 1. Partial payments then full settlement
# ===========================================================================

def test_partial_payments_then_full_settlement(staff_client):
    """One invoice accepts several partial payments and then a settlement."""
    customer = make_customer()
    invoice = create_invoice(staff_client, customer)
    assert invoice.grand_total == Decimal("1000.00")

    # First partial payment.
    response = pay(staff_client, customer, [(invoice, Decimal("300.00"))])
    assert response.status_code == status.HTTP_201_CREATED, response.data
    assert response.data["amount"] == "300.00"
    assert len(response.data["allocations"]) == 1

    detail = staff_client.get(f"{INVOICES_URL}{invoice.id}/").data
    assert detail["paid_amount"] == "300.00"
    assert detail["balance_due"] == "700.00"
    assert detail["payment_status"] == PaymentStatus.PARTIALLY_PAID

    # Second partial payment.
    response = pay(staff_client, customer, [(invoice, Decimal("300.00"))])
    assert response.status_code == status.HTTP_201_CREATED, response.data

    detail = staff_client.get(f"{INVOICES_URL}{invoice.id}/").data
    assert detail["paid_amount"] == "600.00"
    assert detail["balance_due"] == "400.00"
    assert detail["payment_status"] == PaymentStatus.PARTIALLY_PAID

    # Full settlement of the remaining balance.
    response = pay(staff_client, customer, [(invoice, Decimal("400.00"))])
    assert response.status_code == status.HTTP_201_CREATED, response.data

    detail = staff_client.get(f"{INVOICES_URL}{invoice.id}/").data
    assert detail["paid_amount"] == "1000.00"
    assert detail["balance_due"] == "0.00"
    assert detail["payment_status"] == PaymentStatus.PAID

    # List filter follows the same derived status.
    filtered = staff_client.get(
        f"{INVOICES_URL}?payment_status={PaymentStatus.PAID}"
    ).data
    assert filtered["count"] == 1
    assert filtered["results"][0]["id"] == invoice.id

    unpaid = staff_client.get(
        f"{INVOICES_URL}?payment_status={PaymentStatus.UNPAID}"
    ).data
    assert unpaid["count"] == 0


# ===========================================================================
# 2. Over-allocation and allocation-sum rules
# ===========================================================================

def test_over_allocation_rejected(staff_client):
    """An allocation above the remaining balance returns OVER_ALLOCATION."""
    customer = make_customer()
    invoice = create_invoice(staff_client, customer)

    response = pay(staff_client, customer, [(invoice, Decimal("1100.00"))])

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == "OVER_ALLOCATION"
    assert response.data["details"][0]["invoice"] == invoice.id
    assert Payment.objects.count() == 0
    assert PaymentAllocation.objects.count() == 0


def test_allocations_must_sum_to_payment_amount(staff_client):
    """Path A rejects a payment whose allocations do not equal its amount."""
    customer = make_customer()
    invoice = create_invoice(staff_client, customer)

    response = pay(
        staff_client,
        customer,
        [(invoice, Decimal("400.00"))],
        amount=Decimal("500.00"),
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "VALIDATION_ERROR"
    assert "allocations" in response.data["fields"]
    assert Payment.objects.count() == 0


# ===========================================================================
# 3. Invalid allocation targets
# ===========================================================================

def test_allocation_to_draft_invoice_rejected(staff_client):
    """A draft invoice cannot receive a payment."""
    customer = make_customer()
    draft = create_invoice(staff_client, customer, issue=False)

    response = pay(staff_client, customer, [(draft, Decimal("100.00"))])

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "VALIDATION_ERROR"
    assert Payment.objects.count() == 0


def test_allocation_to_other_customers_invoice_rejected(staff_client):
    """An invoice belonging to a different customer is rejected."""
    payer = make_customer(name="Payer")
    other = make_customer(name="Other Customer")
    other_invoice = create_invoice(staff_client, other)

    response = pay(staff_client, payer, [(other_invoice, Decimal("100.00"))])

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "VALIDATION_ERROR"
    assert Payment.objects.count() == 0


def test_duplicate_invoice_in_one_payment_rejected(staff_client):
    """The same invoice may appear only once in a payment."""
    customer = make_customer()
    invoice = create_invoice(staff_client, customer)

    response = pay(
        staff_client,
        customer,
        [(invoice, Decimal("200.00")), (invoice, Decimal("300.00"))],
        amount=Decimal("500.00"),
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "VALIDATION_ERROR"
    assert Payment.objects.count() == 0


# ===========================================================================
# 4. Concurrency
# ===========================================================================

@pytest.mark.django_db(transaction=True)
def test_concurrent_payments_cannot_over_allocate(admin_user, staff_client):
    """Two simultaneous payments cannot together exceed the invoice balance."""
    customer = make_customer()
    invoice = create_invoice(staff_client, customer)
    assert invoice.grand_total == Decimal("1000.00")

    client_one = APIClient()
    client_one.force_login(admin_user)
    client_two = APIClient()
    client_two.force_login(admin_user)

    results = []

    def pay_worker(client):
        try:
            response = pay(client, customer, [(invoice, Decimal("800.00"))])
            results.append(response.status_code)
        finally:
            connections.close_all()

    first = threading.Thread(target=pay_worker, args=(client_one,))
    second = threading.Thread(target=pay_worker, args=(client_two,))
    first.start()
    second.start()
    first.join()
    second.join()

    connections.close_all()

    # Exactly one payment fits in the 1000.00 balance; the other is rejected.
    assert sorted(results) == [
        status.HTTP_201_CREATED,
        status.HTTP_409_CONFLICT,
    ]
    assert Payment.objects.count() == 1
    assert Payment.objects.get().amount == Decimal("800.00")
    assert (
        PaymentAllocation.objects.filter(invoice=invoice).aggregate(
            total=Sum("amount")
        )["total"]
        == Decimal("800.00")
    )


# ===========================================================================
# 5. client_token retry safety
# ===========================================================================

def test_client_token_retry_creates_one_payment(staff_client):
    """A retry with the same client_token returns the original payment."""
    customer = make_customer()
    invoice = create_invoice(staff_client, customer)
    token = "6f8d9c1e-2b3a-4c5d-8e7f-90123456789a"

    first = pay(
        staff_client,
        customer,
        [(invoice, Decimal("250.00"))],
        client_token=token,
    )
    assert first.status_code == status.HTTP_201_CREATED, first.data

    second = pay(
        staff_client,
        customer,
        [(invoice, Decimal("250.00"))],
        client_token=token,
    )
    assert second.status_code == status.HTTP_200_OK, second.data
    assert second.data["id"] == first.data["id"]

    assert Payment.objects.count() == 1
    assert PaymentAllocation.objects.count() == 1

    detail = staff_client.get(f"{INVOICES_URL}{invoice.id}/").data
    assert detail["paid_amount"] == "250.00"


# ===========================================================================
# 6. Outstanding, open invoices, statement and payment history
# ===========================================================================

def test_customer_outstanding_equals_sum_of_invoice_balances(staff_client):
    """Customer outstanding is the sum of the issued invoices' balances."""
    customer = make_customer()
    first = create_invoice(
        staff_client, customer, invoice_date="2026-11-01"
    )
    second = create_invoice(
        staff_client, customer, quantity="5.000", invoice_date="2026-11-02"
    )

    response = pay(staff_client, customer, [(first, Decimal("300.00"))])
    assert response.status_code == status.HTTP_201_CREATED

    detail = staff_client.get(f"{CUSTOMERS_URL}{customer.id}/").data
    assert detail["outstanding_amount"] == "1200.00"

    listing = staff_client.get(f"{CUSTOMERS_URL}?search=Payment").data
    row = next(item for item in listing["results"] if item["id"] == customer.id)
    assert row["outstanding_amount"] == "1200.00"

    # Issued invoices only: a draft invoice adds nothing.
    create_invoice(staff_client, customer, issue=False)
    detail = staff_client.get(f"{CUSTOMERS_URL}{customer.id}/").data
    assert detail["outstanding_amount"] == "1200.00"


def test_open_invoices_endpoint(staff_client):
    """Open invoices are issued, still have a balance, and oldest comes first."""
    customer = make_customer()
    older = create_invoice(
        staff_client, customer, invoice_date="2026-11-01"
    )
    newer = create_invoice(
        staff_client, customer, quantity="5.000", invoice_date="2026-11-02"
    )

    # Settle the newer invoice; only the older one remains open.
    response = pay(staff_client, customer, [(newer, Decimal("500.00"))])
    assert response.status_code == status.HTTP_201_CREATED

    data = staff_client.get(
        f"{CUSTOMERS_URL}{customer.id}/open-invoices/"
    ).data
    assert data["count"] == 1
    assert data["results"][0]["id"] == older.id
    assert data["results"][0]["balance_due"] == "1000.00"
    assert data["results"][0]["payment_status"] == PaymentStatus.UNPAID


def test_statement_running_balance_equals_outstanding(staff_client):
    """The statement's final running balance equals customer outstanding."""
    customer = make_customer()
    first = create_invoice(
        staff_client, customer, invoice_date="2026-11-01"
    )
    second = create_invoice(
        staff_client, customer, quantity="5.000", invoice_date="2026-11-02"
    )
    response = pay(
        staff_client,
        customer,
        [(first, Decimal("300.00"))],
        payment_date="2026-11-03",
        reference="UPI-111",
    )
    assert response.status_code == status.HTTP_201_CREATED

    data = staff_client.get(
        f"{CUSTOMERS_URL}{customer.id}/statement/"
    ).data
    assert data["count"] == 3

    entries = data["results"]
    assert [entry["type"] for entry in entries] == [
        "INVOICE",
        "INVOICE",
        "PAYMENT",
    ]
    assert [entry["balance"] for entry in entries] == [
        "1000.00",
        "1500.00",
        "1200.00",
    ]
    assert entries[2]["reference"] == "UPI-111"
    assert entries[2]["credit"] == "300.00"
    assert entries[2]["debit"] == "0.00"

    detail = staff_client.get(f"{CUSTOMERS_URL}{customer.id}/").data
    assert detail["outstanding_amount"] == entries[-1]["balance"]


def test_invoice_and_customer_payment_history(staff_client):
    """Invoice and customer payment history expose the allocated amount."""
    customer = make_customer()
    invoice = create_invoice(staff_client, customer)
    pay(staff_client, customer, [(invoice, Decimal("300.00"))], reference="A")
    pay(staff_client, customer, [(invoice, Decimal("200.00"))], reference="B")

    invoice_payments = staff_client.get(
        f"{INVOICES_URL}{invoice.id}/payments/"
    ).data
    assert invoice_payments["count"] == 2
    assert {
        row["allocated_amount"] for row in invoice_payments["results"]
    } == {"300.00", "200.00"}

    customer_payments = staff_client.get(
        f"{CUSTOMERS_URL}{customer.id}/payments/"
    ).data
    assert customer_payments["count"] == 2
    assert {
        row["amount"] for row in customer_payments["results"]
    } == {"300.00", "200.00"}


# ===========================================================================
# 7. List filters, detail and immutability
# ===========================================================================

def test_payment_list_filters_and_detail(staff_client):
    """Payment list filters, search and detail include the expected data."""
    customer = make_customer()
    invoice = create_invoice(staff_client, customer)

    upi = pay(
        staff_client,
        customer,
        [(invoice, Decimal("100.00"))],
        reference="UPI-4821",
        method="UPI",
        payment_date="2026-11-10",
    )
    assert upi.status_code == status.HTTP_201_CREATED
    cash = pay(
        staff_client,
        customer,
        [(invoice, Decimal("200.00"))],
        reference="CASH-1",
        method="CASH",
        payment_date="2026-11-15",
    )
    assert cash.status_code == status.HTTP_201_CREATED

    by_method = staff_client.get(f"{PAYMENTS_URL}?method=CASH").data
    assert by_method["count"] == 1
    assert by_method["results"][0]["reference"] == "CASH-1"

    by_search = staff_client.get(f"{PAYMENTS_URL}?search=UPI-4821").data
    assert by_search["count"] == 1
    assert by_search["results"][0]["id"] == upi.data["id"]

    by_customer = staff_client.get(
        f"{PAYMENTS_URL}?customer={customer.id}"
    ).data
    assert by_customer["count"] == 2

    by_date = staff_client.get(
        f"{PAYMENTS_URL}?from=2026-11-12&to=2026-11-20"
    ).data
    assert by_date["count"] == 1
    assert by_date["results"][0]["reference"] == "CASH-1"

    detail = staff_client.get(f"{PAYMENTS_URL}{upi.data['id']}/").data
    assert detail["customer_name"] == customer.name
    assert detail["method"] == "UPI"
    assert detail["allocations"][0]["invoice"] == invoice.id
    assert detail["allocations"][0]["amount"] == "100.00"


def test_payments_are_immutable(staff_client):
    """V1 has no payment edit or delete endpoints."""
    customer = make_customer()
    invoice = create_invoice(staff_client, customer)
    response = pay(staff_client, customer, [(invoice, Decimal("100.00"))])
    payment_id = response.data["id"]

    patch = staff_client.patch(
        f"{PAYMENTS_URL}{payment_id}/",
        {"amount": "50.00"},
        format="json",
    )
    assert patch.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    delete = staff_client.delete(f"{PAYMENTS_URL}{payment_id}/")
    assert delete.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# ===========================================================================
# 8. Authentication and zero-total invoices
# ===========================================================================

def test_endpoints_require_authentication(anon_client):
    """Every Phase 6 endpoint rejects anonymous requests."""
    assert anon_client.get(PAYMENTS_URL).status_code == status.HTTP_401_UNAUTHORIZED
    assert anon_client.get(f"{PAYMENTS_URL}1/").status_code == status.HTTP_401_UNAUTHORIZED
    assert (
        anon_client.get(f"{CUSTOMERS_URL}1/open-invoices/").status_code
        == status.HTTP_401_UNAUTHORIZED
    )
    assert (
        anon_client.get(f"{CUSTOMERS_URL}1/payments/").status_code
        == status.HTTP_401_UNAUTHORIZED
    )
    assert (
        anon_client.get(f"{CUSTOMERS_URL}1/statement/").status_code
        == status.HTTP_401_UNAUTHORIZED
    )
    assert (
        anon_client.get(f"{INVOICES_URL}1/payments/").status_code
        == status.HTTP_401_UNAUTHORIZED
    )
    assert (
        anon_client.post(
            PAYMENTS_URL,
            {
                "customer": 1,
                "payment_date": "2026-11-20",
                "amount": "1.00",
                "method": "CASH",
                "allocations": [],
            },
            format="json",
        ).status_code
        == status.HTTP_401_UNAUTHORIZED
    )


def test_zero_total_invoice_is_paid(staff_client):
    """A zero-total issued invoice is PAID with no balance."""
    customer = make_customer()
    invoice = create_invoice(staff_client, customer, quantity="1.000", rate="0.00")
    assert invoice.grand_total == Decimal("0.00")

    detail = staff_client.get(f"{INVOICES_URL}{invoice.id}/").data
    assert detail["paid_amount"] == "0.00"
    assert detail["balance_due"] == "0.00"
    assert detail["payment_status"] == PaymentStatus.PAID

    paid = staff_client.get(
        f"{INVOICES_URL}?payment_status={PaymentStatus.PAID}"
    ).data
    assert paid["count"] == 1
    assert paid["results"][0]["id"] == invoice.id
