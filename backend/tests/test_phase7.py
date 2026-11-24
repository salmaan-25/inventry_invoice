"""
Phase 7 tests — Delivery Challans.

Test groups:
    1. Partial challan, then a second challan completes delivery
    2. Over-dispatch rejection and duplicate / empty / zero payloads
    3. Concurrent challans cannot over-dispatch one line
    4. Challans never change stock or create movements
    5. Draft, service-only and service-line rejection
    6. Dispatch summary, awaiting-dispatch and delivery status filters
    7. List filters, detail, document and authentication
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
    DeliveryStatus,
    ItemType,
    MovementType,
    Role,
)
from apps.company.models import CompanySettings
from apps.customers.models import Customer, CustomerCodeCounter
from apps.delivery.models import DeliveryChallan, DeliveryChallanItem
from apps.inventory.models import StockMovement
from apps.invoices.models import Invoice
from apps.products.models import Product, ProductCodeCounter, Unit

CHALLANS_URL = "/api/challans/"
INVOICES_URL = "/api/invoices/"

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reference_data(db):
    """Ensure units, counters and company settings exist."""
    Unit.objects.get_or_create(name="pcs")
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
        "name": "Delivery Customer",
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


def make_product(
    item_type=ItemType.GOODS,
    current_stock="1000.000",
    **kwargs,
) -> Product:
    unit = Unit.objects.get(name=kwargs.pop("unit_name", "pcs"))
    defaults = {
        "name": "Delivery Widget",
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
    if item_type == ItemType.SERVICE:
        initial_stock = Decimal("0.000")
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


def create_invoice(client, customer, lines, *, issue=True, invoice_date="2026-11-20"):
    """
    Create an invoice through the API.

    `lines` is a list of (product, quantity, rate) tuples.
    """
    payload_lines = [
        {
            "product": product.id,
            "quantity": str(quantity),
            "rate": str(rate),
        }
        for product, quantity, rate in lines
    ]
    response = client.post(
        INVOICES_URL,
        {
            "customer": customer.id,
            "invoice_date": invoice_date,
            "lines": payload_lines,
        },
        format="json",
    )
    assert response.status_code == status.HTTP_201_CREATED, response.data
    invoice_id = response.data["id"]

    if issue:
        issued = client.post(f"{INVOICES_URL}{invoice_id}/issue/")
        assert issued.status_code == status.HTTP_200_OK, issued.data

    return Invoice.objects.get(pk=invoice_id)


def item_for(invoice, product) -> "InvoiceItem":
    return invoice.items.get(product=product)


def post_challan(
    client,
    invoice,
    items,
    *,
    delivery_date="2026-11-18",
    delivered_by="Ravi",
    received_by="Site supervisor",
):
    """`items` is a list of (invoice_item, quantity) pairs."""
    return client.post(
        CHALLANS_URL,
        {
            "invoice": invoice.id,
            "delivery_date": delivery_date,
            "delivered_by": delivered_by,
            "received_by": received_by,
            "items": [
                {
                    "invoice_item": invoice_item.id,
                    "quantity": str(quantity),
                }
                for invoice_item, quantity in items
            ],
        },
        format="json",
    )


def invoice_detail(client, invoice):
    response = client.get(f"{INVOICES_URL}{invoice.id}/")
    assert response.status_code == status.HTTP_200_OK, response.data
    return response.data


def dispatch_summary(client, invoice):
    response = client.get(f"{INVOICES_URL}{invoice.id}/dispatch-summary/")
    assert response.status_code == status.HTTP_200_OK, response.data
    return response.data


# ===========================================================================
# 1. Partial then complete delivery
# ===========================================================================

def test_partial_challan_then_second_challan_completes_delivery(staff_client):
    customer = make_customer()
    product = make_product()
    invoice = create_invoice(
        staff_client, customer, [(product, "10.000", "100.00")]
    )
    line = item_for(invoice, product)

    assert invoice_detail(staff_client, invoice)["delivery_status"] == (
        DeliveryStatus.PENDING
    )

    first = post_challan(staff_client, invoice, [(line, "4.000")])
    assert first.status_code == status.HTTP_201_CREATED, first.data
    assert first.data["delivered_by"] == "Ravi"
    assert first.data["items"][0]["quantity"] == "4.000"
    assert first.data["items"][0]["product_name"] == product.name

    detail = invoice_detail(staff_client, invoice)
    assert detail["delivery_status"] == DeliveryStatus.PARTIALLY_DELIVERED

    summary = dispatch_summary(staff_client, invoice)
    assert summary["delivery_status"] == DeliveryStatus.PARTIALLY_DELIVERED
    assert summary["items"][0]["invoiced_quantity"] == "10.000"
    assert summary["items"][0]["dispatched_quantity"] == "4.000"
    assert summary["items"][0]["remaining_quantity"] == "6.000"
    assert summary["items"][0]["dispatchable"] is True

    second = post_challan(staff_client, invoice, [(line, "6.000")])
    assert second.status_code == status.HTTP_201_CREATED, second.data

    detail = invoice_detail(staff_client, invoice)
    assert detail["delivery_status"] == DeliveryStatus.DELIVERED

    summary = dispatch_summary(staff_client, invoice)
    assert summary["delivery_status"] == DeliveryStatus.DELIVERED
    assert summary["items"][0]["dispatched_quantity"] == "10.000"
    assert summary["items"][0]["remaining_quantity"] == "0.000"


def test_delivery_status_list_filter(staff_client):
    customer = make_customer()
    product = make_product()

    pending = create_invoice(
        staff_client, customer, [(product, "5.000", "100.00")]
    )
    partial = create_invoice(
        staff_client, customer, [(product, "5.000", "100.00")]
    )
    delivered = create_invoice(
        staff_client, customer, [(product, "5.000", "100.00")]
    )

    post_challan(
        staff_client, partial, [(item_for(partial, product), "2.000")]
    )
    post_challan(
        staff_client, delivered, [(item_for(delivered, product), "5.000")]
    )

    def ids(status_value):
        response = staff_client.get(
            f"{INVOICES_URL}?delivery_status={status_value}&page_size=100"
        )
        assert response.status_code == status.HTTP_200_OK
        return {row["id"] for row in response.data["results"]}

    assert ids(DeliveryStatus.PENDING) == {pending.id}
    assert ids(DeliveryStatus.PARTIALLY_DELIVERED) == {partial.id}
    assert ids(DeliveryStatus.DELIVERED) == {delivered.id}
    assert ids("NOT_A_STATUS") == set()


# ===========================================================================
# 2. Over-dispatch and payload validation
# ===========================================================================

def test_over_dispatch_rejected_and_remaining_kept(staff_client):
    customer = make_customer()
    product = make_product()
    invoice = create_invoice(
        staff_client, customer, [(product, "10.000", "100.00")]
    )
    line = item_for(invoice, product)

    response = post_challan(staff_client, invoice, [(line, "11.000")])
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == "OVER_DISPATCH"
    assert response.data["details"][0]["remaining"] == "10.000"
    assert response.data["details"][0]["requested"] == "11.000"
    assert DeliveryChallan.objects.count() == 0

    assert post_challan(
        staff_client, invoice, [(line, "7.000")]
    ).status_code == status.HTTP_201_CREATED

    response = post_challan(staff_client, invoice, [(line, "4.000")])
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["details"][0]["remaining"] == "3.000"
    assert DeliveryChallan.objects.count() == 1

    summary = dispatch_summary(staff_client, invoice)
    assert summary["items"][0]["remaining_quantity"] == "3.000"


def test_duplicate_empty_and_zero_items_rejected(staff_client):
    customer = make_customer()
    product = make_product()
    invoice = create_invoice(
        staff_client, customer, [(product, "10.000", "100.00")]
    )
    line = item_for(invoice, product)

    duplicate = post_challan(
        staff_client, invoice, [(line, "2.000"), (line, "3.000")]
    )
    assert duplicate.status_code == status.HTTP_400_BAD_REQUEST
    assert duplicate.data["code"] == "VALIDATION_ERROR"

    empty = post_challan(staff_client, invoice, [])
    assert empty.status_code == status.HTTP_400_BAD_REQUEST

    zero = post_challan(staff_client, invoice, [(line, "0.000")])
    assert zero.status_code == status.HTTP_400_BAD_REQUEST

    assert DeliveryChallan.objects.count() == 0


def test_invoice_line_from_another_invoice_rejected(staff_client):
    customer = make_customer()
    product = make_product()
    first = create_invoice(
        staff_client, customer, [(product, "5.000", "100.00")]
    )
    second = create_invoice(
        staff_client, customer, [(product, "5.000", "100.00")]
    )

    response = post_challan(
        staff_client, first, [(item_for(second, product), "1.000")]
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "VALIDATION_ERROR"
    assert DeliveryChallan.objects.count() == 0


# ===========================================================================
# 3. Concurrency
# ===========================================================================

@pytest.mark.django_db(transaction=True)
def test_concurrent_challans_cannot_over_dispatch(admin_user, staff_client):
    customer = make_customer()
    product = make_product()
    invoice = create_invoice(
        staff_client, customer, [(product, "10.000", "100.00")]
    )
    line = item_for(invoice, product)

    client_one = APIClient()
    client_one.force_login(admin_user)
    client_two = APIClient()
    client_two.force_login(admin_user)

    results = []

    def dispatch_worker(client):
        try:
            response = post_challan(client, invoice, [(line, "8.000")])
            results.append(response.status_code)
        finally:
            connections.close_all()

    first = threading.Thread(target=dispatch_worker, args=(client_one,))
    second = threading.Thread(target=dispatch_worker, args=(client_two,))
    first.start()
    second.start()
    first.join()
    second.join()

    connections.close_all()

    # Exactly one challan fits in the 10.000 remaining.
    assert sorted(results) == [
        status.HTTP_201_CREATED,
        status.HTTP_409_CONFLICT,
    ]
    assert DeliveryChallan.objects.count() == 1
    assert (
        DeliveryChallanItem.objects.filter(invoice_item=line).aggregate(
            total=Sum("quantity")
        )["total"]
        == Decimal("8.000")
    )


# ===========================================================================
# 4. Stock is never touched
# ===========================================================================

def test_challan_does_not_change_stock_or_movements(staff_client):
    customer = make_customer()
    product = make_product()
    invoice = create_invoice(
        staff_client, customer, [(product, "10.000", "100.00")]
    )
    line = item_for(invoice, product)

    product.refresh_from_db()
    stock_before = product.current_stock
    movement_count_before = StockMovement.objects.filter(product=product).count()

    response = post_challan(staff_client, invoice, [(line, "4.000")])
    assert response.status_code == status.HTTP_201_CREATED, response.data

    product.refresh_from_db()
    assert product.current_stock == stock_before
    assert (
        StockMovement.objects.filter(product=product).count()
        == movement_count_before
    )
    assert not StockMovement.objects.filter(
        product=product,
        movement_type=MovementType.SALE,
        reason__icontains=f"challan",
    ).exists()


# ===========================================================================
# 5. State and item-type rules
# ===========================================================================

def test_draft_invoice_cannot_receive_challan(staff_client):
    customer = make_customer()
    product = make_product()
    invoice = create_invoice(
        staff_client, customer, [(product, "5.000", "100.00")], issue=False
    )

    response = post_challan(
        staff_client, invoice, [(item_for(invoice, product), "1.000")]
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == "INVALID_STATE"
    assert DeliveryChallan.objects.count() == 0


def test_service_line_rejected_and_service_only_invoice_has_no_status(
    staff_client,
):
    customer = make_customer()
    goods = make_product()
    service = make_product(
        item_type=ItemType.SERVICE,
        name="Installation",
        unit_name="hour",
        selling_price="500.00",
        gst_rate=None,
        hsn_sac="9987",
    )

    mixed = create_invoice(
        staff_client,
        customer,
        [(goods, "5.000", "100.00"), (service, "2.000", "500.00")],
    )
    goods_line = item_for(mixed, goods)
    service_line = item_for(mixed, service)

    summary = dispatch_summary(staff_client, mixed)
    by_type = {line["item_type"]: line for line in summary["items"]}
    assert by_type[ItemType.GOODS]["dispatchable"] is True
    assert by_type[ItemType.SERVICE]["dispatchable"] is False
    assert by_type[ItemType.SERVICE]["remaining_quantity"] == "2.000"

    response = post_challan(staff_client, mixed, [(service_line, "1.000")])
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "VALIDATION_ERROR"

    response = post_challan(
        staff_client, mixed, [(goods_line, "1.000"), (service_line, "1.000")]
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert DeliveryChallan.objects.count() == 0

    # A service-only invoice cannot receive a challan and has null status.
    service_only = create_invoice(
        staff_client, customer, [(service, "3.000", "500.00")]
    )
    assert (
        invoice_detail(staff_client, service_only)["delivery_status"] is None
    )

    response = post_challan(
        staff_client,
        service_only,
        [(item_for(service_only, service), "1.000")],
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert DeliveryChallan.objects.count() == 0

    # The mixed invoice is still PENDING with only its goods line remaining.
    assert (
        invoice_detail(staff_client, mixed)["delivery_status"]
        == DeliveryStatus.PENDING
    )


# ===========================================================================
# 6. Dispatch summary, awaiting dispatch and filters
# ===========================================================================

def test_awaiting_dispatch_lists_only_remaining_goods(staff_client):
    customer = make_customer()
    product = make_product()
    service = make_product(
        item_type=ItemType.SERVICE,
        name="Service Call",
        unit_name="hour",
        selling_price="500.00",
        gst_rate=None,
        hsn_sac="9987",
    )

    pending = create_invoice(
        staff_client, customer, [(product, "5.000", "100.00")]
    )
    partial = create_invoice(
        staff_client, customer, [(product, "5.000", "100.00")]
    )
    delivered = create_invoice(
        staff_client, customer, [(product, "5.000", "100.00")]
    )
    draft = create_invoice(
        staff_client, customer, [(product, "5.000", "100.00")], issue=False
    )
    service_only = create_invoice(
        staff_client, customer, [(service, "1.000", "500.00")]
    )

    post_challan(
        staff_client, partial, [(item_for(partial, product), "2.000")]
    )
    post_challan(
        staff_client, delivered, [(item_for(delivered, product), "5.000")]
    )

    response = staff_client.get(
        f"{INVOICES_URL}awaiting-dispatch/?page_size=100"
    )
    assert response.status_code == status.HTTP_200_OK, response.data

    ids = {row["id"] for row in response.data["results"]}
    assert ids == {pending.id, partial.id}
    assert draft.id not in ids
    assert service_only.id not in ids

    for row in response.data["results"]:
        assert row["delivery_status"] in (
            DeliveryStatus.PENDING,
            DeliveryStatus.PARTIALLY_DELIVERED,
        )


def test_challan_list_filters_by_invoice_customer_and_date(staff_client):
    customer_one = make_customer(name="Customer One")
    customer_two = make_customer(name="Customer Two", phone="9990001112")
    product = make_product()

    invoice_one = create_invoice(
        staff_client, customer_one, [(product, "10.000", "100.00")]
    )
    invoice_two = create_invoice(
        staff_client, customer_two, [(product, "10.000", "100.00")]
    )

    first = post_challan(
        staff_client,
        invoice_one,
        [(item_for(invoice_one, product), "2.000")],
        delivery_date="2026-11-18",
    )
    assert first.status_code == status.HTTP_201_CREATED, first.data

    second = post_challan(
        staff_client,
        invoice_two,
        [(item_for(invoice_two, product), "3.000")],
        delivery_date="2026-11-20",
    )
    assert second.status_code == status.HTTP_201_CREATED, second.data

    def result_ids(query=""):
        response = staff_client.get(f"{CHALLANS_URL}?page_size=100{query}")
        assert response.status_code == status.HTTP_200_OK, response.data
        return {row["id"] for row in response.data["results"]}

    assert result_ids(f"&invoice={invoice_one.id}") == {first.data["id"]}
    assert result_ids(f"&customer={customer_two.id}") == {second.data["id"]}
    assert result_ids("&from=2026-11-18&to=2026-11-18") == {
        first.data["id"]
    }
    assert result_ids("&from=2026-11-19&to=2026-11-21") == {
        second.data["id"]
    }


# ===========================================================================
# 7. Detail, document and authentication
# ===========================================================================

def test_challan_detail_and_document(staff_client):
    customer = make_customer()
    product = make_product()
    invoice = create_invoice(
        staff_client, customer, [(product, "10.000", "100.00")]
    )
    created = post_challan(
        staff_client, invoice, [(item_for(invoice, product), "4.000")]
    )
    assert created.status_code == status.HTTP_201_CREATED, created.data

    challan_id = created.data["id"]
    detail = staff_client.get(f"{CHALLANS_URL}{challan_id}/")
    assert detail.status_code == status.HTTP_200_OK, detail.data
    assert detail.data["invoice"] == invoice.id
    assert detail.data["customer"] == customer.id
    assert detail.data["items"][0]["quantity"] == "4.000"

    document = staff_client.get(f"{CHALLANS_URL}{challan_id}/document/")
    assert document.status_code == status.HTTP_200_OK
    assert document["Content-Type"] == "application/pdf"
    assert document.content.startswith(b"%PDF")
    assert len(document.content) > 100


def test_challan_endpoints_require_authentication(anon_client):
    response = anon_client.get(CHALLANS_URL)
    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    )

    response = anon_client.post(CHALLANS_URL, {}, format="json")
    assert response.status_code in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    )
